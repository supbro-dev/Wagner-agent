import asyncio
import os
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated
from typing import Dict, Literal
from typing import List, Optional, cast
from typing import Sequence

from langchain.embeddings import init_embeddings
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.messages import AnyMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_deepseek import ChatDeepSeek
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_store
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.graph import add_messages
from langgraph.managed import IsLastStep
from langgraph.prebuilt import ToolNode
from langgraph.store.memory import InMemoryStore
from pydantic import BaseModel, Field
from typing_extensions import Annotated

from dao import ai_example_dao, query_data_task_dao
from entity.ai_example_entity import AiExampleEntity
from entity.query_data_task_entity import QueryDataTaskEntity
from model.query_data_task_detail import QueryDataTaskDetail
from model.work_group import WorkGroup
from model.workplace import Workplace
from service.example import ExampleTemplate, ToolInvoke
from service.wagner_tool_service import get_employee, get_group_employee, get_employee_time_on_task, \
    get_employee_efficiency
from util import datetime_util
from util.config_util import read_private_config

workflow_map = {}

# 节点名称
INTENT_CLASSIFIER = "intent_classifier" #意图探测节点，判断用户是希望创建/修改/执行取数任务，还是做其他不相关的事情
PURE_CHAT = "pure_chat" # 纯对话节点，没有任何实际意义
FIND_TASK_IN_DB = "find_task_in_db" # 根据id或name从db中查找任务
FIND_TASK_IN_STORE = "find_task_in_store" # 根据用户意图从向量数据库中查找任务
EXECUTE_TASK = "execute_task" # 根据id或name查找并执行任务
CREATE_TASK = "create_task" # 创建一个新的取数任务
EDIT_TASK = "edit_task" # 根据id或name查找任务，并让用户进行编辑


@dataclass
class InputState:

    messages: Annotated[Sequence[AnyMessage], add_messages] = Field(
        default=Sequence[AnyMessage]
    )


@dataclass
class State(InputState):
    workplace_code:str = Field(
        description="工作点编码"
    )

    work_group_code:str = Field(
        discriminator="工作组编码"
    )

    intent_type: Optional[str] = Field(
        default=None,
        description= "用户请求的意图类型"
    )
    task_id: Optional[str] = Field(
        default=None,
        description="取数任务id"
    )
    task_name: Optional[str] = Field(
        default=None,
        description="取数任务名称"
    )
    task_detail: Optional[str] = Field(
        default=None,
        description="已经查找到的任务明细"
    )

    def __init__(self, workplace_code, work_group_code):
        self.workplace_code = workplace_code
        self.work_group_code = work_group_code


EXECUTE = "execute"
CREATE = "create"
EDIT = "edit"
OTHERS = "others"
# 1. 定义意图分类规范
class IntentSchema(BaseModel):
    intent_type: Literal[EXECUTE, CREATE, EDIT, OTHERS] = Field(
        description="用户请求的核心意图类型"
    )
    task_id: Optional[str] = Field(
        default=None,
        description="涉及的任务ID（如果是执行/编辑）"
    )
    task_name: Optional[str] = Field(
        default=None,
        description="涉及的任务名称（如果是执行/编辑）"
    )

