import os
import tempfile
from datetime import datetime

from flask import Blueprint, request, jsonify, Response, stream_with_context
from langchain_community.document_loaders import UnstructuredMarkdownLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from werkzeug.utils import secure_filename

from model.response import success
from service.agent.assistant_service import create_assistant_service, get_assistant_service, \
    get_or_create_assistant_service
from web.vo.answer_vo import AnswerVo
from web.vo.result_vo import ResultVo

assistantApi = Blueprint('assistant', __name__)


@assistantApi.route('/welcome', methods=['GET'])
def welcome():
    business_key = request.args.get('businessKey')

    assistant_service = get_or_create_assistant_service(business_key)

    answer = AnswerVo(content="您好好，我是您的AI助手，请问有什么可以帮您？")

    return jsonify(success(answer).to_dict())



@assistantApi.route('/askAssistant', methods=['GET'])
def ask_assistant():
    question = request.args.get('question')
    session_id = request.args.get('sessionId')
    business_key = request.args.get('businessKey')

    assistant_service = get_or_create_assistant_service(business_key)

    event_stream = assistant_service.get_event_stream_function(question, session_id)

    return Response(stream_with_context(event_stream()), mimetype='text/event-stream')


@assistantApi.route('/uploadFile', methods=['POST'])
def upload_file():
    """
    处理文件上传的POST请求方法
    从前端接收文件并获取文件内容
    """
    # 检查是否有文件在请求中
    if 'file' not in request.files:
        result = ResultVo(success= False, result="未找到文件")
        return jsonify(success(result).to_dict())

    file = request.files['file']

    # 检查文件名是否为空
    if file.filename == '':
        result = ResultVo(success=False, result="未找到文件")
        return jsonify(success(result).to_dict())

    business_key = request.args.get('businessKey')

    assistant_service = get_or_create_assistant_service(business_key)

    assistant_service.upload_file(file)

    result = ResultVo(success=True, result="success")
    return jsonify(success(result).to_dict())
