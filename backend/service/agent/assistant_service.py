# Initialize memory
import json
import logging
import os
import queue
import tempfile
import threading
from datetime import datetime
from typing import Optional, Type, cast, Literal

from langchain.retrievers import MultiQueryRetriever
from langchain_community.document_loaders import UnstructuredMarkdownLoader
from langchain_core.callbacks import CallbackManagerForToolRun
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langchain_deepseek import ChatDeepSeek
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_redis import RedisVectorStore, RedisConfig
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.redis import RedisSaver
from langgraph.constants import START, END
from langgraph.graph.state import CompiledStateGraph, StateGraph
from langgraph.prebuilt import ToolNode
from memori import Memori, create_memory_tool, MemoryTool, ConfigManager
from memori.core.providers import ProviderConfig
from pydantic import BaseModel, Field
from werkzeug.utils import secure_filename

import container
from config import Config
from dao.agent_def_dao import AgentDefDAO
from entity.agent_def_entity import AgentDefType
from service.agent.model.assistant_state import AssistantState
from service.agent.model.state import InputState
from util import datetime_util
from util.config_util import read_private_config


service_map = {}

class AssistantGraphNode:
    CHAT = "chat"
    TOOL_SEARCH_FOR_MEMORI = "tool_search_for_memori"
    QUERY_FROM_VECTOR_STORE = "query_from_vector_store"
    QUERY_FROM_MEMORI = "query_from_memori"
    CHAT_AFTER_VECTOR_AND_MEMORI = "chat_after_vector_and_memori"

AI_CHAT_NODES = [AssistantGraphNode.CHAT_AFTER_VECTOR_AND_MEMORI]


class MemorySearchInput(BaseModel):
    """Input for the memory search tool."""

    query: str = Field(
        description="在记忆中搜索什么（例如，“过去关于AI的对话”、“用户偏好”）"
    )

