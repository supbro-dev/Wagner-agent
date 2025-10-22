# Initialize memory
import json
import logging
import os
import tempfile
from datetime import datetime
from typing import Optional, cast, Literal

from dotenv import load_dotenv
from langchain.retrievers import MultiQueryRetriever
from langchain_community.document_loaders import UnstructuredMarkdownLoader
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_deepseek import ChatDeepSeek
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_redis import RedisVectorStore, RedisConfig
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.redis import RedisSaver
from langgraph.constants import START, END
from langgraph.graph.state import CompiledStateGraph, StateGraph
from langgraph.prebuilt import ToolNode
from mem0 import Memory
from mem0.configs.enums import MemoryType
from quart import stream_with_context
from werkzeug.utils import secure_filename

from config import Config
from container import dao_container
from dao.agent_def_dao import AgentDefDAO
from dao.query_data_task_dao import QueryDataTaskDAO
from dao.rag_file_dao import RagFileDAO
from entity.agent_def_entity import AgentDefType
from entity.rag_file_entity import RagFileEntity
from model.query_data_task_detail import QueryDataTaskDetail
from service.agent.data_analyst_service import get_or_create_data_analyst_service
from service.agent.model.assistant_output_schema import DEFAULT, QUERY_DATA, IntentSchema
from service.agent.model.assistant_state import AssistantState
from service.agent.model.state import InputState
from service.agent.prompt import prompts
from service.agent.prompt.prompts import ASSISTANT_EXTRACT_QUERYING_DATA_PROMPT
from util import datetime_util
from util.config_util import read_private_config

service_map = {}

AI_CHAT_NODES = ["chat", "default"]
AI_REASONER_NODES = ["reason"]


