# Initialize memory
import json
import logging
import os
import queue
import tempfile
import threading
from datetime import datetime
from enum import StrEnum
from typing import Optional, Type, cast, Literal

from dotenv import load_dotenv
from langchain.retrievers import MultiQueryRetriever
from langchain_community.document_loaders import UnstructuredMarkdownLoader
from langchain_core.callbacks import CallbackManagerForToolRun
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool
from langchain_deepseek import ChatDeepSeek
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_redis import RedisVectorStore, RedisConfig
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.redis import RedisSaver
from langgraph.constants import START, END
from langgraph.graph.state import CompiledStateGraph, StateGraph
from langgraph.prebuilt import ToolNode
from mem0 import MemoryClient, Memory
from memori import Memori, create_memory_tool, MemoryTool, ConfigManager
from memori.core.providers import ProviderConfig
from pydantic import BaseModel, Field
from quart import stream_with_context
from werkzeug.utils import secure_filename

from config import Config
from container import dao_container
from dao.agent_def_dao import AgentDefDAO
from entity.agent_def_entity import AgentDefType
from service.agent.data_analyst_service import get_service
from service.agent.model.assistant_state import AssistantState
from service.agent.model.state import InputState
from service.agent.prompt import prompts
from util import datetime_util
from util.config_util import read_private_config


service_map = {}

AI_CHAT_NODES = ["chat"]


