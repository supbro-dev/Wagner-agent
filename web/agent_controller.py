import asyncio
from typing import Any

from flask import Blueprint, jsonify, request
import json

from model.response import success, failure
from model.work_group import WorkGroup
from service.workflow_service import create_workflow, get_workflow
from util.http_util import http_get
from model.workplace import Workplace

agentApi = Blueprint('myAgent', __name__)


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

    workflow_service = get_workflow(workplace_code, work_group_code)

    content = asyncio.run(workflow_service.question(question, session_id))

    return jsonify(success(content).to_dict())


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
