import asyncio
import json
import logging
import os
import queue
import threading
import time
from enum import StrEnum

import redis
from typing import Callable, Any
from typing import List
from typing import Literal
from typing import Optional, cast

from langchain_redis import RedisConfig, RedisVectorStore
from langchain.output_parsers import OutputFixingParser
from langchain_community.vectorstores import Redis
from langchain_core.callbacks import BaseCallbackHandler, CallbackManager
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool as create_tool, ArgsSchema
from langchain_core.tools import tool
from langchain_deepseek import ChatDeepSeek
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import OpenAIEmbeddings
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.interrupt import HumanInterruptConfig, HumanInterrupt
from langgraph.types import interrupt, Command, Interrupt
from openai import responses
from quart import stream_with_context

import container
from config import Config
from dao import query_data_task_dao
from dao.agent_def_dao import AgentDefDAO
from dao.llm_tool_dao import LLMToolDAO
from dao.query_data_task_dao import QueryDataTaskDAO
from entity.agent_def_entity import AgentDefType, AgentDefEntity
from entity.llm_tool_entity import LLMToolType, LLMToolEntity
from entity.query_data_task_entity import QueryDataTaskEntity
from model.llm_http_tool_content import LLMHTTPToolContent
from model.query_data_task_detail import QueryDataTaskDetail
from service.agent.model.interrupt import WorkflowInterrupt
from service.agent.model.json_output_schema import QUERY_DATA, EXECUTE, CREATE, EDIT, DELETE, OTHERS, IntentSchema, \
    TaskSchema, DEFAULT, TableSchema, TEST_RUN, SAVE, LineChartSchema
from service.agent.model.resume import WorkflowResume
from service.agent.model.state import State, InputState
from service.tool.llm_http_tool import create_llm_http_tool
from service.tool.mcp_client_tool import create_mcp_client_tools
from util import datetime_util
from util.config_util import read_private_config
from langgraph.checkpoint.redis import RedisSaver
from pydantic import BaseModel, Field, create_model

from util.http_util import http_get, http_post