class WorkflowService:
    def __init__(self, workplace: Workplace, work_group: WorkGroup):
        current_date = datetime_util.format_datatime(datetime.now())

        self.workplace = workplace
        self.work_group = work_group

        # 初始化大模型
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_API_KEY"] = read_private_config("langsmith", "LANGSMITH_API_KEY")
        os.environ["LANGSMITH_PROJECT"] = read_private_config("langsmith", "LANGSMITH_PROJECT")

        api_key: Optional[str] = read_private_config("deepseek", "API_KEY")
        self.llm = ChatDeepSeek(
            model="deepseek-chat",
            temperature=0,
            max_tokens=None,
            timeout=None,
            max_retries=2,
            api_key=api_key
        )

        self.basic_system_template = f"你的角色是{workplace.name}这个工作点的一名工作组:{work_group.name}的组长助理，该小组的工作岗位是:{work_group.position_name}。"
        f"{workplace.name}的具体介绍是【{workplace.desc}】。你管理的小组的具体介绍是【{work_group.desc}】。"
        "你的日常工作就是辅助你的小组长一起管理这个小组，所有员工信息、员工出勤情况、作业数据、作业情况都会由专门的工具获取，不要随便编造数据。"
        f"当前日期是{current_date}"

        # 初始化langGraph
        self.graph = self.create_graph("work_group_agent")

    # NODES
    def intent_classifier(self, state: State):
        intent_prompt = ChatPromptTemplate.from_messages([
            # 系统提示词
            ("system", "你是一个仓储报表系统意图分类器。根据用户输入判断意图：\n"
                       f"1. {EXECUTE} - 执行现有任务\n"
                       f"2. {CREATE} - 创建新任务\n"
                       f"3. {EDIT} - 修改现有任务\n"
                       f"4. {OTHERS} - 和任务无关内容\n"
                       "按JSON格式输出分类结果"),
            # 使用few-shot示例（强调AI必须返回JsonOutputParser的格式，不加AI会尝试返回自然语言的KV）：
            ("human", "用户输入：执行月度库存报告"),
            ("ai", "{{\"intent_type\": \"" + EXECUTE + "\", \"task_name\": \"执行月度库存报告\"}}"),
            # 设定用户输入格式
            ("human", "用户输入：{user_input}")
        ])

        parser = JsonOutputParser(pydantic_object=IntentSchema)
        chain = intent_prompt | self.llm | parser

        user_query = state.messages[-1].content

        result = chain.invoke({"user_input": user_query})

        # 更新状态
        intent_type = result["intent_type"]
        new_state = state
        if intent_type != OTHERS:
            if "task_id" in result:
                new_state.task_id = result["task_id"]
            if "task_name" in result:
                new_state.task_name = result["task_name"]
            return new_state
        else:
            return new_state


    def pure_chat(self, state: State):
        prompt = ChatPromptTemplate.from_messages([
            # 系统提示词
            ("system", self.basic_system_template),
            # 设定用户输入格式
            ("human", "用户输入：{user_input}")
        ])

        chain = prompt | self.llm

        user_query = state.messages[-1].content

        result = chain.invoke({"user_input": user_query})

        # 更新状态
        return {
            "messages":[cast(AIMessage, result)]
        }

    def find_task_in_db(self, state: State):
        query_data_task: QueryDataTaskEntity | None = None

        if state.task_id is not None:
            query_data_task = query_data_task_dao.find_by_id(state.task_id)
        elif state.task_name is not None:
            business_key = f"{self.workplace.code}_{self.work_group.code}"
            query_data_task = query_data_task_dao.find_by_name(business_key, state.task_name)

        if query_data_task is not None:
            detail = QueryDataTaskDetail.model_validate(query_data_task.task_detail)
            state.task_detail = detail.to_desc()
            return state
        else:
            return state

    def find_task_in_store(self, state:State):
        return state


    def execute_task(self, state:State):
        pass

    def create_task(self, state:State):
        pass


    # EDGES
    def intent_classifier_to_next(self, state: State) -> Literal[PURE_CHAT, EXECUTE_TASK, CREATE_TASK, END]:
        if state.intent_type == OTHERS:
            return PURE_CHAT
        elif state.intent_type == EXECUTE or state.intent_type == EDIT:
            return FIND_TASK_IN_DB
        elif state.intent_type == CREATE:
            return CREATE_TASK
        else:
            return END

    def need_to_find_store(self, state:State) -> Literal[FIND_TASK_IN_STORE, EXECUTE_TASK]:
        if state.task_detail is not None:
            return EXECUTE_TASK
        else:
            return FIND_TASK_IN_STORE

    # 创建Graph
    def create_graph(self, graph_name):
        builder = StateGraph(State, input_schema=InputState)
        # 新Graph

        # START
        # 查找模板(TOOL)
        # NodeFindInDb 根据模板id或名称去数据库精确查找模板
        # NodeSearch 根据 描述信息去向量库查找Top1相似模板
        # NodeJudge(LLM) 判断是执行模板，新增模板，维护模板
        # IF是执行
        # NodeExecute(LLM) 执行模板
        # ELIF 新增模板
        # NodeShowEmptyTemplateScheme(TOOL) 提问用户描述给出描述信息
        # NodeEditTemplate(LLM) 根据用户提示，不断维护这个模板信息
        # NodeExecute(LLM) 执行模板
        # NodeSaveTemplate(HIO) 保存模板
        # ELSE 维护模板
        # NodeShowTemplateScheme 展示原始模板信息
        # NodeEditTemplate(LLM) 根据用户提示，不断维护这个模板信息
        # NodeExecute(LLM) 执行模板
        # NodeSaveTemplate(HIO) 保存模板
        # END

        builder.add_node(INTENT_CLASSIFIER, self.intent_classifier)
        builder.add_node(PURE_CHAT, self.pure_chat)
        builder.add_node(FIND_TASK_IN_DB, self.find_task_in_db)
        builder.add_node(FIND_TASK_IN_STORE, self.find_task_in_store)
        builder.add_node(EXECUTE_TASK, self.execute_task)
        builder.add_node(CREATE_TASK, self.create_task)

        builder.add_edge(START, INTENT_CLASSIFIER)
        builder.add_conditional_edges(INTENT_CLASSIFIER, self.intent_classifier_to_next)
        builder.add_conditional_edges(FIND_TASK_IN_DB, self.need_to_find_store)
        builder.add_edge(FIND_TASK_IN_STORE, EXECUTE_TASK)
        builder.add_edge(EXECUTE_TASK, END)

        # 记忆功能
        memory = InMemorySaver()
        graph = builder.compile(name=graph_name, checkpointer=memory)

        return graph


    async def question(self, query, session_id) -> (str, str, str):
        # 上下文配置
        config = {"configurable": {"thread_id": session_id}}

        res = await self.graph.ainvoke(
            input = InputState(messages=[("user", query)]),
            config = config,
        )

        result = res["messages"][-1]
        content = str(result.content)

        if content == "":
            print("content is empty:", result)

        return content

def create_workflow(workplace: Workplace, work_group: WorkGroup) -> WorkflowService:
    workflow_service = WorkflowService(workplace, work_group)

    workflow_map[f"{workplace.code}_{work_group.code}"] = workflow_service
    return workflow_service

def get_workflow(workplace_code, work_group_code) -> WorkflowService:
    workflow_service = workflow_map[f"{workplace_code}_{work_group_code}"]
    return workflow_service
