import asyncio
import json
from typing import Optional


from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain_deepseek import ChatDeepSeek
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode
from quart import Quart, request, stream_with_context, Response, Blueprint

import container

from config import Config
from dao import query_data_task_dao
from model.query_data_task_detail import QueryDataTaskDetail
from model.response import success
from service.agent.model.state import State, InputState
from util.config_util import read_private_config
from web.data_analyst_controller import get_or_create_data_analyst_service
from web.vo.result_vo import ResultVo

adminApi = Blueprint('admin', __name__)
#
# @adminApi.route('/addAllTask2Vector', methods=['GET'])
# def add_all_task_2_vector():
#     business_key = request.args.get('businessKey')
#
#     data_analyst_service = get_or_create_data_analyst_service(business_key)
#     task_list = container.dao_container.query_data_task_dao().get_all_tasks(business_key)
#
#     texts = []
#     metadatas = []
#     for task in task_list:
#         detail = QueryDataTaskDetail.model_validate(json.loads(task.task_detail))
#         texts.append(f"任务名称：{task.name}\n任务目标：{detail.target}")
#         metadatas.append({
#                 "task_id": task.id,
#                 "task_name": task.name,
#                 "task_detail": task.task_detail
#             })
#
#     data_analyst_service.vector_store.add_texts(texts=texts, metadatas=metadatas)
#
#     result = ResultVo(success=True,result="加载完成")
#     return jsonify(success(result).to_dict())


connections = {
    "mcp_server":{"url": "http://localhost:8001/mcp/", "transport": "streamable_http"},
}

client = MultiServerMCPClient(connections)
tools = asyncio.run(client.get_tools())


async def talk_with_llm(state: State):
    api_key: Optional[str] = read_private_config("deepseek", "API_KEY")
    llm = ChatDeepSeek(
        model=Config.LLM_MODEL,
        temperature=0,
        max_tokens=None,
        timeout=None,
        max_retries=2,
        api_key=api_key
    )

    intent_prompt = ChatPromptTemplate.from_messages([
        # 系统提示词
        ("system", f"""你是一个助理"""),
        # 包含所有历史对话
        *state.messages
    ])

    chain = intent_prompt | llm.bind_tools(tools)
    res = await chain.ainvoke({})

    return {
        "messages": [res],

    }

def talk_edge(state: State):
    last_msg = state.messages[-1]
    if not last_msg.tool_calls:
        return END
    else:
        return "weather_tool"



builder = StateGraph(State, input_schema=InputState)
# 新Graph
builder.add_node("talk", talk_with_llm)
builder.add_node("weather_tool", ToolNode(tools))
builder.add_edge(START, "talk")
builder.add_conditional_edges("talk", talk_edge)
builder.add_edge("weather_tool", "talk")
builder.add_edge("talk", END)

graph = builder.compile(name="admin")

@adminApi.route(rule = '/talk', methods=['GET'])
async def talk():
    query = request.args.get('query')

    @stream_with_context
    async def async_event_stream():
        try:
            # 上下文配置
            config = RunnableConfig(
                configurable={"thread_id": "1"},
            )

            stream = graph.astream(
                input=InputState(messages=[("user", query)]),
                config=config,
                stream_mode=["messages","tasks"]
            )

            # 直接异步迭代处理流数据
            async for stream_mode, detail in stream:
                if stream_mode == "messages":
                    chunk, metadata = detail
                    content = chunk.content
                    print(content)
                    yield f"data: {json.dumps({'msgId': chunk.id, 'token': content})}\n\n"
            yield "event: done\ndata: \n\n"

        except Exception as e:
            yield f"event: error\ndata: {str(e)}\n\n"
            yield "event: done\ndata: \n\n"

    return Response(async_event_stream(), mimetype='text/event-stream')









