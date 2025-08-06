import asyncio
from typing import Any

from flask import Blueprint, jsonify, request

from model.response import success, failure
from model.work_group import WorkGroup
from service.workflow_new_service import create_workflow, get_workflow, WorkflowService
from util.http_util import http_get
from model.workplace import Workplace
from web.answer_vo import AnswerVo

agentApi = Blueprint('myAgent', __name__)
# 注册蓝图



# 定义一个路由，返回 JSON 数据
@agentApi.route('/welcome', methods=['GET'])
def welcome():
    workplace_code = request.args.get('workplaceCode')
    work_group_code = request.args.get('workGroupCode')
    #session_id = request.args.get('sessionId')

    workplace = get_workplace(workplace_code)
    work_group = get_work_group(work_group_code, workplace_code)

    create_workflow(workplace, work_group)

    content = f"我是{work_group.name}的组长助理，有什么可以帮您？"
    res = success(content)
    return jsonify(res.to_dict())

@agentApi.route('/question', methods=['POST'])
def handle_question():
    if not request.is_json:
        return jsonify(failure())

    data = request.get_json()
    workplace_code = data.get('workplaceCode')
    work_group_code = data.get('workGroupCode')
    session_id = data.get('sessionId')
    question = data.get('question')

    workflow_service = get_or_create_workflow_service(workplace_code, work_group_code)

    content = asyncio.run(workflow_service.question(question, session_id))
    answer = AnswerVo("", content, "")

    return jsonify(success(answer.to_dict()).to_dict())


@agentApi.route('/train', methods=['POST'])
def train():
    if not request.is_json:
        return jsonify(failure())

    data = request.get_json()

    workplace_code = data.get('workplaceCode')
    work_group_code = data.get('workGroupCode')
    session_id = data.get('sessionId')

    human_msg_id = data.get('humanId')
    human_content = data.get('humanContent')
    ai_msg_id = data.get('aiId')
    ai_content = data.get('aiContent')

    workflow_service = get_or_create_workflow_service(workplace_code, work_group_code)

    try:
        workflow_service.train(session_id, human_msg_id, human_content, ai_msg_id, ai_content)
        return jsonify(success("success").to_dict())
    except Exception as e:
        return jsonify(failure(e))



def get_or_create_workflow_service(workplace_code, work_group_code) -> WorkflowService:
    workflow_service = get_workflow(workplace_code, work_group_code)
    if workflow_service is None:
        workplace = get_workplace(workplace_code)
        work_group = get_work_group(work_group_code, workplace_code)

        workflow_service = create_workflow(workplace, work_group)
    return workflow_service


# 获取工作点
def get_workplace(workplace_code) -> Workplace:
    res = http_get(f"/workplace/findWorkplaceByCode?workplaceCode={workplace_code}")
    data: dict[str, Any] = res["data"]
    workplace = Workplace(data["name"], data["code"], data["desc"])

    return workplace


# 获取工作组
def get_work_group(work_group_code, workplace_code) -> WorkGroup:
    res = http_get(f"/workGroup/findByCode?workplaceCode={workplace_code}&workGroupCode={work_group_code}")
    data: dict[str, Any] = res["data"]
    work_group = WorkGroup(data["name"], data["code"], data["positionName"], data["desc"])
    return work_group