# 配置基础日志设置（输出到控制台）
logging.basicConfig(
    level=logging.INFO,  # 设置日志级别
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

service_map = {}

class GraphNode(StrEnum):
    # 节点名称
    INTENT_CLASSIFIER = "intent_classifier" #意图探测节点，判断用户是希望创建/修改/执行取数任务，还是做其他不相关的事情
    FIND_TASK_IN_DB = "find_task_in_db" # 根据id或name从db中查找任务
    FIND_TASK_IN_STORE = "find_task_in_store" # 根据用户意图从向量数据库中查找任务
    SAME_NAME_WHEN_CREATE = "same_name_when_create" # 创建任务时查找到同名任务
    EXECUTE_TASK = "execute_task" # 根据id或name查找并执行任务
    CREATE_TASK = "create_task" # 创建一个新的取数任务
    EDIT_TASK = "edit_task" # 编辑任务信息时更新任务信息对象
    DELETE_TASK = "delete_task" # 逻辑删除任务
    TOOLS_FOR_TASK = "tools_for_task" # 所有数据查询工具，用来给EXECUTE_TASK节点执行任务
    QUERY_DATA_NODE = "query_data_node" # 用来调用工具做简单的数据查询
    TOOLS_FOR_QUERY_DATA = "tools_for_query_data" # 所有数据查询工具，用来给QUERY_DATA_NODE节点执行任务
    TOOLS_FOR_UPDATE_TASK = "tools_for_update_task" # 保存任务用的工具，包括人工审核
    TOOLS_FOR_DELETE_TASK = "tools_for_delete_task" # 删除任务用的工具，包括人工审核
    HOW_TO_IMPROVE_TASK = "how_to_improve_task" # 检查是否还需要用户进一步完善任务模板内容
    SAVE_TASK = "save_task" # 保存任务
    TEST_RUN_TASK = "test_run_task" # 试跑任务
    DEFAULT_NODE = "default_node"
    CONVERT_TO_STANDARD_FORMAT = "convert_to_standard_format" # 把试跑或执行任务的结果转化成标准格式
    START = "__start__"
    END = "__end__"


# 记录有AI逐步返回token返回的节点
AI_CHAT_NODES = [GraphNode.EXECUTE_TASK, GraphNode.QUERY_DATA_NODE, GraphNode.HOW_TO_IMPROVE_TASK, GraphNode.DELETE_TASK, GraphNode.TEST_RUN_TASK, GraphNode.DEFAULT_NODE]
# 记录人工构造AI MSG
AI_MSG_NODES = [GraphNode.SAME_NAME_WHEN_CREATE, GraphNode.SAVE_TASK]


# 默认中断配置
DEFAULT_INTERRUPT_CONFIG = {
            "allow_accept": True,
            "allow_edit": True,
            "allow_respond": True,
        }


# 默认任务模板
DEFAULT_TASK_TEMPLATE = QueryDataTaskDetail(
        target="无。(请说明该任务的使用意图)",
        query_param="无。(请索命该任务执行时需要使用哪些查询参数，例如查询日期为昨天)",
        data_operation="无。(请详细描述，查询到结果之后希望进行哪些加工处理)",
        data_format="无。(只能选用表格、折线图)"
    )


class CustomCallbackHandler(BaseCallbackHandler):
    def on_chain_start(self, serialized, inputs, **kwargs):
        print(f"开始执行: {serialized.get('name')}")

    def on_chain_end(self, outputs, **kwargs):
        print(f"执行完成，输出: {outputs}")

    def on_chain_error(self, error, **kwargs):
        print(f"执行错误: {error}")

class DataAnalystService:
    # 工作流服务的业务唯一键，同一个business_key下的取数任务名称唯一
    business_key:str
    # 工作流服务默认的系统提示词，包含所有基础业务信息
    basic_system_template:str
    # llm用业务工具
    business_tool_list:list[BaseTool]
    # 任务删除用工具
    delete_task_tool_list:list[BaseTool]
    # langGraph实例
    graph:CompiledStateGraph
    # 向量存储
    vector_store: RedisVectorStore

    # dao
    agent_def_dao: AgentDefDAO
    query_data_task_dao: QueryDataTaskDAO
    llm_tool_dao: LLMToolDAO

    def __init__(self, service_name, business_key:str):
        self.business_key = business_key

        self.agent_def_dao = container.dao_container.agent_def_dao()
        self.query_data_task_dao = container.dao_container.query_data_task_dao()
        self.llm_tool_dao = container.dao_container.llm_tool_dao()

        # 初始化大模型
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_API_KEY"] = read_private_config("langsmith", "LANGSMITH_API_KEY")
        os.environ["LANGSMITH_PROJECT"] = read_private_config("langsmith", "LANGSMITH_PROJECT")

        # 初始化llm
        api_key: Optional[str] = read_private_config("deepseek", "API_KEY")
        self.llm = ChatDeepSeek(
            model=Config.LLM_MODEL,
            temperature=0,
            max_tokens=None,
            timeout=None,
            max_retries=2,
            api_key=api_key
        )

        agent_def = self.get_agent_def(business_key)
        if agent_def is None:
            raise ValueError(f"未找到业务键{business_key}对应的Agent")

        self.basic_system_template = agent_def.system_prompt + f"\n当前日期:{datetime_util.get_current_date()}"

        # 设置业务用所有工具方法
        self.business_tool_list = self.get_business_tool_list(agent_def)

        # 设置业务用所有工具方法
        self.execute_with_business_tool_list = [*self.business_tool_list, self.execute_once]

        # 删除任务的工具
        self.delete_task_tool_list = [add_human_in_the_loop(self.logical_delete_task, [WorkflowResume(resume_type="accept", resume_desc="删除", resume_mode="invoke")], lambda tool_input: f"是否确定要删除任务：{tool_input["task_name"]}?")]

        # 初始化langGraph
        self.graph = self.create_graph(service_name)

        # 初始化向量存储链接
        if Config.USE_VECTOR_STORE:
            self.vector_store = self.create_vector_store()

    def create_graph(self, graph_name):
        """
        创建Graph
        :param graph_name:
        :return: graph
        """
        builder = StateGraph(State, input_schema=InputState)
        # 新Graph
        builder.add_node(GraphNode.INTENT_CLASSIFIER, self.intent_classifier)
        builder.add_node(GraphNode.QUERY_DATA_NODE, self.query_data)
        builder.add_node(GraphNode.FIND_TASK_IN_DB, self.find_task_in_db)
        builder.add_node(GraphNode.FIND_TASK_IN_STORE, self.find_task_in_store)
        builder.add_node(GraphNode.EXECUTE_TASK, self.execute_task)
        builder.add_node(GraphNode.CREATE_TASK, self.create_task)
        builder.add_node(GraphNode.TOOLS_FOR_TASK, ToolNode(self.business_tool_list))
        builder.add_node(GraphNode.TOOLS_FOR_QUERY_DATA, ToolNode(self.business_tool_list))
        builder.add_node(GraphNode.HOW_TO_IMPROVE_TASK, self.how_to_improve_task)
        builder.add_node(GraphNode.SAME_NAME_WHEN_CREATE, self.same_name_when_create)
        builder.add_node(GraphNode.DELETE_TASK, self.delete_task)
        builder.add_node(GraphNode.EDIT_TASK, self.edit_task)
        builder.add_node(GraphNode.TOOLS_FOR_DELETE_TASK, ToolNode(self.delete_task_tool_list))
        builder.add_node(GraphNode.TEST_RUN_TASK, self.test_run_task)
        builder.add_node(GraphNode.SAVE_TASK, self.save_task)
        builder.add_node(GraphNode.DEFAULT_NODE, self.default_node)
        builder.add_node(GraphNode.CONVERT_TO_STANDARD_FORMAT, self.convert_to_standard_format)

        # 起始节点，判断意图
        builder.add_edge(START, GraphNode.INTENT_CLASSIFIER)
        builder.add_conditional_edges(GraphNode.INTENT_CLASSIFIER, self.after_intent_classifier)
        builder.add_conditional_edges(GraphNode.FIND_TASK_IN_DB, self.check_exist_and_next_node)
        builder.add_conditional_edges(GraphNode.FIND_TASK_IN_STORE, self.check_exist_in_store_and_next_node)
        builder.add_conditional_edges(GraphNode.TOOLS_FOR_TASK, self.after_invoke_tool)
        builder.add_edge(GraphNode.TOOLS_FOR_QUERY_DATA, GraphNode.QUERY_DATA_NODE)
        builder.add_conditional_edges(GraphNode.EXECUTE_TASK, self.need_invoke_tool)
        builder.add_conditional_edges(GraphNode.QUERY_DATA_NODE, self.need_invoke_tool)
        builder.add_edge(GraphNode.CREATE_TASK, GraphNode.HOW_TO_IMPROVE_TASK)
        builder.add_edge(GraphNode.HOW_TO_IMPROVE_TASK, END)
        builder.add_edge(GraphNode.SAME_NAME_WHEN_CREATE, END)
        builder.add_edge(GraphNode.EDIT_TASK, GraphNode.HOW_TO_IMPROVE_TASK)
        builder.add_conditional_edges(GraphNode.DELETE_TASK, self.need_invoke_delete_task_tool)
        builder.add_conditional_edges(GraphNode.TEST_RUN_TASK, self.need_invoke_tool)
        builder.add_edge(GraphNode.CONVERT_TO_STANDARD_FORMAT, END)
        builder.add_edge(GraphNode.SAVE_TASK, END)
        builder.add_edge(GraphNode.DEFAULT_NODE, END)

        # 记忆功能
        if Config.MEMORY_USE == "local":
            memory = InMemorySaver()
        else:
            memory = RedisSaver(Config.REDIS_URL)
            # 第一次执行时初始化redis
            # memory.setup()
        graph = builder.compile(name=graph_name, checkpointer=memory)
        # 生成PNG流程图
        try:
            png_data = graph.get_graph().draw_mermaid_png()
            # 保存到文件
            with open("/tmp/langgraph_diagram.png", "wb") as png_file:
                png_file.write(png_data)
            logging.info("流程图已保存为 /tmp/workflow_diagram.png")
        except Exception as e:
            logging.exception("Failed to generate PNG workflow diagram", e)

        return graph
    def create_vector_store(self) -> RedisVectorStore:
        """
        创建向量存储
        :return: vector_store
        """
        model_location :Optional[str] = read_private_config("embedding_models", "LOCATION")
        if model_location is None:
            model_location = Config.EMBEDDING_LOCAL_MODEL

        try:
            model_name = model_location
            model_kwargs = {"device": "cpu"}
            encode_kwargs = {"normalize_embeddings": True}
            embeddings = HuggingFaceEmbeddings(
                model_name=model_name, model_kwargs=model_kwargs, encode_kwargs=encode_kwargs
            )

            config = RedisConfig(
                index_name=self.business_key,
                redis_url=Config.REDIS_URL,
                metadata_schema=[
                    {"name": "task_name", "type": "tag"},
                    {"name": "task_id", "type": "tag"},
                    {"name": "task_detail", "type": "text"},
                ],
            )

            vectorstore = RedisVectorStore(embeddings, config=config)

            return vectorstore
        except Exception as e:
            logging.error("创建向量存储连接失败:", e)
            return None


    def stream_question(self, query, session_id):
        """
        流式触发graph
        :param query: 用户提问信息
        :param session_id: 用来做state的隔离
        :return:stream
        """
        # 使用回调
        handler = CustomCallbackHandler()

        # 上下文配置
        config = RunnableConfig(
            configurable={"thread_id": session_id},
            callbacks=CallbackManager([handler])
        )

        stream = self.graph.astream(
            input=InputState(messages=[("user", query)]),
            config=config,
            stream_mode=["messages", "tasks"]
        )

        return stream

    def default(self, session_id):
        """
        直接返回默认节点
        :param session_id: 用来做state的隔离
        :return:stream
        """
        # 使用回调
        handler = CustomCallbackHandler()

        # 上下文配置
        config = RunnableConfig(
            configurable={"thread_id": session_id},
            callbacks=CallbackManager([handler])
        )

        stream = self.graph.astream(
            input=InputState(
                messages=[],
            ),
            config=config,
            stream_mode=["messages", "tasks"]
        )

        return stream


    async def question(self, query, session_id) -> str:
        """
        同步返回提问的回答（仅用来测试）
        :param query: 用户提问信息
        :param session_id: 用来做state的隔离
        :return: 回答内容
        """
        # 上下文配置
        config = RunnableConfig(
            configurable={"thread_id": session_id},
        )

        res = await self.graph.ainvoke(
            input=InputState(messages=[("user", query)]),
            config=config,
        )

        result = res["messages"][-1]
        content = str(result.content)

        if content == "":
            print("content is empty:", result)

        return content

    def resume(self, resume_type, session_id) -> (str, WorkflowInterrupt):
        """
        同步回复中断
        :param resume_type:回复类型
        :param session_id:用来做state的隔离
        :return: 响应内容或中断详情
        """
        # 上下文配置
        config = {"configurable": {"thread_id": session_id}}

        res = self.graph.invoke(
            Command(resume=[{"resumeType": resume_type}]),
            config=config,
        )

        # 如果是中断
        if "__interrupt__" in res:
            return None, convert_2_interrupt(res["__interrupt__"][0])
        else:
            last_msg = res["messages"][-1]
            return last_msg.content, None

    def stream_resume(self, resume_type, session_id):
        """
        流式回复中断
        :param resume_type:回复类型
        :param session_id:用来做state的隔离
        :return: stream
        """
        # 上下文配置
        config = RunnableConfig(
            configurable={"thread_id": session_id},
        )

        stream = self.graph.stream(input=Command(resume=[{"resumeType": resume_type}]),
                                   config=config,
                                   stream_mode=["messages", "tasks"])

        return stream


    # NODES
    async def intent_classifier(self, state: State):
        """
        意图判断节点
        :param state:
        :return: state
        """

        # 如果没有任何消息，直接返回DEFAULT
        if len(state.messages) == 0:
            state.intent_type = DEFAULT
            return state

        intent_prompt = ChatPromptTemplate.from_messages([
            # 系统提示词
            ("system", f"""{self.basic_system_template}
            
            你的职责是分析用户的意图，如果用户是提问查询某些数据，意图为“查询数据”，如果用户提到和任务相关，有可能是对任务进行创建/修改/删除/执行操作
            
            共有以下几种意图
            1. {QUERY_DATA} - 查询数据  
            2. {EXECUTE} - 执行某个任务
            3. {CREATE} - 创建新任务
            4. {EDIT} - 修改/编辑某个任务
            5. {DELETE} - 删除某个任务
            6. {TEST_RUN} - 试算某个任务
            7. {SAVE} - 保存某个任务
            8. {OTHERS} - 既不查询数据也和任务操作无关     
            
            按JSON格式输出分类结果，无关话题一律归类为OTHERS。
            
            **重要说明**: 以下示例仅用于展示意图分类逻辑，不是实际对话历史，不要直接解析为意图。
                       """),
            # 明确标识示例区
            MessagesPlaceholder("examples", optional=True),
            # 包含所有历史对话
            *state.messages
        ])

        examples = [
            # 使用few-shot示例（强调AI必须返回JsonOutputParser的格式，不加AI会尝试返回自然语言的KV）：
            ("human", "执行任务：本小组上个月的月度人效报告"),
            ("ai", "{\"intent_type\": \"" + EXECUTE + "\", \"task_name\": \"月度人效报告\"}"),
            ("human", "创建任务：一个工时分析报表，用来分析每天组内员工的工时分布"),
            ("ai",
             "{\"intent_type\": \"" + CREATE + "\", \"task_name\": \"工时分析报表\"}"),
            ("human", "查一下员工工时信息"),
            ("ai", "{\"intent_type\": \"" + QUERY_DATA + "\"}"),
            ("human", "试跑任务：员工工时信息"),
            ("ai", "{\"intent_type\": \"" + TEST_RUN + "\", \"task_name\": \"员工工时信息\"}"),
        ]

        parser = JsonOutputParser(pydantic_object=IntentSchema)
        parser_with_llm = OutputFixingParser.from_llm(parser=parser, llm=self.llm)
        chain = intent_prompt | self.llm | parser_with_llm

        result = await chain.ainvoke({
            "examples": examples,
        })

        # 更新状态
        intent_type = result["intent_type"]

        logging.info("推断出的intent_type:%s, result:%s", intent_type, result)

        # 如果用户有明确意图且指定了任务名或任务id，才更新意图类型
        if intent_type in [EXECUTE, TEST_RUN, DELETE, SAVE]:
            if "task_name" in result or "task_id" in result:
                state.intent_type = intent_type
                if "task_id" in result:
                    state.task_id = result["task_id"]
                if "task_name" in result:
                    state.task_name = result["task_name"]
            else:
                # 识别出名称为空时，返回LLM的默认对话
                state.intent_type = DEFAULT
        elif intent_type in [CREATE, EDIT]:
            if "task_name" in result or "task_id" in result:
                if state.task_name != result["task_name"]:
                    # 清空上下文
                    state.last_run_msg_id = None
                    state.last_standard_data = None
                    state.task_detail = None
                    state.first_time_create = True
                    state.target = None
                    state.task_id = None
                    state.task_name = None

                    state.intent_type = intent_type
                    if "task_id" in result:
                        state.task_id = result["task_id"]
                    if "task_name" in result:
                        state.task_name = result["task_name"]

            else:
                # 识别出名称为空时，返回LLM的默认对话
                state.intent_type = DEFAULT
        elif intent_type == QUERY_DATA:
            state.intent_type = intent_type
        elif intent_type == OTHERS and  ("task_name" not in result and "task_id" not in result):
            state.intent_type = intent_type

        return state

    async def default_node(self, state:State):
        # 初次调用，使用原始用户查询
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=f"""
                        {self.basic_system_template}

                        请介绍一下自己，然后询问：有什么可以帮您？
                          """),
            HumanMessage(content="{user_input}")  # 用户最后一条消息
        ])

        chain = prompt | self.llm
        response = await chain.ainvoke({"user_input":"请介绍一下自己"})

        return {
            "messages": [response],
        }


    def find_task_in_db(self, state: State):
        """
        根据任务名称/任务id查找任务详情
        :param state:
        :return:state
        """
        query_data_task = self.find_task_by_id_or_name(state.task_id, state.task_name, self.business_key)

        if query_data_task is not None:
            detail = QueryDataTaskDetail.model_validate(json.loads(query_data_task.task_detail))
            state.task_name = query_data_task.name
            state.task_id = query_data_task.id
            state.task_detail = detail
            return state
        else:
            return state

    def find_task_in_store(self, state:State):
        """
        去向量存储中查找相近的任务信息
        :param state:
        :return: state
        """
        # 如果没有使用向量存储，则返回
        if not Config.USE_VECTOR_STORE:
            return state

        # 执行相似度搜索
        results = self.vector_store.similarity_search_with_score(
                query=f"{state.task_name}",
                k=1,  # 返回唯一的结果
                return_metadata=True
            )

        for doc, i in results:
            logging.info("向量存储相似度搜索结果：%s, 相似度：%s", doc, i)
            state.task_id = doc.metadata["task_id"]
            state.task_name = doc.metadata["task_name"]
            state.task_detail = QueryDataTaskDetail.model_validate(json.loads(doc.metadata["task_detail"]))
            break

        return state

    async def execute_task(self, state:State):
        """
        调用工具执行任务
        :param state:
        :return: state
        """

        all_messages = state.messages
        # 如果是工具返回后的再次调用
        if isinstance(all_messages[-1], ToolMessage):
            # 使用完整的对话历史作为上下文
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=f"""
                {self.basic_system_template}

                任务ID:{state.task_id}                
                任务详情:
                {state.task_detail}
                
                """),
                *all_messages  # 包含所有历史消息
            ])
            chain = prompt | self.llm.bind_tools(self.execute_with_business_tool_list)
            response = await chain.ainvoke({})
            return {
                "messages": [response],
            }
        else:
            last_human_message = state.messages[-1].content

            # 初次调用，使用原始用户查询
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=f"""
                {self.basic_system_template}
                
                请根据任务详情，执行任务，并返回结果。只需要返回给用户任务详情的介绍，无需返回执行任务的过程。

                任务ID:{state.task_id}
                                
                任务详情:
                {state.task_detail.to_desc()}
                
                注意：每次执行完任务的最后，一定要调用工具，传入任务id，把任务的执行次数加1
                """
                              ),
                HumanMessage(content="{user_input}")  # 用户最后一条消息
            ])

            chain = prompt | self.llm.bind_tools(self.execute_with_business_tool_list)
            response = await chain.ainvoke({"user_input": last_human_message})
            return {
                "messages": [response],
            }

    async def query_data(self, state: State):
        """
        使用llm+业务工具进行对话和数据查询
        :param state:
        :return:state
        """
        all_messages = state.messages

        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=f"{self.basic_system_template}"),
            *all_messages  # 包含所有历史消息
        ])
        chain = prompt | self.llm.bind_tools(self.business_tool_list)
        response = await chain.ainvoke({})

        return {
            "messages": [response],
        }

    def same_name_when_create(self, state:State):
        """
        创建任务时找到同名任务回复给用户
        :param state:
        :return:state
        """
        response = ("ai", f"查找到与【{state.task_name}】同名任务，是否编辑该任务？")
        return {
            "messages": [cast(AIMessage, response)],
        }

    async def edit_task(self, state: State):
        parser = JsonOutputParser(pydantic_object=TaskSchema)

        prompt = ChatPromptTemplate.from_messages([
            ("system", f"""
                       {self.basic_system_template}

                       现在你要解析用户的输入，按JSON格式输出用户给出的模板内容。
                       
                       任务id:{state.task_id}
                       任务名称:{state.task_name}

                       任务模板信息（解释任务信息中的每个字段的含义）:
                       {DEFAULT_TASK_TEMPLATE.to_desc()}
                       
                       当前任务信息:
                       {state.task_detail.to_desc()}

                       **重要说明**: 以下示例仅用于展示从用户输入中提取任务信息并按json格式返回操作，并不是实际对话历史
                       """),
            # 明确标识示例区
            MessagesPlaceholder("examples", optional=True),
            # 包含历史所有对话
            *state.messages
        ])

        examples = [
            ("human", "任务的目标：每日工作效率统计。查询参数为：查询昨天的数据。获取到结果之后的数据加工逻辑：单加一列，工作量除以工作时长为工作效率"),
            ("ai",
             "{\"data_operation\": \"单加一列：工作量除以工作时长为工作效率\",  \"query_param\":\"查询昨天的数据\", \"target\": \"每日工作效率统计\"}"),
        ]

        chain = prompt | self.llm | parser
        response = await chain.ainvoke({
            "examples": examples,
        })

        task_detail = QueryDataTaskDetail.model_validate(response)

        if state.task_detail.to_dict() != task_detail.to_dict():
            state.task_detail = task_detail
        return state


    async def delete_task(self, state:State):
        """
        删除任务
        :param state:
        :return:state
        """
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=f"""
                                   {self.basic_system_template}
                                   你现在要做的事情是删除取数任务
                                   
                                   取数任务的模板如下：
                                   {DEFAULT_TASK_TEMPLATE.to_desc()}
                                   
                                   已有的取数任务如下：
                                   任务id：{state.task_id}
                                   任务名称：{state.task_name}
                                   {state.task_detail.to_desc()}
                                   
                                   具体事项：
                                   1.首先给用户展示任务内容
                                   2.调用工具删除任务
                                   
                                   注意:任务id不要透露给用户
                                   """),
            *state.messages])

        chain = prompt | self.llm.bind_tools(self.delete_task_tool_list)

        response = await chain.ainvoke({})

        return {
            "messages": [response],
        }

    async def create_task(self, state:State):
        """
        解析用户输入中对任务模板的补充
        :param state:
        :return: state
        """
        task_name = state.task_name

        if state.first_time_create:
            state.first_time_create = False
            return state
        else:
            # 后续根据用户提示信息更新模板
            parser = JsonOutputParser(pydantic_object=TaskSchema)

            prompt = ChatPromptTemplate.from_messages([
                ("system", f"""
                {self.basic_system_template}
                
                现在你要解析用户的输入把以下任务模板填写完整
                任务模板如下
                
                任务名称：{task_name}
                {DEFAULT_TASK_TEMPLATE.to_desc()}            
                
                用户给你的输入参考任务模板解析之后，按JSON格式输出用户给出的模板内容。
                **重要说明**: 以下示例仅用于展示维护任务模板的问答逻辑，不是实际对话历史
                """),
                # 明确标识示例区
                MessagesPlaceholder("examples", optional=True),
                # 包含历史所有对话
                *state.messages
            ])

            examples = [
                ("human", "任务的目标：每日工作效率统计。查询参数：查询昨天的数据，数据加工逻辑：单加一列：工作量除以工作时长为工作效率，数据格式：表格"),
                ("ai", "{\"data_operation\": \"单加一列：工作量除以工作时长为工作效率\",  \"query_param\":\"查询昨天的数据\", \"target\": \"每日工作效率统计\", \"data_format\":\"表格\"}"),
            ]

            chain = prompt | self.llm| parser
            response = await chain.ainvoke({
               "examples": examples,
            })

            task_detail = QueryDataTaskDetail.model_validate(response)

            state.task_detail = task_detail

            return state

    #

    def save_task(self, state:State):
        """
        保存任务
        为什么不使用llm调用tool的方式保存？因为是使用resume_stream的方式调用到该节点的，这种方式没法把llm的输出by token返回
        :param state:
        :return: state
        """

        entity = QueryDataTaskEntity(
            name=state.task_name,
            business_key=self.business_key,
            task_detail=json.dumps(state.task_detail.to_dict(), ensure_ascii=False)
        )

        if state.task_id is not None:
            entity.id = state.task_id
            id = self.query_data_task_dao.save(entity)
        else:
            id = self.query_data_task_dao.save(entity)

        # 如果没有使用向量存储，则返回
        if Config.USE_VECTOR_STORE:
            # 存储到向量空间
            self.vector_store.add_texts(texts=[f"任务名称：{state.task_name}\n任务目标：{state.task_detail.target}"], metadatas=[{
                        "task_id": id,
                        "task_name": state.task_name,
                        "task_detail": entity.task_detail
                    }])

        return {
            "task_id": id,
            "query_data_task": True,
            "intent_type": EDIT,
            "messages": [("ai", f"{state.task_name}保存成功")]
        }


    async def test_run_task(self, state:State):
        """
        任务试跑
        :param state:
        :return: state
        """
        all_messages = state.messages

        # 如果是工具返回后的再次调用
        if isinstance(all_messages[-1], ToolMessage):
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=f"""
                {self.basic_system_template}
                你的职责是调用工具执行以下任务：
                
                任务名称：{state.task_name}
                {state.task_detail.to_desc()}
                
                如果你所用到的工具的参数涉及到日期，默认查询当前时间的前一天
                
                只用返回按用户要求进行数据加工之后的结果
                
                """),
                *all_messages  # 包含所有历史消息
            ])

            chain = prompt | self.llm.bind_tools(self.business_tool_list)
            response = await chain.ainvoke({})
        else:
            # 与工具返回后的调用区别在于，这里不传所有历史信息
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=f"""
                           {self.basic_system_template}
                           你的职责是调用工具执行以下任务：

                           任务名称：{state.task_name}
                           {state.task_detail.to_desc()}

                           如果你所用到的工具的参数涉及到日期，默认查询当前时间的前一天

                           只用返回按用户要求进行数据加工之后的结果。

                           """),
            ])
            chain = prompt | self.llm.bind_tools(self.business_tool_list)
            response = await chain.ainvoke({})

        return {
            "messages": [response],
            }


    async def convert_to_standard_format(self, state:State):
        all_messages = state.messages
        last_ai_message = all_messages[-1]

        if state.task_detail.data_format == '表格':
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=f"""
                            你的职责是把给你的文本中的数据转化成标准JSON格式。
                            
                            **重要说明**: 以下示例仅用于展示提取数据转化为标准格式的逻辑，不是实际对话历史
                           """),
                # 明确标识示例区
                MessagesPlaceholder("examples", optional=True),
                last_ai_message
            ])

            examples = [
                AIMessage(f"""今天员工工作情况如下：
                员工工号\t员工工作量
                A1\t1000
                A2\t2000
                
                """),
                AIMessage('{"data_exists":true, "header_list": ["员工工号","员工工作量"],"data_list":[["A1"，"1000"], ["A2","2000"]]}'),
                AIMessage(f"今天员工工作情况没有查到任何数据"),
                AIMessage('{"data_exists":false}'),
            ]

            parser = JsonOutputParser(pydantic_object=TableSchema)
        elif state.task_detail.data_format == '折线图':
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=f"""
                                        你的职责是把给你的文本中的数据转化成标准JSON格式。
                                        请参考下文描述的折线图数据展示方式：
                                        {state.task_detail.data_operation}
                                        
                                        
                                        **注意**:由于是折线图，如果纵轴(y轴)数据为空，则默认设置为0。
                                        **重要说明**: 以下示例仅用于展示提取数据转化为标准格式的逻辑，不是实际对话历史。
                                       """),
                # 明确标识示例区
                MessagesPlaceholder("examples", optional=True),
                last_ai_message
            ])

            examples = [
                SystemMessage(content=f"""
                                        你的职责是把给你的文本中的数据转化成标准JSON格式。
                                        请参考下文描述的折线图数据展示方式：
                                        使用月份作为横轴，效率值作为纵轴                                        
                                        """),
                AIMessage(f"""今天员工工作情况如下：
                            员工工号\t月份\t员工工作量
                            A1\t1月\t1000
                            A2\t2月\t2000
                            A3\t3月\t3000
                            A4\t4月\t4000
                            A5\t5月\t5000
                            """),
                AIMessage('{"data_exists":true, "x_axis": ["1月", "2月", "3月", "4月", "5月"],"y_axis":[1000,2000,3000,4000,5000]，"x_name":"月份", "y_name":"效率值"}'),
                AIMessage(f"今天员工工作情况没有查到任何数据"),
                AIMessage('{"data_exists":false}'),
            ]

            parser = JsonOutputParser(pydantic_object=LineChartSchema)
        else:
            return state

        parser_with_llm = OutputFixingParser.from_llm(parser=parser, llm=self.llm)
        chain = prompt | self.llm | parser_with_llm

        response = await chain.ainvoke({"examples": examples})

        data_exists = response["data_exists"]
        if data_exists:
            return {
                "last_run_msg_id": last_ai_message.id,
                "last_standard_data": json.dumps(response)
            }
        else:
            return state

    async def how_to_improve_task(self, state:State):
        """
        在用户更新任务模板的过程中，对比模板是否填写完善
        :param state:
        :return: state
        """
        if state.task_detail is None or not state.task_detail.is_integrated():
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=f"""
                            {self.basic_system_template}
                            你的职责是对比：
                            任务模板：
                            {DEFAULT_TASK_TEMPLATE.to_desc()}
                            当前任务信息：
                            {"无" if state.task_detail is None else state.task_detail.to_desc()}
                            
                            这两者之间的差别。
                            提示用户模板里还有哪些内容是需要填写的，如果确认用户已经全部填写完成，请询问用户是否进行任务的试算或保存。
                            """),
                *state.messages])

            chain = prompt | self.llm
        else:
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=f"""
                                        {self.basic_system_template}
                                        
                                        以下是用户填写的任务信息                                        
                                        任务名称:{state.task_name}
                                        {state.task_detail.to_desc()}

                                        你的职责是向用户简单、准确的展示任务的名称及任务的详情（而不是真正执行任务）。之后询问用户是否需要补充，或者进行任务的试算或保存
                                        """),
                *state.messages])

            chain = prompt | self.llm

        response = await chain.ainvoke({})

        return {
            "messages": [response],
        }

    # EDGES
    def after_intent_classifier(self, state: State) -> Literal[GraphNode.SAVE_TASK, GraphNode.DEFAULT_NODE, GraphNode.QUERY_DATA_NODE, GraphNode.FIND_TASK_IN_DB]:
        if state.intent_type == DEFAULT:
            return GraphNode.DEFAULT_NODE
        elif state.intent_type == OTHERS:
            return GraphNode.QUERY_DATA_NODE
        elif state.intent_type in [EXECUTE, EDIT, CREATE, DELETE, TEST_RUN]:
            return GraphNode.FIND_TASK_IN_DB
        elif state.intent_type == QUERY_DATA:
            return GraphNode.QUERY_DATA_NODE
        elif state.intent_type == SAVE:
            # 如果要保存任务，必须已经有任务详情
            if state.task_detail is not None and state.task_detail.is_integrated():
                return GraphNode.SAVE_TASK
            else:
                return GraphNode.DEFAULT_NODE
        else:
            return END

    def check_exist_and_next_node(self, state: State) -> Literal[
            GraphNode.FIND_TASK_IN_STORE, GraphNode.SAME_NAME_WHEN_CREATE, GraphNode.CREATE_TASK, GraphNode.EXECUTE_TASK, GraphNode.EDIT_TASK, GraphNode.DELETE_TASK, GraphNode.TEST_RUN_TASK, GraphNode.END]:
        if state.task_detail is None:
            if state.intent_type == CREATE:
                return GraphNode.CREATE_TASK
            else:
                return GraphNode.FIND_TASK_IN_STORE
        else:
            if state.intent_type == CREATE:
                return GraphNode.SAME_NAME_WHEN_CREATE
            elif state.intent_type == EXECUTE:
                return GraphNode.EXECUTE_TASK
            elif state.intent_type == TEST_RUN:
                return GraphNode.TEST_RUN_TASK
            elif state.intent_type == EDIT:
                return GraphNode.EDIT_TASK
            elif state.intent_type == DELETE:
                return GraphNode.DELETE_TASK
            else:
                return END

    def check_exist_in_store_and_next_node(self, state: State) -> Literal[GraphNode.CREATE_TASK, GraphNode.SAME_NAME_WHEN_CREATE, GraphNode.EXECUTE_TASK, GraphNode.EDIT_TASK, GraphNode.DELETE_TASK, GraphNode.END]:
        if state.task_detail is not None:
            if state.intent_type == CREATE:
                return GraphNode.CREATE_TASK
            elif state.intent_type == EXECUTE:
                return GraphNode.CREATE_TASK
            elif state.intent_type == EDIT:
                return GraphNode.CREATE_TASK
            elif state.intent_type == DELETE:
                return GraphNode.CREATE_TASK
            else:
                return END
        else:
            if state.intent_type == CREATE:
                return GraphNode.SAME_NAME_WHEN_CREATE
            elif state.intent_type == EXECUTE:
                return GraphNode.EXECUTE_TASK
            elif state.intent_type == EDIT:
                return GraphNode.EDIT_TASK
            elif state.intent_type == DELETE:
                return GraphNode.DELETE_TASK
            else:
                return END



    def need_invoke_tool(self, state: State) -> Literal[GraphNode.TOOLS_FOR_TASK, GraphNode.TOOLS_FOR_QUERY_DATA, GraphNode.CONVERT_TO_STANDARD_FORMAT, GraphNode.END]:
        last_message = state.messages[-1]
        if not isinstance(last_message, AIMessage):
            raise ValueError(
                f"Expected AIMessage in output edges, but got {type(last_message).__name__}"
            )

        if not last_message.tool_calls:
            # 如果任务已经执行完毕，再次循环到试跑/保存的中断
            if state.intent_type in [TEST_RUN, EXECUTE]:
                return GraphNode.CONVERT_TO_STANDARD_FORMAT
            else:
                return END
        elif state.intent_type == EXECUTE:
            return GraphNode.TOOLS_FOR_TASK
        elif state.intent_type == QUERY_DATA or state.intent_type == OTHERS:
            return GraphNode.TOOLS_FOR_QUERY_DATA
        elif state.intent_type == TEST_RUN:
            return GraphNode.TOOLS_FOR_TASK
        else:
            return END

    def after_invoke_tool(self, state: State) -> Literal[GraphNode.EXECUTE_TASK, GraphNode.TEST_RUN_TASK, GraphNode.END]:
        if state.intent_type == EXECUTE:
            return GraphNode.EXECUTE_TASK
        elif state.intent_type == TEST_RUN:
            return GraphNode.TEST_RUN_TASK
        else:
            return END


    def need_invoke_delete_task_tool(self, state: State) -> Literal[GraphNode.TOOLS_FOR_DELETE_TASK, GraphNode.END]:
        last_message = state.messages[-1]
        if not isinstance(last_message, AIMessage):
            raise ValueError(
                f"Expected AIMessage in output edges, but got {type(last_message).__name__}"
            )

        if not last_message.tool_calls:
            return END
        else:
            return GraphNode.TOOLS_FOR_DELETE_TASK

    @tool
    def logical_delete_task(self, id: int, task_name, business_key: str):
        """
           删除任务信息，结果返回是否删除成功

           输入参数：
           id：任务唯一id
           task_name：任务名称
           business_key：业务键
       """
        self.query_data_task_dao.delete(id, business_key)

        # 如果没有使用向量存储，则返回
        if Config.USE_VECTOR_STORE:
            self.vector_store.delete(filter={"task_id": id, "task_name": task_name})

        return True


    def get_frequently_and_usually_execute_tasks(self) -> set[str]:
        """
        获取最频繁/最近执行过的任务名称
        :return:任务名称列表
        """
        usually_execute_tasks = self.query_data_task_dao.get_usually_execute_top3_tasks(self.business_key)

        names = set()
        not_in_ids = []
        for t in usually_execute_tasks:
            names.add(t.name)
            not_in_ids.append(t.id)

        frequently_execute_tasks = self.query_data_task_dao.get_frequently_execute_top3_tasks(self.business_key, not_in_ids)

        for t in frequently_execute_tasks:
            names.add(t.name)

        return names

    def get_event_stream_function(self, input: str | None, session_id, stream_type: Literal["question", "resume"]):
        """
        获取流式方法，这个方法直接返回给前端使用
        :param input:
        :param session_id:
        :param stream_type; 是提问还是中断的回复
        :return: event_stream
        """

        @stream_with_context
        async def async_event_stream():
            try:
                # 根据不同的流类型获取对应的流
                if stream_type == "question":
                    stream = self.stream_question(input, session_id)
                elif stream_type == "resume":
                    stream = self.stream_resume(input, session_id)
                else:
                    stream = self.default(session_id)

                # 直接异步迭代处理流数据
                async for stream_mode, detail in stream:
                    # print(stream_mode, detail)
                    if stream_mode == "messages":
                        chunk, metadata = detail
                        if metadata['langgraph_node'] in AI_CHAT_NODES:
                            content = chunk.content
                            yield f"data: {json.dumps({'msgId': chunk.id, 'token': content})}\n\n"
                    elif stream_mode == "tasks":
                        if "interrupts" in detail and len(detail["interrupts"]) > 0:
                            yield f"data: {json.dumps({'interrupt': convert_2_interrupt(detail['interrupts'][0]).to_json()})}\n\n"
                        elif detail["name"] in AI_MSG_NODES:
                            content = get_tasks_mode_ai_msg_content(detail)
                            if content is not None:
                                yield f"data: {json.dumps({'msgId': detail['id'], 'token': content})}\n\n"
                # print("ready to done")
                yield "event: done\ndata: \n\n"

            except Exception as e:
                logging.error(f"Stream processing error: {e}")
                yield f"event: error\ndata: {str(e)}\n\n"
                yield "event: done\ndata: \n\n"

        return async_event_stream



    def get_state_properties(self, session_id, state_property_names):
        """
        根据session_id获取当前任务是否在新增/编辑中，且任务是否维护完善

        Parameters:
            session_id: str sessionId
            state_property_names: state中的属性名，逗号分割

        Returns:
            是否维护完善
        """
        # 上下文配置
        config = RunnableConfig(
            configurable={"thread_id": session_id},
        )

        state = self.graph.get_state(config=config)

        state_data = {}
        for property in state_property_names.split(","):
            if property == "is_integrated":
                task_detail = state.values["task_detail"]
                if task_detail is not None and task_detail.is_integrated():
                    state_data[property] = True
                else:
                    state_data[property] = False
            else:
                if property in state.values:
                    state_data[property] = state.values[property]
        return state_data

    def find_task_by_id_or_name(self, task_id: int, task_name: str | None, business_key: str) -> QueryDataTaskEntity:
        """
        根据按优先级根据task_id,task_name查询db中的任务对象
        :param task_id:
        :param task_name:
        :param business_key:业务键
        :return: 任务对象
        """
        if task_id is not None:
            entity = self.query_data_task_dao.find_by_id(task_id)
        elif task_name is not None:
            entity = self.query_data_task_dao.find_by_name(business_key, task_name)
        else:
            entity = None

        return entity

    @tool
    def execute_once(self, id: int, business_key: str):
        """
              当执行任务时，把执行任务的次数+1

              输入参数：
              id：任务唯一id
              business_key：业务键
          """
        self.query_data_task_dao.update_execute_times_once(id, business_key)

    def get_agent_def(self, business_key) -> AgentDefEntity | None:
        return self.agent_def_dao.find_by_business_key_and_type(business_key, AgentDefType.DATA_ANALYST)

    def get_business_tool_list(self, agent_def: AgentDefEntity):
        llm_tool_list: list[LLMToolEntity] = self.llm_tool_dao.get_llm_tools_by_agent_id(agent_def.id)

        tools = []
        # 处理http tool
        for tool in llm_tool_list:
            if tool.tool_type == LLMToolType.HTTP_TOOL:
                t = create_llm_http_tool(tool)
                tools.append(t)

        # 处理mcp tool
        mcp_tool_list = []
        for tool in llm_tool_list:
            if tool.tool_type == LLMToolType.MCP:
                mcp_tool_list.append(tool)

        mcp_tool_list = asyncio.run(create_mcp_client_tools(mcp_tool_list))
        tools = tools + mcp_tool_list

        return tools






