import asyncio
import json
import queue
import threading
from typing import Any

from flask import Blueprint, jsonify, request, Response, stream_with_context

from model.response import success, failure
from service.tool.wagner.model.work_group import WorkGroup
from service.tool.wagner.model.workplace import Workplace
from service.agent.workflow_service import create_workflow, get_workflow, WorkflowService, AI_CHAT_NODES, AI_MSG_NODES, \
    convert_2_interrupt
from util.http_util import http_get
from web.answer_vo import AnswerVo
from web.result_vo import ResultVo

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

    content = f"我是{work_group.name}的AI数据员，有什么可以帮您？"
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

    def event_stream():

        # 为每个请求创建专用队列
        data_queue = queue.Queue()

        def run_workflow():
            try:
                stream = workflow_service.resume_stream(resume_type, session_id)
                for stream_mode, detail in stream:
                    if stream_mode == "messages":
                        # print("resume", stream_mode, detail)
                        chunk, metadata = detail
                        if metadata['langgraph_node'] in AI_CHAT_NODES:
                            content = chunk.content
                            data_queue.put({"token": content})
                    elif stream_mode == "tasks":
                        # print("resume", stream_mode, detail)
                        if "interrupts" in detail and len(detail["interrupts"]) > 0:
                            data_queue.put({"interrupt": convert_2_interrupt(detail["interrupts"][0]).to_json()})
                        elif detail["name"] in AI_MSG_NODES:
                            content = get_tasks_mode_ai_msg_content(detail)
                            if content is not None:
                                data_queue.put({"token": content})
            finally:
                data_queue.put(None)

        # 启动 LangGraph 线程
        threading.Thread(target=run_workflow).start()

        # 从队列获取数据并发送
        while True:
            data = data_queue.get()
            if data is None:
                yield "event: done\ndata: \n\n"
                break
            # 格式化为 SSE 事件
            yield f"data: {json.dumps(data)}\n\n"

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

    def event_stream():

        # 为每个请求创建专用队列
        data_queue = queue.Queue()

        def run_workflow():
            try:
                stream = workflow_service.stream_question(question, session_id)
                for stream_mode, detail in stream:
                    if stream_mode == "messages":
                        chunk, metadata = detail
                        if metadata['langgraph_node'] in AI_CHAT_NODES:
                            # print("question", stream_mode, detail)
                            content = chunk.content
                            data_queue.put({"token":content})
                    elif stream_mode == "tasks":
                        # print("question", stream_mode, detail)
                        if "interrupts" in detail and len(detail["interrupts"]) > 0:
                            data_queue.put({"interrupt":convert_2_interrupt(detail["interrupts"][0]).to_json()})
                        elif detail["name"] in AI_MSG_NODES:
                            content = get_tasks_mode_ai_msg_content(detail)
                            if content is not None:
                                data_queue.put({"token":content})
            finally:
                data_queue.put(None)

        # 启动 LangGraph 线程
        threading.Thread(target=run_workflow).start()

        # 从队列获取数据并发送
        while True:
            data = data_queue.get()
            if data is None:
                yield "event: done\ndata: \n\n"
                break
            # 格式化为 SSE 事件
            yield f"data: {json.dumps(data)}\n\n"

    return Response(stream_with_context(event_stream()), mimetype='text/event-stream')

# 解析这个结构没想到更好的办法
def get_tasks_mode_ai_msg_content(detail) -> str | None:
    if "result" in detail:
        msgs = detail["result"][0]
        if msgs[0] == "messages":
            msg_list = msgs[1]
            for m in msg_list:
                if m[0] == "ai":
                    return m[1]
    return None


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
