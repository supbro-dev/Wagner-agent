from typing import Any

from flask import Blueprint, jsonify, request
import json

from model.response import success, failure
from model.work_group import WorkGroup
from service.agent_service import AgentService, create_agent, get_agent
from util.http_util import http_get
from model.workplace import Workplace

agentApi = Blueprint('myAgent', __name__)


# 定义一个路由，返回 JSON 数据
@agentApi.route('/welcome', methods=['GET'])
def welcome():
    workplace_code = request.args.get('workplaceCode')
    work_group_code = request.args.get('workGroupCode')

    workplace = get_workplace(workplace_code)
    work_group = get_work_group(work_group_code, workplace_code)

    agent_service = create_agent(workplace, work_group)

    content = agent_service.welcome()

    res = success(content)
    return jsonify(res.to_dict())

@agentApi.route('/question', methods=['POST'])
def handleQuestion():
    if not request.is_json:
        return jsonify(failure())

    data = request.get_json()
    workplace_code = data.get('workplaceCode')
    work_group_code = data.get('workGroupCode')
    question = data.get('question')

    agent_service = get_agent(workplace_code, work_group_code)
    content = agent_service.question(question)
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