class AssistantService:
    # 工作流服务的业务唯一键，同一个business_key下的取数任务名称唯一
    __business_key: str
    # 工作流服务默认的系统提示词，包含所有基础业务信息
    __basic_system_template: str
    # RAG专用向量存储
    __vector_store:RedisVectorStore
    # langGraph实例
    __graph: CompiledStateGraph
    # 记忆(mem0)
    __memory: Memory

    __agent_def_dao:AgentDefDAO
    __query_data_task_dao:QueryDataTaskDAO
    __rag_file_dao:RagFileDAO


    def __init__(self, business_key):
        self.__business_key = business_key

        self.__query_data_task_dao = dao_container.query_data_task_dao()
        self.__agent_def_dao = dao_container.agent_def_dao()
        self.__rag_file_dao = dao_container.rag_file_dao()
        agent_def = self.__agent_def_dao.find_by_business_key_and_type(business_key, AgentDefType.ASSISTANT)

        if agent_def is None:
            raise Exception("未找到对应的agent定义")

        self.__basic_system_template = agent_def.system_prompt

        # 初始化大模型
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_API_KEY"] = read_private_config("langsmith", "LANGSMITH_API_KEY")
        os.environ["LANGSMITH_PROJECT"] = read_private_config("langsmith", "LANGSMITH_PROJECT")

        # 初始化llm
        api_key: Optional[str] = read_private_config("deepseek", "API_KEY")
        self.__llm = ChatDeepSeek(
            model=Config.LLM_MODEL,
            temperature=0,
            max_tokens=8192,
            timeout=60000,
            max_retries=2,
            api_key=api_key
        )

        self.__reasoner_llm = ChatDeepSeek(
            model=Config.REASONER_LLM_MODEL,
            max_tokens=8192,
            timeout=60000,
            max_retries=2,
            api_key=api_key,
            stream_usage = True,
        )

        # 初始化记忆(mem0)
        self.__memory = self.__create_memory()
        # 创建数据员子图调用工具
        # transfer_to_data_analyst_agent = create_handoff_tool(agent_name="data_analyst_agent")
        self.__data_analyst_tool = [ask_data_analyst]
        # 初始化langGraph
        self.__data_analyst_graph = get_or_create_data_analyst_service(business_key).graph
        self.__graph = self.__create_graph(agent_def.name)
        # 创建rag专用向量存储
        self.__vector_store = self.__create_vector_store()




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
                    # print(stream_mode, detail)
                    if stream_mode == "messages":
                        chunk, metadata = detail
                        if metadata['langgraph_node'] in AI_CHAT_NODES:
                            content = chunk.content
                            yield f"data: {json.dumps({'msgId': chunk.id, 'token': content})}\n\n"
                        elif metadata['langgraph_node'] in AI_REASONER_NODES:
                            if "reasoning_content" in chunk.additional_kwargs:
                                reasoning_content = chunk.additional_kwargs['reasoning_content']
                                yield f"data: {json.dumps({"reasoningContent": reasoning_content})}\n\n"
                    elif stream_mode == "tasks":
                        if detail["name"] == "get_all_tasks" and "result" in detail:
                            # 获取任务内容
                            for tuple in detail["result"]:
                                result_dict = {tuple[0]:tuple[1]}
                                if "task_names" in result_dict:
                                    task_names = result_dict["task_names"]
                                    yield f"data: {json.dumps({'taskSize': len(task_names), 'taskNames':",".join(task_names)})}\n\n"
                        elif detail["name"] == "get_doc_content_from_vector" and "result" in detail:
                            # 获取rag内容
                            for tuple in detail["result"]:
                                result_dict = {tuple[0]: tuple[1]}
                                if "rag_docs" in result_dict:
                                    rag_docs = result_dict["rag_docs"]
                                    yield f"data: {json.dumps({'ragDocSize': len(rag_docs)})}\n\n"
                                elif "rag_content" in result_dict:
                                    rag_content = result_dict["rag_content"]
                                    yield f"data: {json.dumps({'ragContent': rag_content})}\n\n"
                        elif detail["name"] == "get_memories" and "result" in detail:
                            # 获取查询到的记忆内容
                            for tuple in detail["result"]:
                                result_dict = {tuple[0]: tuple[1]}
                                if "memories" in result_dict:
                                    memories = result_dict["memories"]
                                    yield f"data: {json.dumps({'memorySize': len(memories)})}\n\n"
                                if "memory_content" in result_dict:
                                    memory_content = result_dict["memory_content"]
                                    yield f"data: {json.dumps({'memoryContent': memory_content})}\n\n"
                        elif (detail["name"] == "default" or detail["name"] == "chat") and "result" in detail:
                            # 获取生成的记忆内容
                            for tuple in detail["result"]:
                                result_dict = {tuple[0]: tuple[1]}
                                if "saved_memory_content" in result_dict:
                                    saved_memory_content = result_dict["saved_memory_content"]
                                    if saved_memory_content != "":
                                        yield f"data: {json.dumps({'savedMemoryContent': saved_memory_content})}\n\n"
                                if "msg_id_saved_memories" in result_dict:
                                    msg_id_saved_memories = result_dict["msg_id_saved_memories"]
                                    yield f"data: {json.dumps({'msgIdSavedMemories': msg_id_saved_memories})}\n\n"
                yield "event: done\ndata: \n\n"

            except Exception as e:
                logging.error(f"Stream processing error: {e}")
                yield f"event: error\ndata: {str(e)}\n\n"
                yield "event: done\ndata: \n\n"

        return async_event_stream

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

        stream = self.__graph.astream(
            input=InputState(messages=[("user", query)], session_id = session_id),
            config=config,
            stream_mode=["messages", "tasks"]
        )

        return stream

    def __get_all_tasks(self, state: AssistantState):
        """
        获取所有的任务
        :return:state
        """
        tasks = self.__query_data_task_dao.get_all_tasks(self.__business_key)

        task_details = []
        task_names = []
        task_content = "你能使用的所有任务信息如下:\n"
        for task in tasks:
            task_names.append(task.name)
            task_detail = QueryDataTaskDetail.model_validate(json.loads(task.task_detail))
            task_content += f"任务名：{task.name}\n {task_detail.to_desc_for_llm()}\n"
            task_details.append(task_detail)

        return {
            "task_details": task_details,
            "task_names": task_names,
            "task_content": task_content,
        }

    def __get_doc_content_from_vector(self, state:AssistantState):
        human_msg: HumanMessage = cast(HumanMessage, state.messages[-1])

        search_kwargs = {
            "score_threshold": Config.ASSISTANT_RAG_SCORE_THRESHOLD,
            "k": Config.ASSISTANT_RAG_TOP_K,
        }

        retriever_from_llm = MultiQueryRetriever.from_llm(
            retriever=self.__vector_store.as_retriever(search_kwargs=search_kwargs), llm=self.__llm
        )
        docs = retriever_from_llm.invoke(human_msg.content)
        rag_content = "查询知识库搜索到相关信息如下:\n"
        for doc in docs:
            file_name = doc.metadata["source"]
            upload_time = doc.metadata["upload_time"]
            content = doc.page_content

            rag_content += f"{content} \n内容来源于:{file_name},上传时间:{upload_time}\n"

        return {
            "rag_docs": docs,
            "rag_content": rag_content,
        }

    def __get_memories(self, state: AssistantState):
        try:
            human_msg: HumanMessage = cast(HumanMessage, state.messages[-1])

            # mem0 0.0.118版本有bug，threshold不能直接传，过滤时类型不匹配
            memories = self.__memory.search(human_msg.content,
                                            user_id=self.__business_key,
                                            limit=Config.ASSISTANT_MEMORY_TOP_K)
            # 过滤掉低于阈值的记忆
            filtered_memories = [
                memory for memory in memories['results']
                if float(memory.get('score', 0)) <= Config.ASSISTANT_MEMORY_SCORE_THRESHOLD
            ]

            memory_list = filtered_memories
            memory_content = self.__get_memory_content(filtered_memories)

            return {
                "memories": memory_list,
                "memory_content": memory_content,
            }
        except Exception as e:
            logging.error(f"Get memories error: {e}")
            return {
                "memories": [],
            }

    async def __intent_classifier(self, state: AssistantState):
        """
        意图判断节点
        :param state:
        :return: state
        """

        # 如果没有任何消息，直接返回DEFAULT
        if len(state.messages) == 0:
            state.intent_type = DEFAULT
            return state

        # 展示所有任务信息
        intent_prompt = ChatPromptTemplate.from_messages([
            # 系统提示词
            ("system", f"""{self.__basic_system_template}
            
            你的职责是根据用户的对话，以及以下信息：
            
            1.用户对话相关的知识库内容
            2.用户对话相关的记忆
            3.可以使用的数据查询任务
            
            结合用户最近的对话内容，分析用户的意图，如果用户的提问需要调用任务进行查询才能回答，则意图为“查询数据”，否则意图为“默认”
            
            {state.task_content}
            {state.rag_content}
            {state.memory_content}

            共有以下几种意图
            1. {QUERY_DATA} - 查询数据  
            2. {DEFAULT} - 默认

            按JSON格式输出分类结果，无关话题一律归类为默认。
            你还需要根据历史对话记录辨认用户是否是在进行数据查询（例如调成查询参数或查询步骤），若果"是"，则意图为查询数据，否则为默认。

            **重要说明**: 以下示例仅用于展示意图分类逻辑，不是实际对话历史，不要直接解析为意图。
                       """),
            # 明确标识示例区
            MessagesPlaceholder("examples", optional=True),
            # 包含所有历史对话
            *state.messages
        ])

        examples = [
            # 使用few-shot示例（强调AI必须返回JsonOutputParser的格式，不加AI会尝试返回自然语言的KV）：
            ("human", "你好，我是皮特"),
            ("ai", "{\"intent_type\": \"" + DEFAULT + "}"),
            ("human", "请检查员工考勤"),
            ("ai", "{\"intent_type\": \"" + QUERY_DATA + "}"),
        ]

        parser = JsonOutputParser(pydantic_object=IntentSchema)
        chain = intent_prompt | self.__llm | parser

        result = await chain.ainvoke({
            "examples": examples,
        })

        return {
            "intent_type" :result["intent_type"],
        }

    async def __default(self, state:AssistantState):
        """
        使用llm进行推理（只做rag和记忆读取）
        :param state:
        :return:state
        """
        # 1.basic提示词
        basic_system_prompt = self.__basic_system_template \
                              + f""""
                        当前日期:{datetime_util.get_current_date()}             
        """

        # 2.知识库提示词
        knowledge_prompt_context = "\n查询知识库搜索到相关信息如下:\n"
        if len(state.rag_docs) > 0:
            knowledge_prompt_context += state.rag_docs
        else:
            knowledge_prompt_context += "无"

        # 3.记忆提示词
        memory_content = state.memory_content

        all_messages = state.messages
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="\n".join(
                [basic_system_prompt, knowledge_prompt_context, memory_content])),
            *all_messages,
        ])
        chain = prompt | self.__reasoner_llm
        config = RunnableConfig(
            configurable={"timeout": 600000}
        )
        response = await chain.ainvoke({},
                                       config=config,
                                       )

        saved_memories = []
        saved_memory_content = ""
        msg_id_saved_memories = ""
        if response.tool_calls is None or len(response.tool_calls) == 0:
            # 生成事实记忆
            saved_memories, saved_memory_content = self.__add_fact_memory(all_messages, response)
            if len(saved_memories) > 0:
                msg_id_saved_memories = response.id

        return {
            "messages": [response.content],
            "saved_memories": saved_memories,
            "saved_memory_content": saved_memory_content,
            "msg_id_saved_memories": msg_id_saved_memories,
        }

    def __get_memory_content(self, memories:list[dict]):
        memory_content = "从历史对话中获取到的相关信息如下:\n"
        if len(memories) > 0:
            for memory in memories:
                formatted_time = datetime_util.format_iso_2_datetime_at_zone(memory["created_at"])
                memory_content += f"{memory["memory"]}(记忆产生于{formatted_time})\n"
        else:
            memory_content += "无"

        return memory_content


    async def __reason(self, state: AssistantState):
        """
        使用llm进行推理
        :param state:
        :return:state
        """
        # 1.basic提示词
        basic_system_prompt = self.__basic_system_template \
                + f""""
                当前日期:{datetime_util.get_current_date()}             
"""

        # 2.推理专用提示词
        reason_prompt_content = prompts.get_assistant_system_prompt()

        # 3.知识库提示词
        knowledge_prompt_content = state.rag_content

        # 4.记忆提示词
        memory_content = state.memory_content

        # 5.所有任务信息
        task_content = state.task_content

        all_messages = state.messages
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="\n".join([basic_system_prompt, reason_prompt_content, knowledge_prompt_content, memory_content, task_content])),
            *all_messages,
        ])
        chain = prompt | self.__reasoner_llm
        config = RunnableConfig(
            configurable={"timeout": 600000}
        )
        response = await chain.ainvoke({},
            config=config,
        )

        return {
            "reasoning_context": response.content,
        }

    def __find_last_human_message(self, messages, before_msg_id:str | None = None) -> (int, HumanMessage):
        """
        从消息列表中查找指定消息ID之前最后一条人类用户发送的消息

        Args:
            messages: 消息列表
            before_msg_id: 指定的消息ID，查找在此ID之前的消息

        Returns:
            tuple: (消息索引, HumanMessage对象) 如果找到的话，否则返回 (-1, None)
        """
        before_msg_index = -1
        # 从后往前遍历消息列表
        for i in range(len(messages) - 1, -1, -1):
            # 找到指定消息ID的位置
            if before_msg_id is not None and messages[i].id == before_msg_id:
                before_msg_index = i
            # 在指定消息之前找到的第一条人类用户消息
            if isinstance(messages[i], HumanMessage) and i <= before_msg_index:
                return i, messages[i]
        # 未找到符合条件的人类用户消息
        return -1, None


    def __add_fact_memory(self, messages, response):
        _, human_msg = self.__find_last_human_message(messages)

        response_content = response.content
        if response_content != "":
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
                result = self.__memory.add(interaction, user_id=self.__business_key, agent_id=self.__business_key)
                saved_memories = result.get('results', [])

                logging.info(f"Memory saved: {len(saved_memories)} memories added")

                saved_memory_content = ""
                for saved_memory in saved_memories:
                    event_type = saved_memory["event"]
                    content = ""
                    if event_type == "ADD":
                        content = "新增记忆:"
                    elif event_type == "UPDATE":
                        content = "更新记忆:"
                    elif event_type == "DELETE":
                        content = "删除记忆:"
                    content += saved_memory["memory"] + "\n"
                    saved_memory_content += content
                return saved_memories, saved_memory_content
            except Exception as e:
                logging.error(f"Error saving memory: {e}")
                return [], ""

    async def __chat(self, state: AssistantState):
        """
        使用llm进行对话(并查找过往记忆)
        :param state:
        :return:state
        """
        all_messages = state.messages

        # 如果是工具返回后的再次调用
        if isinstance(all_messages[-1], ToolMessage):
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=f"""
                {self.__basic_system_template}
    
                当前日期:{datetime_util.get_current_date()}            
                当前对话的sessionId = {state.session_id}
                业务键(businessKey) = {self.__business_key}
                
                你需要执行的操作是:
                {state.reasoning_context}
                """),
                *all_messages,
            ])
            chain = prompt | self.__llm.bind_tools(self.__data_analyst_tool)
        else:
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=f"""
                            {self.__basic_system_template}

                            当前日期:{datetime_util.get_current_date()}            
                            当前对话的sessionId = {state.session_id}
                            业务键(businessKey) = {self.__business_key}

                            你需要执行的操作是:
                            {state.reasoning_context}
                            
                            先向用户负数你要执行的具体操作（严格按照操作执行的步骤），然后给出你的答案。
                            """),
                all_messages[-1], # 取最后一条直接执行命令
            ])
            chain = prompt | self.__llm.bind_tools(self.__data_analyst_tool)
        response = await chain.ainvoke({})

        saved_memories = []
        saved_memory_content = ""
        msg_id_saved_memories = ""
        if response.tool_calls is None or len(response.tool_calls) == 0:
            # 生成事实记忆
            saved_memories, saved_memory_content = self.__add_fact_memory(all_messages, response)
            if len(saved_memories) > 0:
                msg_id_saved_memories = response.id

        return {
            "messages": [response],
            "saved_memories": saved_memories,
            "saved_memory_content": saved_memory_content,
            "msg_id_saved_memories": msg_id_saved_memories,
        }


    # conditional edge
    def __need_reason(self, state: AssistantState) -> Literal["reason", "default"]:
        if state.intent_type == QUERY_DATA:
            return "reason"
        else:
            return "default"

    def __need_invoke_tool(self, state: AssistantState) -> Literal["data_analyst_tool", END]:
        last_message = state.messages[-1]
        if not isinstance(last_message, AIMessage):
            raise ValueError(
                f"Expected AIMessage in output edges, but got {type(last_message).__name__}"
            )

        if not last_message.tool_calls:
            return END
        else:
            return "data_analyst_tool"


    def __create_memory(self):
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
                    "collection_name": "mem0_" + self.__business_key,
                    "redis_url": "redis://localhost:6379",
                    "embedding_model_dims": Config.EMBEDDING_MODEL_DIMS,
                }
            },
            "llm": {
                "provider": "langchain",
                "config": {
                    "model": self.__llm,
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

    def __create_vector_store(self) -> RedisVectorStore:
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
                index_name="assistant_" + self.__business_key,
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

    def __create_graph(self, graph_name):
        builder = StateGraph(AssistantState, input_schema=AssistantState)
        builder.add_node("intent_classifier", self.__intent_classifier)
        builder.add_node("get_all_tasks", self.__get_all_tasks)
        builder.add_node("get_doc_content_from_vector", self.__get_doc_content_from_vector)
        builder.add_node("get_memories", self.__get_memories)
        builder.add_node("reason", self.__reason)
        builder.add_node("default", self.__default)
        builder.add_node("chat", self.__chat)
        builder.add_node("data_analyst_tool", ToolNode(self.__data_analyst_tool))

        builder.add_edge(START, "get_all_tasks")
        builder.add_edge("get_all_tasks", "get_doc_content_from_vector")
        builder.add_edge("get_doc_content_from_vector", "get_memories")
        builder.add_edge("get_memories", "intent_classifier")
        builder.add_conditional_edges("intent_classifier", self.__need_reason)
        builder.add_edge("reason", "chat")
        builder.add_edge("default", END)
        builder.add_conditional_edges("chat", self.__need_invoke_tool)
        builder.add_edge("data_analyst_tool", "chat")

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

    # 先只支持md
    ALLOWED_EXTENSIONS = {'md', 'markdown', 'txt'}

    def __allowed_file(self, filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in self.ALLOWED_EXTENSIONS

    async def upload_file(self, file):
        # 获取文件内容
        if file and self.__allowed_file(file.filename):
            # 创建临时文件
            with tempfile.NamedTemporaryFile(delete=True, suffix='.md') as temp_file:
                temp_path = temp_file.name  # 获取临时文件路径

                # 方法1：使用 Quart 的异步保存（推荐）
                await file.save(temp_path)

                logging.info(f"文件保存成功, {temp_path}")

                # 处理Markdown文件
                ids = self.__process_single_file(temp_path, file.filename)

                self.__rag_file_dao.add_rag_file(
                    RagFileEntity(file_name=file.filename, content=str(ids), business_key=self.__business_key))
        else:
            raise Exception("Invalid file")


    def __add_metadata(self, doc, filename, time_str):
        doc.metadata['source'] = filename
        doc.metadata['upload_time'] = time_str
        return doc.metadata

    def __process_single_file(self, file_path, filename):
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
            ids = self.__vector_store.add_texts(texts=[doc.page_content for doc in splits],
                                                metadatas=[self.__add_metadata(doc, filename, now_str) for doc in
                                                         splits])
            logging.info("添加知识库文档到向量存储完成:%s", ids)
            return ids
        except Exception as e:
            logging.error(f"处理Markdown文件失败: {str(e)}")
            raise e

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

        res = self.__graph.invoke(
            input=AssistantState(messages=[("user", question)]),
            config=config,
        )

        result = res["messages"][-1]
        content = str(result.content)

        if content == "":
            print("content is empty:", result)

        return content

    def add_procedural_memory(self, session_id, msg_id):
        """
        添加过程记忆

        :param session_id: 会话ID，用于获取对应的对话状态
        :param msg_id: 消息ID，用于标识特定的消息
        :return: 添加成功/失败
        """
        # 上下文配置
        config = RunnableConfig(
            configurable={"thread_id": session_id},
        )

        state = self.__graph.get_state(config=config)

        all_messages = state.values["messages"]
        _, last_human_msg = self._find_last_human_message(all_messages, msg_id)

        # 遍历所有消息，找到对应的消息
        interaction = []
        interaction_start = False
        for message in all_messages:
            if hasattr(message, 'id') and message.id == last_human_msg.id:
                interaction_start = True
            elif hasattr(message, 'id') and message.id == msg_id:
                break

            if interaction_start:
                role = "user" if isinstance(message, HumanMessage) else "assistant"
                interaction.append({
                    "role": role,
                    "content": message.content,
                })

        result = self.__memory.add(interaction,
                                   user_id=self.__business_key,
                                   agent_id=self.__business_key,
                                   memory_type=MemoryType.PROCEDURAL.value,
                                   prompt=ASSISTANT_EXTRACT_QUERYING_DATA_PROMPT)
        return result


@tool
async def ask_data_analyst(business_key:str, session_id:str, task_name:str) -> str:
    """
    根据业务键和任务名，执行任务并返回任务结果

    输入参数：
    business_key: 业务键
    session_id：会话id
    task_name：任务名
    """
    data_analyst_service = get_or_create_data_analyst_service(business_key)
    content = await data_analyst_service.question(f"执行任务:{task_name}", session_id)

    return content




def get_or_create_assistant_service(business_key) -> AssistantService:
    service = get_assistant_service(business_key)
    if service is None:
        service = create_assistant_service(business_key)
    return service


def create_assistant_service(business_key) -> AssistantService:
    service = AssistantService(business_key)
    service_map[business_key] = service
    return service

def get_assistant_service(business_key):
    if business_key in service_map:
        return service_map[business_key]
    else:
        return None
