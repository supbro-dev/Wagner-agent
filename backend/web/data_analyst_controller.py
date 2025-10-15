import asyncio
import json
import queue
import threading
from datetime import datetime
from typing import Any

from flask import Blueprint, jsonify, request, Response, stream_with_context
from marshmallow import Schema, fields

from model.response import success, failure_with_ex, failure_with_msg
from service.agent.data_analyst_service import create_service, get_service, DataAnalystService
from util import datetime_util
from util.http_util import http_get_old
from web.validate.validator import validate_query_params
from web.vo.answer_vo import AnswerVo
from web.vo.result_vo import ResultVo

dataAnalystApi = Blueprint('dataAnalyst', __name__)

@dataAnalystApi.route('/async-test')
async def async_test():
    return "Async working!"


@dataAnalystApi.route('/welcome', methods=['GET'])
@validate_query_params(
    businessKey=fields.Str(required=True),
    sessionId=fields.Str(required=True)
)
async def welcome():
    business_key = request.validated_data.get('businessKey')
    session_id = request.validated_data.get('sessionId')

    data_analyst_service = get_or_create_data_analyst_service(business_key)

    event_stream = data_analyst_service.get_event_stream_function_(None, session_id, "default")

    return Response(stream_with_context(event_stream()), mimetype='text/event-stream')



@dataAnalystApi.route('/question', methods=['POST'])
@validate_query_params(
    businessKey=fields.Str(required=True),
    sessionId=fields.Str(required=True),
    question=fields.Str(required=True)
)
def handle_question():
    business_key = request.validated_data.get('businessKey')
    session_id = request.validated_data.get('sessionId')
    question = request.validated_data.get('question')

    data_analyst_service = get_or_create_data_analyst_service(business_key)

    content = asyncio.run(data_analyst_service.question(question, session_id))
    answer = AnswerVo(content=content)

    return jsonify(success(answer).to_dict())

# 中断取消专用
@dataAnalystApi.route('/resumeInterrupt', methods=['POST'])
@validate_query_params(
    businessKey=fields.Str(required=True),
    sessionId=fields.Str(required=True),
    resume_type=fields.Str(required=True)
)
def resume_interrupt():
    business_key = request.validated_data.get('businessKey')
    session_id = request.validated_data.get('sessionId')
    resume_type = request.validated_data.get('resume_type')

    data_analyst_service = get_or_create_data_analyst_service(business_key)

    content, interrupt = data_analyst_service.resume(resume_type, session_id)

    answer = AnswerVo(content=content, interrupt=interrupt)
    return jsonify(success(answer).to_dict())

@dataAnalystApi.route('/resumeInterruptStream', methods=['GET'])
@validate_query_params(
    businessKey=fields.Str(required=True),
    sessionId=fields.Str(required=True),
    resume_type=fields.Str(required=True)
)
def resume_interrupt_stream():
    business_key = request.validated_data.get('businessKey')
    session_id = request.validated_data.get('sessionId')
    resume_type = request.validated_data.get('resume_type')

    data_analyst_service = get_or_create_data_analyst_service(business_key)

    event_stream = data_analyst_service.get_event_stream_function(resume_type, session_id, "resume")

    return Response(stream_with_context(event_stream()), mimetype='text/event-stream')

@dataAnalystApi.route('/getStateProperties', methods=['GET'])
@validate_query_params(
    businessKey=fields.Str(required=True),
    sessionId=fields.Str(required=True),
    statePropertyNames=fields.Str(required=True)
)
def get_state_properties():
    business_key = request.validated_data.get('businessKey')
    session_id = request.validated_data.get('sessionId')
    state_property_names = request.validated_data.get("statePropertyNames")

    data_analyst_service = get_or_create_data_analyst_service(business_key)
    data = data_analyst_service.get_state_properties(session_id, state_property_names)

    result = ResultVo(success=True, result=data)
    return jsonify(success(result).to_dict())


@dataAnalystApi.route('/getFrequentlyAndUsuallyExecuteTasks', methods=['GET'])
@validate_query_params(
    businessKey=fields.Str(required=True),
)
def get_frequently_and_usually_execute_tasks():
    business_key = request.validated_data.get('businessKey')

    data_analyst_service = get_or_create_data_analyst_service(business_key)

    names = data_analyst_service.get_frequently_and_usually_execute_tasks()

    result = ResultVo(success=True, result=list(names))
    return jsonify(success(result).to_dict())

# 流式路由
@dataAnalystApi.route('/questionStream', methods=['GET'])
@validate_query_params(
    businessKey=fields.Str(required=True),
    sessionId=fields.Str(required=True),
    question=fields.Str(required=True)
)
async def question_stream():
    business_key = request.validated_data.get('businessKey')
    session_id = request.validated_data.get('sessionId')
    question = request.validated_data.get('question')

    data_analyst_service = get_or_create_data_analyst_service(business_key)

    event_stream = data_analyst_service.get_event_stream_function_(question, session_id, "question")

    return Response(stream_with_context(event_stream()), mimetype='text/event-stream')


def get_or_create_data_analyst_service(business_key) -> DataAnalystService:
    data_analyst_service = get_service(business_key)
    if data_analyst_service is None:
        data_analyst_service = create_service(business_key, business_key)
    return data_analyst_service