class MemorySearchTool(BaseTool):
    """LangChain tool for searching agent memory."""

    name: str = "search_memory"
    description: str = (
        "在AI的记忆中搜索过去的对话和信息。使用此功能可回忆之前的互动、用户偏好和上下文。"
    )
    args_schema: Type[BaseModel] = MemorySearchInput

    memory_tool: MemoryTool

    def _run(
            self,
            query: str,
            run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        """Use the tool to search memory."""
        try:
            if not query.strip():
                return "Please provide a search query"

            result = self.memory_tool.execute(query=query.strip())
            return str(result) if result else "No relevant memories found"

        except Exception as e:
            return f"Memory search error: {str(e)}"

class AssistantService:
    # 工作流服务的业务唯一键，同一个business_key下的取数任务名称唯一
    business_key: str
    # 工作流服务默认的系统提示词，包含所有基础业务信息
    basic_system_template: str
    # langGraph实例
    graph: CompiledStateGraph
    # 向量存储
    vector_store: RedisVectorStore

    def __init__(self, workflow_name, business_key: str, basic_system_template:str):
        self.business_key = business_key
        self.basic_system_template = basic_system_template


        # 初始化大模型
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_API_KEY"] = read_private_config("langsmith", "LANGSMITH_API_KEY")
        os.environ["LANGSMITH_PROJECT"] = read_private_config("langsmith", "LANGSMITH_PROJECT")

        # 初始化llm
        api_key: Optional[str] = read_private_config("deepseek", "API_KEY")
        self.llm = ChatDeepSeek(
            model="deepseek-chat",
            temperature=0,
            max_tokens=None,
            timeout=None,
            max_retries=2,
            api_key=api_key
        )
        # 初始化memori
        self.memori = self.create_memori(api_key)

        # 初始化memory_tool
        memory_tool = create_memory_tool(self.memori)
        memory_tool._search_engine = self.memori.search_engine
        self.memory_tool = memory_tool
        self.memory_search_tool = MemorySearchTool(memory_tool=memory_tool)

        # 初始化langGraph
        self.graph = self.create_graph(workflow_name)
        if Config.USE_VECTOR_STORE:
            self.vector_store = self.create_vector_store()

    def get_event_stream_function(self, input: str | None, session_id):
        """
        获取流式方法，这个方法直接返回给前端使用
        :param input:
        :param session_id:
        :return: event_stream
        """

        def event_stream():

            # 为每个请求创建专用队列
            data_queue = queue.Queue()

            def run_workflow():
                try:
                    stream = self.stream_question(input, session_id)


                    for stream_mode, detail in stream:
                        if stream_mode == "messages":
                            chunk, metadata = detail
                            if metadata['langgraph_node'] in AI_CHAT_NODES:
                                # print("question", stream_mode, detail)
                                content = chunk.content
                                data_queue.put({"msgId": chunk.id, "token": content})
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

        return event_stream

    def stream_question(self, query, session_id):
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

        stream = self.graph.stream(
            input=InputState(messages=[("user", query)]),
            config=config,
            stream_mode=["messages"]
        )

        return stream

    def find_last_human_message(self, messages) -> (int, BaseMessage):
        """
        从后往前查找最后一条HumanMessage
        """
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], HumanMessage):
                return i, messages[i]
        return -1, None


    def query_from_vector_store(self, state:AssistantState):
        all_messages = state.messages
        question = all_messages[-1].content

        search_kwargs = {
            "score_threshold": Config.ASSISTANT_RAG_SCORE_THRESHOLD,
            "k": Config.ASSISTANT_RAG_TOP_K,
        }

        retriever_from_llm = MultiQueryRetriever.from_llm(
            retriever=self.vector_store.as_retriever(search_kwargs = search_kwargs), llm=self.llm
        )

        docs = retriever_from_llm.invoke(question)

        return {
            "rag_docs": docs
        }


    def query_from_memori(self, state: AssistantState):
        all_messages = state.messages
        query = all_messages[-1].content

        result = self.memory_tool.execute(query=query.strip())
        memori_content = str(result) if result else "No relevant memories found"

        return {
            "memori_content": memori_content
        }

    def chat_after_vector_and_memori(self, state: AssistantState):
        all_messages = state.messages
        human_msg: HumanMessage = cast(HumanMessage, state.messages[-1])

        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=f"{self.basic_system_template}"),
            *all_messages,
        ])
        chain = prompt | self.llm
        response = chain.invoke({})

        response_content = response.content
        if response_content != "":
            self.memori.record_conversation(
                user_input=human_msg.content, ai_output=response_content
            )
        return {
            "messages": [response],
        }




    def chat(self, state: AssistantState):
        """
        使用llm进行对话(并查找过往记忆)
        :param state:
        :return:state
        """
        all_messages = state.messages
        if isinstance(all_messages[-1], ToolMessage):
            index, human_msg = self.find_last_human_message(all_messages)
            # 使用从找到的HumanMessage开始到最新的所有消息
            messages_to_use = all_messages[index:] if index != -1 else all_messages

            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=f"{self.basic_system_template}"),
                *messages_to_use,
            ])
            chain = prompt | self.llm.bind_tools([self.memory_search_tool])
            response = chain.invoke({})

            if human_msg is not None:
                self.memori.record_conversation(
                    user_input=human_msg.content, ai_output=response.content
                )

            return {
                "messages": [response],
            }
        else:
            human_msg:HumanMessage = cast(HumanMessage, state.messages[-1])

            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=f"{self.basic_system_template}"),
                human_msg, # 最后一条是用户信息
            ])
            chain = prompt | self.llm.bind_tools([self.memory_search_tool])
            response = chain.invoke({})

            if response.tool_calls is None or len(response.tool_calls) == 0:
                response_content = response.content
                if response_content != "" :
                    self.memori.record_conversation(
                        user_input=human_msg.content, ai_output=response_content
                    )
            return {
                "messages": [response],
            }

    def need_search_for_memori(self, state: AssistantState) -> Literal[AssistantGraphNode.TOOL_SEARCH_FOR_MEMORI, END]:
        last_message = state.messages[-1]
        if not isinstance(last_message, AIMessage):
            raise ValueError(
                f"Expected AIMessage in output edges, but got {type(last_message).__name__}"
            )

        if not last_message.tool_calls:
            return END
        else:
            return AssistantGraphNode.TOOL_SEARCH_FOR_MEMORI

    def create_memori(self, api_key):
        llm_provider = ProviderConfig.from_custom(
            base_url="https://api.deepseek.com",
            api_key=api_key,
            model = Config.LLM_MODEL,
        )
        config = ConfigManager()
        # config.auto_load()  # Loads memori.json automatically
        config.update_setting("logging.level", "DEBUG")

        memori = Memori(
            database_connect=Config.MYSQL_DATABASE,
            conscious_ingest=True,
            auto_ingest=True,
            api_key=read_private_config("deepseek", "API_KEY"),
            namespace="assistant_" + self.business_key,
            schema_init=False, # 第一次执行设置为True，为了自动创建表结构
            provider_config = llm_provider,
            # verbose=True,
        )
        memori.enable()

        return memori

    def create_graph(self, graph_name):
        builder = StateGraph(AssistantState, input_schema=AssistantState)
        builder.add_node(AssistantGraphNode.QUERY_FROM_VECTOR_STORE, self.query_from_vector_store)
        builder.add_node(AssistantGraphNode.QUERY_FROM_MEMORI, self.query_from_memori)
        builder.add_node(AssistantGraphNode.CHAT_AFTER_VECTOR_AND_MEMORI, self.chat_after_vector_and_memori)

        builder.add_edge(START, AssistantGraphNode.QUERY_FROM_VECTOR_STORE)
        builder.add_edge(AssistantGraphNode.QUERY_FROM_VECTOR_STORE, AssistantGraphNode.QUERY_FROM_MEMORI)
        builder.add_edge(AssistantGraphNode.QUERY_FROM_MEMORI, AssistantGraphNode.CHAT_AFTER_VECTOR_AND_MEMORI)
        builder.add_edge(AssistantGraphNode.CHAT_AFTER_VECTOR_AND_MEMORI, END)

        # 记忆功能
        if Config.MESSAGE_MEMORY_USE == "local":
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

    # 先只支持md
    ALLOWED_EXTENSIONS = {'md', 'markdown', 'txt'}

    def allowed_file(self, filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in self.ALLOWED_EXTENSIONS

    def upload_file(self, file):
        # 获取文件内容
        if file and self.allowed_file(file.filename):
            # 安全处理文件名
            filename = secure_filename(file.filename)

            # 创建临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix='.md') as temp_file:
                file.save(temp_file.name)
                logging.info(f"文件保存成功, {temp_file.name}")

                # 处理Markdown文件
                id = self.process_single_file(temp_file.name, filename)

                print(id)

                # 清理临时文件
                os.unlink(temp_file.name)

    def add_metadata(self, doc, filename, time_str):
        doc.metadata['source'] = filename
        doc.metadata['upload_time'] = time_str
        return doc.metadata

    def process_single_file(self, file_path, filename):
        """处理单个Markdown文件"""
        try:
            # 1. 加载Markdown文件
            loader = UnstructuredMarkdownLoader(file_path)
            documents = loader.load()

            # 2. 第一层文本分割
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=Config.MD_DOC_VECTOR_CHUNK_SIZE,
                chunk_overlap=Config.MD_DOC_VECTOR_CHUNK_OVERLAP,
                separators=Config.MD_DOC_VECTOR_SEPARATORS
            )
            splits = text_splitter.split_documents(documents)

            now_str = datetime_util.format_datatime(datetime.now())
            ids = self.vector_store.add_texts(texts=[doc.page_content for doc in splits], metadatas=[self.add_metadata(doc, filename, now_str) for doc in splits])
            logging.info("添加知识库文档到向量存储完成:%s", ids)
        except Exception as e:
            logging.error(f"处理Markdown文件失败: {str(e)}")
            raise e


def get_or_create_assistant_service(business_key) -> AssistantService:
    service = get_assistant_service(business_key)
    if service is None:
        service = create_assistant_service(business_key)
    return service


def create_assistant_service(business_key) -> AssistantService:
    agent_def_dao = container.dao_container.agent_def_dao()
    agent_def = agent_def_dao.find_by_business_key_and_type(business_key, AgentDefType.ASSISTANT)

    if agent_def is None:
        raise Exception("未找到对应的agent定义")

    service = AssistantService(agent_def.name, business_key, agent_def.system_prompt)
    service_map[business_key] = service

    return service

def get_assistant_service(business_key):
    if business_key in service_map:
        return service_map[business_key]
    else:
        return None