class AssistantService:
    # 工作流服务的业务唯一键，同一个business_key下的取数任务名称唯一
    business_key: str
    # 工作流服务默认的系统提示词，包含所有基础业务信息
    basic_system_template: str
    # RAG专用向量存储
    vector_store:RedisVectorStore
    # langGraph实例
    graph: CompiledStateGraph
    # 记忆(mem0)
    memory: Memory

    agent_def_dao:AgentDefDAO


    def __init__(self, business_key):
        self.business_key = business_key

        self.agent_def_dao = dao_container.agent_def_dao()
        agent_def = self.agent_def_dao.find_by_business_key_and_type(business_key, AgentDefType.ASSISTANT)

        if agent_def is None:
            raise Exception("未找到对应的agent定义")

        self.basic_system_template = agent_def.system_prompt

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

        self.reasoner_llm = ChatDeepSeek(
            model=Config.REASONER_LLM_MODEL,
            temperature=0,
            max_tokens=None,
            timeout=None,
            max_retries=2,
            api_key=api_key
        )

        # 初始化记忆(mem0)
        self.memory = self.create_memory()
        # 初始化langGraph
        self.graph = self.create_graph(agent_def.name)
        # 创建rag专用向量存储
        self.vector_store = self.create_vector_store()
        # 创建数据员子图调用工具
        self.data_analyst_tool = [ask_data_analyst]



    def get_event_stream_function(self, input: str | None, session_id):
        """
        获取流式方法，这个方法直接返回给前端使用
        :param input:
        :param session_id:
        :return: event_stream
        """

        @stream_with_context
        async def async_event_stream():
            try:

                stream = self.stream_question(input, session_id)

                # 直接异步迭代处理流数据
                async for stream_mode, detail in stream:

                    if stream_mode == "messages":
                        chunk, metadata = detail
                        if metadata['langgraph_node'] in AI_CHAT_NODES:
                            content = chunk.content
                            yield f"data: {json.dumps({'msgId': chunk.id, 'token': content})}\n\n"
                yield "event: done\ndata: \n\n"

            except Exception as e:
                logging.error(f"Stream processing error: {e}")
                yield f"event: error\ndata: {str(e)}\n\n"
                yield "event: done\ndata: \n\n"

        return async_event_stream

    async def stream_question(self, query, session_id):
        """
        流式触发graph
        :param query: 用户提问信息
        :param session_id: 用来做state的隔离
        :return:stream
        """
        # 上下文配置
        config = RunnableConfig(
            configurable={"thread_id": session_id},
        )

        stream = self.graph.astream(
            input=InputState(messages=[("user", query)]),
            config=config,
            stream_mode=["messages"]
        )

        return stream

    def get_all_tasks(self, state: AssistantState):
        """
        获取所有的任务
        :return:state
        """
        tasks = self.agent_def_dao.get_all_tasks(self.business_key)

        return {
            "tasks": tasks,
        }

    def get_doc_content_from_vector(self, state:AssistantState):
        human_msg: HumanMessage = cast(HumanMessage, state.messages[-1])

        search_kwargs = {
            "score_threshold": Config.ASSISTANT_RAG_SCORE_THRESHOLD,
            "k": Config.ASSISTANT_RAG_TOP_K,
        }

        retriever_from_llm = MultiQueryRetriever.from_llm(
            retriever=self.vector_store.as_retriever(search_kwargs=search_kwargs), llm=self.llm
        )
        docs = retriever_from_llm.invoke(human_msg.content)

        return {
            "rag_docs": docs,
        }

    def get_memories(self, state: AssistantState):
        human_msg: HumanMessage = cast(HumanMessage, state.messages[-1])

        memories = self.memory.search(human_msg.content, user_id=self.business_key)
        memory_list = memories['results']

        memory_content = ""
        for memory in memory_list:
            memory_content += f"- {memory['memory']}\n"

        return {
            "memory_content": memory_content,
        }


    def reason(self, state: AssistantState):
        """
        使用llm进行推理
        :param state:
        :return:state
        """
        # 1.basic提示词
        basic_system_prompt = self.basic_system_template

        # 2.推理专用提示词
        reason_prompt_context = prompts.get_assistant_system_prompt()

        # 3.知识库提示词
        knowledge_prompt_context = "\n查询知识库搜索到相关信息如下:\b"
        knowledge_prompt_context += state.rag_docs

        # 4.记忆提示词
        memory_context = "\n从历史对话中获取到的相关信息如下:\n"
        memory_context += state.memory_content

        # 5.所有任务信息
        task_context = "\n你能使用的所有任务信息如下:\n"
        task_context += "\n".join([task.to_desc() for task in state.tasks]) + "\n"

        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="\n".join([basic_system_prompt, reason_prompt_context, knowledge_prompt_context, memory_context, task_context])),
            state.messages,
        ])
        chain = prompt | self.reasoner_llm
        response = chain.invoke({})

        return {
            "reasoning_context": response.content,
        }


    def chat(self, state: AssistantState):
        """
        使用llm进行对话(并查找过往记忆)
        :param state:
        :return:state
        """
        human_msg: HumanMessage = cast(HumanMessage, state.messages[-1])

        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=f"""
            {self.basic_system_template}
            
            你需要执行的操作是:
            {state.reasoning_context}
            """),
            state.messages,
        ])
        chain = prompt | self.llm.bind_tools(self.data_analyst_tool)
        response = chain.invoke({})

        if response.tool_calls is None or len(response.tool_calls) == 0:
            response_content = response.content
            if response_content != "" :
                # Store the interaction in Mem0
                try:
                    interaction = [
                        {
                            "role": "user",
                            "content": human_msg.content,
                        },
                        {
                            "role": "assistant",
                            "content": response.content
                        }
                    ]
                    result = self.memory.add(interaction, user_id=self.business_key)

                    print(f"Memory saved: {len(result.get('results', []))} memories added")
                except Exception as e:
                    print(f"Error saving memory: {e}")

        #todo 生成长期记忆

        return {
            "messages": [response],
        }


    def create_memory(self):
        """
        创建mem0组件的agent记忆
        """
        load_dotenv()

        # 读取本地模型
        model_location: Optional[str] = read_private_config("embedding_models", "LOCATION")
        if model_location is None:
            model_location = Config.EMBEDDING_LOCAL_MODEL

        model_name = model_location
        model_kwargs = {"device": "cpu"}
        # todo 是否需要添加归一化配置，没找到哪里可配
        # config_kwargs = {"normalize_embeddings": True}

        config = {
            "vector_store": {
                "provider": "redis",
                "config": {
                    "collection_name": "mem0_" + self.business_key,
                    "redis_url": "redis://localhost:6379",
                     "embedding_model_dims": 512,
                }
            },
            "llm": {
                "provider": "langchain",
                "config": {
                    "model": self.llm,
                }
            },
            "embedder": {
                "provider": "huggingface",
                "config": {
                    "model": model_name,
                    "model_kwargs": model_kwargs,
                }
            },
            "version": "v1.1"
        }

        memory = Memory.from_config(config)

        return memory

    def create_vector_store(self) -> RedisVectorStore:
        """
        创建RAG专用向量存储
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
                index_name="assistant_" + self.business_key,
                redis_url=Config.REDIS_URL,
                metadata_schema=[
                    {"name": "source", "type": "tag"},
                    {"name": "upload_time", "type": "tag"},
                ],
            )

            vectorstore = RedisVectorStore(embeddings, config=config)

            return vectorstore
        except Exception as e:
            logging.error("创建向量存储连接失败:", e)
            return None

    def create_graph(self, graph_name):
        builder = StateGraph(AssistantState, input_schema=AssistantState)
        builder.add_node(self.get_all_tasks)
        builder.add_node(self.get_doc_content_from_vector)
        builder.add_node(self.get_memories)
        builder.add_node(self.chat)
        builder.add_node(self.reason)

        builder.add_edge(START, self.get_all_tasks.__name__)
        builder.add_edge(self.get_all_tasks.__name__, self.get_doc_content_from_vector.__name__)
        builder.add_edge(self.get_doc_content_from_vector.__name__, self.get_memories.__name__)
        builder.add_edge("reason", "chat")
        builder.add_edge("chat", END)

        # 记忆功能
        if Config.MEMORY_USE == "local":
            memory = InMemorySaver()
        else:
            memory = RedisSaver(Config.REDIS_URL)
            # 第一次执行时初始化redis
            # memory.setup()
        graph = builder.compile(name=graph_name, checkpointer=memory)
        # # 生成PNG流程图
        # try:
        #     png_data = graph.get_graph().draw_mermaid_png()
        #     # 保存到文件
        #     with open("/tmp/langgraph_assistant_diagram.png", "wb") as png_file:
        #         png_file.write(png_data)
        #     logging.info("流程图已保存为 /tmp/workflow_diagram.png")
        # except Exception as e:
        #     logging.exception("Failed to generate PNG workflow diagram", e)

        return graph

    def ask(self, question, session_id):
        """
        同步返回提问的回答（仅用来测试）
        :param question: 用户提问信息
        :param session_id: 用来做state的隔离
        :return: 回答内容
        """
        # 上下文配置
        config = RunnableConfig(
            configurable={"thread_id": session_id},
        )

        res = self.graph.invoke(
            input=AssistantState(messages=[("user", question)]),
            config=config,
        )

        result = res["messages"][-1]
        content = str(result.content)

        if content == "":
            print("content is empty:", result)

        return content

@tool
def ask_data_analyst(business_key, session_id, task_name):
    """
    根据业务键和任务名，执行任务并返回任务结果

    输入参数：
    business_key：业务键
    session_id：会话id
    task_name：任务名
    """
    data_analyst_service = get_service(business_key)
    content = data_analyst_service.question(f"执行任务:{task_name}", session_id)

    return content


def get_or_create_assistant_service(business_key) -> AssistantService:
    service = get_assistant_service(business_key)
    if service is None:
        service = create_assistant_service(business_key)
    return service


def create_assistant_service(business_key) -> AssistantService:
    service_map[business_key] = service

    return service

def get_assistant_service(business_key):
    if business_key in service_map:
        return service_map[business_key]
    else:
        return None
