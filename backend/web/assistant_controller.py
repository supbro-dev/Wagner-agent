from marshmallow import fields
from quart import Blueprint, request, jsonify, Response, g

from model.response import success
from service.agent.assistant_service import get_or_create_assistant_service
from web.validate.validator import validate_query_params, validate_json_params
from web.vo.answer_vo import AnswerVo
from web.vo.result_vo import ResultVo

assistantApi = Blueprint('assistant', __name__)


@assistantApi.route('/welcome', methods=['GET'])
@validate_query_params(
    businessKey=fields.Str(required=True),
)
async def welcome():
    business_key = g.validated_data['businessKey']

    assistant_service = get_or_create_assistant_service(business_key)

    answer = AnswerVo(content="您好，我是您的AI助手，请问有什么可以帮您？")

    return jsonify(success(answer).to_dict())



@assistantApi.route('/askAssistant', methods=['GET'])
@validate_query_params(
    businessKey=fields.Str(required=True),
    sessionId=fields.Str(required=True),
    question=fields.Str(required=True)
)
async def ask_assistant():
    question = g.validated_data['question']
    session_id = g.validated_data['sessionId']
    business_key = g.validated_data['businessKey']

    assistant_service = get_or_create_assistant_service(business_key)

    event_stream = assistant_service.get_event_stream_function(question, session_id)

    return Response(event_stream(), mimetype='text/event-stream')

@assistantApi.route('/addProceduralMemory', methods=['POST'])
@validate_json_params(
    businessKey=fields.Str(required=True),
    sessionId=fields.Str(required=True),
    msgId=fields.Str(required=True),
)
async def add_procedural_memory():
    session_id = g.validated_data['sessionId']
    business_key = g.validated_data['businessKey']
    msg_id = g.validated_data['msgId']

    assistant_service = get_or_create_assistant_service(business_key)

    add_result = assistant_service.add_procedural_memory(session_id, msg_id)

    if len(add_result) > 0:
        result = ResultVo(success =True, result="添加永久记忆成功")
    else:
        result = ResultVo(success=False, result="无记忆可添加")

    return jsonify(success(result).to_dict())


@assistantApi.route('/uploadFile', methods=['POST'])
async def upload_file():
    """
    处理文件上传的POST请求方法
    从前端接收文件并获取文件内容
    """
    # 获取上传的文件
    files = await request.files
    file = files.get('file')  # 'file' 是前端表单中的字段名

    # 检查文件名是否为空
    if file.filename == '':
        result = ResultVo(success=False, result="未找到文件")
        return jsonify(success(result).to_dict())

    business_key = request.args.get('businessKey')

    assistant_service = get_or_create_assistant_service(business_key)
    try:
        await assistant_service.upload_file(file)
        result = ResultVo(success=True, result="success")
        return jsonify(success(result).to_dict())
    except Exception as e:
        result = ResultVo(success=False, result=str(e))
        return jsonify(success(result).to_dict())