def get_tasks_mode_ai_msg_content(detail) -> str | None:
    """
    解析返回结构里强行解析消息内容（没想到更好的办法）
    :param detail:
    :return:
    """
    if "result" in detail:
        result_dict = dict(detail["result"])
        msgs = result_dict["messages"]
        for m in msgs:
            msg_dict = dict(m)
            if "ai" in msg_dict:
                return msg_dict["di"]
    return None


def create_service(service_name, business_key) -> DataAnalystService:
    """
    创建并缓存service
    :param service_name: 工作流名称
    :param business_key: 业务键
    :return: service
    """
    data_analyst_service = DataAnalystService(service_name, business_key)
    service_map[business_key] = data_analyst_service
    return data_analyst_service

def get_service(business_key) -> DataAnalystService | None:
    """
    根据业务键从缓存中获取工作流实例
    :param business_key:
    :return:工作流实例
    """
    if business_key not in service_map:
        return None
    else:
        data_analyst_service = service_map[business_key]
        return data_analyst_service

def convert_2_interrupt(interrupt: Interrupt|dict) -> WorkflowInterrupt:
    """
    从原始中断信息转化成业务中断信息
    :param interrupt:
    :return:业务中断信息
    """
    if isinstance(interrupt, dict):
        value = interrupt["value"]
    else:
        value = interrupt.value

    args: dict = value["action_request"]["args"]

    workflow_interrupt = WorkflowInterrupt(
        action=value["action_request"]["action"],
        description=value["description"],
        confirm_option_list=args["confirm_option_list"],
        task_name=args["task_name"],
    )

    return workflow_interrupt

