import asyncio

from marshmallow import fields
from quart import Blueprint, jsonify, Response, g

from model.response import success
from service.agent.data_analyst_service import create_service, get_service, DataAnalystService, \
    get_or_create_data_analyst_service
from web.validate.validator import validate_query_params, validate_json_params
from web.vo.answer_vo import AnswerVo
from web.vo.result_vo import ResultVo

dataAnalystApi = Blueprint('dataAnalyst', __name__)

@dataAnalystApi.route('/welcome', methods=['GET'])
@validate_query_params(
    businessKey=fields.Str(required=True),
    sessionId=fields.Str(required=True)
)
async def welcome():
    business_key = g.validated_data['businessKey']
    session_id = g.validated_data['sessionId']

    data_analyst_service = get_or_create_data_analyst_service(business_key)

    event_stream = data_analyst_service.get_event_stream_function(None, session_id, "default")

    return Response(event_stream(), mimetype='text/event-stream')



@dataAnalystApi.route('/question', methods=['POST'])
@validate_json_params(
    businessKey=fields.Str(required=True),
    sessionId=fields.Str(required=True),
    question=fields.Str(required=True)
)
def handle_question():
    business_key = g.validated_data['businessKey']
    session_id = g.validated_data['sessionId']
    question = g.validated_data['question']

    data_analyst_service = get_or_create_data_analyst_service(business_key)

    content = asyncio.run(data_analyst_service.question(question, session_id))
    answer = AnswerVo(content=content)

    return jsonify(success(answer).to_dict())

# 中断取消专用
@dataAnalystApi.route('/resumeInterrupt', methods=['POST'])
@validate_json_params(
    businessKey=fields.Str(required=True),
    sessionId=fields.Str(required=True),
    resume_type=fields.Str(required=True)
)
def resume_interrupt():
    business_key = g.validated_data['businessKey']
    session_id = g.validated_data['sessionId']
    resume_type = g.validated_data['resume_type']

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
async def resume_interrupt_stream():
    business_key = g.validated_data['businessKey']
    session_id = g.validated_data['sessionId']
    resume_type = g.validated_data['resume_type']

    data_analyst_service = get_or_create_data_analyst_service(business_key)

    event_stream = data_analyst_service.get_event_stream_function(resume_type, session_id, "resume")

    return Response(event_stream(), mimetype='text/event-stream')

@dataAnalystApi.route('/getStateProperties', methods=['GET'])
@validate_query_params(
    businessKey=fields.Str(required=True),
    sessionId=fields.Str(required=True),
    statePropertyNames=fields.Str(required=True)
)
def get_state_properties():
    business_key = g.validated_data['businessKey']
    session_id = g.validated_data['sessionId']
    state_property_names = g.validated_data['statePropertyNames']

    data_analyst_service = get_or_create_data_analyst_service(business_key)
    data = data_analyst_service.get_state_properties(session_id, state_property_names)

    result = ResultVo(success=True, result=data)
    return jsonify(success(result).to_dict())


@dataAnalystApi.route('/getFrequentlyAndUsuallyExecuteTasks', methods=['GET'])
@validate_query_params(
    businessKey=fields.Str(required=True),
)
def get_frequently_and_usually_execute_tasks():
    business_key = g.validated_data['businessKey']

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
    business_key = g.validated_data['businessKey']
    session_id = g.validated_data['sessionId']
    question = g.validated_data['question']

    data_analyst_service = get_or_create_data_analyst_service(business_key)

    event_stream = data_analyst_service.get_event_stream_function(question, session_id, "question")

    return Response(event_stream(), mimetype='text/event-stream')

