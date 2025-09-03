import asyncio
import json
import queue
import threading
from datetime import datetime
from typing import Any

from flask import Blueprint, jsonify, request, Response, stream_with_context

from model.response import success, failure
from service.tool.wagner.model.work_group import WorkGroup
from service.tool.wagner.model.workplace import Workplace
from service.agent.workflow_service import create_workflow, get_workflow, WorkflowService, AI_CHAT_NODES, AI_MSG_NODES, \
    convert_2_interrupt
from util import datetime_util
from util.http_util import http_get
from web.vo.answer_vo import AnswerVo
from web.vo.result_vo import ResultVo
from service.tool.wagner.wagner_service import get_employee, get_group_employee, get_employee_time_on_task, \
    get_employee_efficiency, make_work_group_business_key

agentApi = Blueprint('myAgent', __name__)
# 注册蓝图



# 定义一个路由，返回 JSON 数据
@agentApi.route('/welcome', methods=['GET'])
def welcome():
    workplace_code = request.args.get('workplaceCode')
    work_group_code = request.args.get('workGroupCode')

    get_or_create_workflow_service(workplace_code, work_group_code)

    content = f"我是本组的AI数据员，有什么可以帮您？"
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
    answer = AnswerVo(content=content)

    return jsonify(success(answer).to_dict())

# 中断取消专用
@agentApi.route('/resumeInterrupt', methods=['POST'])
def resume_interrupt():
    if not request.is_json:
        return jsonify(failure())

    data = request.get_json()
    workplace_code = data.get('workplaceCode')
    work_group_code = data.get('workGroupCode')
    session_id = data.get('sessionId')
    resume_type = data.get('resumeType')

    workflow_service = get_or_create_workflow_service(workplace_code, work_group_code)

    content, interrupt = workflow_service.resume(resume_type, session_id)

    answer = AnswerVo(content=content, interrupt=interrupt)
    return jsonify(success(answer).to_dict())

@agentApi.route('/resumeInterruptStream', methods=['GET'])
def resume_interrupt_stream():
    workplace_code = request.args.get('workplaceCode')
    work_group_code = request.args.get('workGroupCode')
    session_id = request.args.get('sessionId')
    resume_type = request.args.get('resumeType')

    workflow_service = get_or_create_workflow_service(workplace_code, work_group_code)

    event_stream = workflow_service.get_event_stream_function(resume_type, session_id, "resume")

    return Response(stream_with_context(event_stream()), mimetype='text/event-stream')

@agentApi.route('/getFrequentlyAndUsuallyExecuteTasks', methods=['GET'])
def get_frequently_and_usually_execute_tasks():
    workplace_code = request.args.get('workplaceCode')
    work_group_code = request.args.get('workGroupCode')

    workflow_service = get_or_create_workflow_service(workplace_code, work_group_code)

    names = workflow_service.get_frequently_and_usually_execute_tasks()

    result = ResultVo(result=list(names))
    return jsonify(success(result).to_dict())

# 流式路由
@agentApi.route('/stream', methods=['GET'])
def stream_response():
    workplace_code = request.args.get('workplaceCode')
    work_group_code = request.args.get('workGroupCode')
    session_id = request.args.get('sessionId')
    question = request.args.get('question')

    workflow_service = get_or_create_workflow_service(workplace_code, work_group_code)

    event_stream = workflow_service.get_event_stream_function(question, session_id, "question")

    return Response(stream_with_context(event_stream()), mimetype='text/event-stream')


def get_or_create_workflow_service(workplace_code, work_group_code) -> WorkflowService:
    # 初始化业务键
    business_key = make_work_group_business_key(workplace_code, work_group_code)

    workflow_service = get_workflow(business_key)
    if workflow_service is None:
        workplace = get_workplace(workplace_code)
        work_group = get_work_group(work_group_code, workplace_code)

        # 当前时间
        current_date = datetime_util.format_datatime(datetime.now())
        # 业务系统提示词
        basic_system_template = (
            f"你的角色是{workplace.name}这个工作点的一名工作组:{work_group.name}的数据员，该小组的工作岗位是:{work_group.position_name}。"
            f"你所在的工作点为{workplace.name}，编码是：【{workplace.code}】，具体介绍是【{workplace.desc}】。"
            f"你参与管理的小组，该小组的编码为：【{work_group.code}】"
            f"另一个重要参数：业务键为{business_key}。"
            "你的日常工作就是辅助你的小组长一起管理这个小组，所有员工信息、员工出勤情况、作业数据、作业情况都会由专门的工具获取，不要随便编造数据。"
            f"当前日期是{current_date}")
        # 所有业务系统工具
        business_tool_list = [get_employee, get_group_employee, get_employee_time_on_task, get_employee_efficiency]
        # 工作流名称
        workflow_name = "work_group_agent"

        workflow_service = create_workflow(workflow_name, business_key, basic_system_template, business_tool_list)
    return workflow_service


# 获取工作点
def get_workplace(workplace_code) -> Workplace:
    res = http_get(f"/workplace/findWorkplaceByCode?workplaceCode={workplace_code}")
    data: dict[str, Any] = res["data"]
    workplace = Workplace(name = data["name"], code = data["code"], desc = data["desc"])

    return workplace


# 获取工作组
def get_work_group(work_group_code, workplace_code) -> WorkGroup:
    res = http_get(f"/workGroup/findByCode?workplaceCode={workplace_code}&workGroupCode={work_group_code}")
    data: dict[str, Any] = res["data"]
    work_group = WorkGroup(name = data["name"], code = data["code"], position_name = data["positionName"], desc = data["desc"])
    return work_group