def get_real_url(tool_input: dict[str, Any], url: str) -> str:
    real_url = url.format(**tool_input)
    return real_url





def add_human_in_the_loop(
    tool: Callable | BaseTool,
    confirm_option_list:List[WorkflowResume],
    tool_input_2_desc: Callable[[{}], str],
    interrupt_config: HumanInterruptConfig = None,
) -> BaseTool:
    """
    可把中断统一加入到工具中的
    :param tool: 工具
    :param confirm_option_list: 中断之后的选项
    :param tool_input_2_desc: 生成中断的提问语句
    :param interrupt_config: 中断配置（默认为DEFAULT_INTERRUPT_CONFIG）
    :return: 包含中断的工具
    """
    if not isinstance(tool, BaseTool):
        tool = create_tool(tool)

    if interrupt_config is None:
        interrupt_config = DEFAULT_INTERRUPT_CONFIG

    @create_tool(
        tool.name,
        description=tool.description,
        args_schema=tool.args_schema
    )
    def call_tool_with_interrupt(config: RunnableConfig, **tool_input):
        start = int(time.time())
        print(f"call_tool_with_interrupt从：{start}开始执行")
        args = {**tool_input, "confirm_option_list": confirm_option_list}

        request: HumanInterrupt = {
            "action_request": {
                "action": tool.name,
                "args": args,
            },
            "config": interrupt_config,
            "description": tool_input_2_desc(tool_input)
        }
        response = interrupt(request)[0]

        if response["resumeType"] == "accept":
            tool_response = tool.invoke(tool_input, config)
        elif response["resumeType"] == "cancel":
            tool_response = "取消调用"
        else:
            raise ValueError(f"Unsupported interrupt response type: {response['type']}")

        return tool_response

    return call_tool_with_interrupt

def get_or_create_data_analyst_service(business_key) -> DataAnalystService:
    data_analyst_service = get_service(business_key)
    if data_analyst_service is None:
        data_analyst_service = create_service(business_key, business_key)
    return data_analyst_service