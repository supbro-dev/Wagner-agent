# Initialize memory
import logging
import os
from typing import Optional, Type, cast, Literal

from langchain_core.callbacks import CallbackManagerForToolRun
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langchain_deepseek import ChatDeepSeek
from langchain_redis import RedisVectorStore
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.constants import START, END
from langgraph.graph.state import CompiledStateGraph, StateGraph
from langgraph.prebuilt import ToolNode
from memori import Memori, create_memory_tool, MemoryTool, ConfigManager
from memori.core.providers import ProviderConfig
from pydantic import BaseModel, Field

from config import Config
from service.agent.model.assistant_state import AssistantState
from util.config_util import read_private_config


service_map = {}

class AssistantGraphNode:
    CHAT = "chat"
    TOOL_SEARCH_FOR_MEMORI = "tool_search_for_memori"


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
        self.memory_search_tool = MemorySearchTool(memory_tool=memory_tool)

        # 初始化langGraph
        self.graph = self.create_graph(workflow_name)

    def find_last_human_message(self, messages) -> (int, BaseMessage):
        """
        从后往前查找最后一条HumanMessage
        """
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], HumanMessage):
                return i, messages[i]
        return -1, None

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
            namespace=self.business_key,
            schema_init=False, # 第一次执行设置为True，为了自动创建表结构
            provider_config = llm_provider,
            # verbose=True,
        )
        memori.enable()

        return memori

    def create_graph(self, graph_name):
        builder = StateGraph(AssistantState, input_schema=AssistantState)
        builder.add_node(AssistantGraphNode.CHAT, self.chat)
        builder.add_node(AssistantGraphNode.TOOL_SEARCH_FOR_MEMORI, ToolNode([self.memory_search_tool]))

        builder.add_edge(START, AssistantGraphNode.CHAT)
        builder.add_conditional_edges(AssistantGraphNode.CHAT, self.need_search_for_memori)
        builder.add_edge(AssistantGraphNode.TOOL_SEARCH_FOR_MEMORI, AssistantGraphNode.CHAT)

        # memory = InMemorySaver()

        graph = builder.compile(name=graph_name)
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


def create_assistant_service(workflow_name, business_key, basic_system_template) -> AssistantService:
    service = AssistantService(workflow_name, business_key, basic_system_template)
    service_map[business_key] = service

    return service

def get_assistant_service(business_key) -> AssistantService:
    service = service_map[business_key]
    return service

