from IPython.display import Image, display
import logging
import os
import json
from dataclasses import dataclass, field
from datetime import datetime
from flask import current_app
from typing import Annotated
from typing import Dict, Literal
from typing import List, Optional, cast
from typing import Sequence

from langchain.embeddings import init_embeddings
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, SystemMessage
from langchain_core.messages import AnyMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig
from langchain_core.runnables.graph_ascii import draw_ascii
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

from dao import query_data_task_dao
from entity.query_data_task_entity import QueryDataTaskEntity
from model.query_data_task_detail import QueryDataTaskDetail
from model.work_group import WorkGroup
from model.workplace import Workplace
from service.example import ExampleTemplate, ToolInvoke
from service.wagner_tool_service import get_employee, get_group_employee, get_employee_time_on_task, \
    get_employee_efficiency
from util import datetime_util
from util.config_util import read_private_config



# 配置基础日志设置（输出到控制台）
logging.basicConfig(
    level=logging.INFO,  # 设置日志级别
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

workflow_map = {}

# 节点名称
INTENT_CLASSIFIER = "intent_classifier" #意图探测节点，判断用户是希望创建/修改/执行取数任务，还是做其他不相关的事情
PURE_CHAT = "pure_chat" # 纯对话节点，没有任何实际意义
FIND_TASK_IN_DB = "find_task_in_db" # 根据id或name从db中查找任务
FIND_TASK_IN_STORE = "find_task_in_store" # 根据用户意图从向量数据库中查找任务
EXECUTE_TASK = "execute_task" # 根据id或name查找并执行任务
CREATE_TASK = "create_task" # 创建一个新的取数任务
EDIT_TASK = "edit_task" # 根据id或name查找任务，并让用户进行编辑
TOOLS_FOR_TASK = "tools_for_task" # 所有数据查询工具，用来给EXECUTE_TASK节点执行任务
QUERY_DATA_NODE = "query_data_node" # 用来调用工具做简单的数据查询
TOOLS_FOR_QUERY_DATA = "tools_for_query_data" # 所有数据查询工具，用来给QUERY_DATA_NODE节点执行任务

# 记录有AI返回的节点
AI_CHAT_NODES = [PURE_CHAT, EXECUTE_TASK, CREATE_TASK, EDIT_TASK, QUERY_DATA_NODE]


@dataclass
class InputState:

    messages: Annotated[Sequence[AnyMessage], add_messages] = field(
        default_factory=list
    )


@dataclass
class State(InputState):
    #用户请求的意图类型
    intent_type: str|None = None
    #取数任务的目的
    target: str | None = None
    #取数任务id
    task_id: str|None = None
    #取数任务名称
    task_name: str |None = None
    #已经查找到的任务明细
    task_detail: str | None = None
    #任务执行结果
    task_result: str | None = None

QUERY_DATA = "query_data"
EXECUTE = "execute"
CREATE = "create"
EDIT = "edit"
OTHERS = "others"
# 定义意图分类规范
class IntentSchema(BaseModel):
    intent_type: Literal[EXECUTE, CREATE, EDIT, OTHERS] = Field(
        description="用户请求的核心意图类型"
    )
    target:Optional[str] = Field(
        default=None,
        description="创建取数任务的目的"
    )
    task_id: Optional[str] = Field(
        default=None,
        description="涉及的任务ID（如果是执行/编辑）"
    )
    task_name: Optional[str] = Field(
        default=None,
        description="涉及的任务名称（如果是执行/编辑）"
    )


# 任务的模板
class TaskSchema(BaseModel):
    target: Optional[str] = Field(
        description="任务的目标"
    )
    tool_used: Optional[str] = Field(
        default=None,
        description="使用的工具"
    )
    query_parameters: Optional[str] = Field(
        default=None,
        description="查询参数"
    )
    data_operation: Optional[str] = Field(
        default=None,
        description="调用工具后的加工逻辑"
    )
    guiding_language: Optional[str] = Field(
        default=None,
        description="获得用户对模板的部分更新信息后，引导用户继续完善模板的提示语，例如：从工具获取到结果之后还需要进行后续数据加工吗？"
    )

# class AiChatTemplate(BaseModel):
#     response: str = Field(
#         description="AI大模型的回复信息"
#     )



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

        self.basic_system_template = (f"你的角色是{workplace.name}这个工作点的一名工作组:{work_group.name}的组长助理，该小组的工作岗位是:{work_group.position_name}。"
        f"你所在的工作点为{workplace.name}，编码是：【{workplace.code}】，具体介绍是【{workplace.desc}】。你参与管理的小组，编码是【{work_group.code}】，具体介绍是【{work_group.desc}】。"
        "你的日常工作就是辅助你的小组长一起管理这个小组，所有员工信息、员工出勤情况、作业数据、作业情况都会由专门的工具获取，不要随便编造数据。"
        f"当前日期是{current_date}")

        # 设置业务用所有工具方法
        self.tool_list = [get_employee, get_group_employee, get_employee_time_on_task, get_employee_efficiency]

        # 初始化langGraph
        self.graph = self.create_graph("work_group_agent")

    # NODES
    def intent_classifier(self, state: State):
        intent_prompt = ChatPromptTemplate.from_messages([
            # 系统提示词
            ("system", f"""你是一个仓储报表系统意图分类器。根据用户输入判断意图：
                       1. {QUERY_DATA} - 查询数据  
                       2. {EXECUTE} - 执行现有任务
                       3. {CREATE} - 创建新任务
                       4. {EDIT} - 修改现有任务
                       5. {OTHERS} - 既不查询数据也和任务操作无关
                       按JSON格式输出分类结果，只有当用户明确提及创建、执行或修改任务时才归类为相应意图，无关话题一律归类为OTHERS。
                       **重要说明**: 以下示例仅用于展示分类逻辑，不是实际对话历史。
                       """),
            # 明确标识示例区
            MessagesPlaceholder("examples", optional=True),
            # 设定用户输入格式
            ("human", "{user_input}")
        ])

        examples = [
            # 使用few-shot示例（强调AI必须返回JsonOutputParser的格式，不加AI会尝试返回自然语言的KV）：
            ("human", "执行本小组上个月的月度人效报告"),
            ("ai", "{\"intent_type\": \"" + EXECUTE + "\", \"task_name\": \"月度人效报告\"}"),
            ("human", "运行本组上周的工时分析报表"),
            ("ai", "{\"intent_type\": \"" + EXECUTE + "\", \"task_name\": \"工时分析报表\"}"),
            ("human", "创建一个工时分析报表，用来分析每天组内员工的工时分布"),
            ("ai",
             "{\"intent_type\": \"" + CREATE + "\", \"task_name\": \"工时分析报表\", \"target\": \"用来分析每天组内员工的工时分布\"}"),
            ("human", "查一下员工工时信息"),
            ("ai",
             "{\"intent_type\": \"" + QUERY_DATA + "\"}"),
        ]

        parser = JsonOutputParser(pydantic_object=IntentSchema)
        chain = intent_prompt | self.llm | parser

        user_query = state.messages[-1].content

        result = chain.invoke({
            "user_input": user_query,
            "examples": examples,
        })

        # 更新状态
        intent_type = result["intent_type"]

        logging.info("推断出的intent_type:%s", intent_type)

        # 如果用户有明确意图且指定了任务名或任务id，才更新意图类型
        if intent_type in [EXECUTE, CREATE, EDIT] and ("task_name" in result or "task_id" in result):
            state.intent_type = intent_type
            if "task_id" in result:
                state.task_id = result["task_id"]
            if "task_name" in result:
                state.task_name = result["task_name"]
            if "target" in result:
                state.target = result["target"]
        elif intent_type == QUERY_DATA:
            state.intent_type = intent_type
        elif intent_type == OTHERS and  ("task_name" not in result and "task_id" not in result):
            state.intent_type = intent_type

        return state



    def pure_chat(self, state: State):
        prompt = ChatPromptTemplate.from_messages([
            # 系统提示词
            ("system", self.basic_system_template),
            # 设定用户输入格式
            *state.messages
        ])


        chain = prompt | self.llm

        result = chain.invoke({})

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
            detail = QueryDataTaskDetail.model_validate(json.loads(query_data_task.task_detail))
            state.task_detail = detail.to_desc()
            return state
        else:
            return state

    def find_task_in_store(self, state:State):
        return state

    # 调用工具执行任务
    def execute_task(self, state:State):
        all_messages = state.messages

        # 如果是工具返回后的再次调用
        if isinstance(all_messages[-1], ToolMessage):
            # 使用完整的对话历史作为上下文
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=f"{self.basic_system_template}\n\n任务详情:\n{state.task_detail}"),
                *all_messages  # 包含所有历史消息
            ])
            chain = prompt | self.llm.bind_tools(self.tool_list)
            response = chain.invoke({})
        else:
            last_human_message = state.messages[-1].content

            # 初次调用，使用原始用户查询
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=f"{self.basic_system_template}\n\n任务详情:\n{state.task_detail}"),
                HumanMessage(content="{user_input}")  # 用户最后一条消息
            ])

            chain = prompt | self.llm.bind_tools(self.tool_list)
            response = chain.invoke({"user_input": last_human_message})


        return {
            "messages": [response],
            "task_result": response.content  # 存储任务结果
        }

    # 调用工具查询数据
    def query_data(self, state: State):
        all_messages = state.messages

        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=f"{self.basic_system_template}"),
            *all_messages  # 包含所有历史消息
        ])
        chain = prompt | self.llm.bind_tools(self.tool_list)
        response = chain.invoke({})

        return {
            "messages": [response],
        }

    def create_task(self, state:State):
        task_name = state.task_name
        target = state.target

        last_human_message = state.messages[-1].content

        # 首次创建任务时，自动返回默认模板
        if state.task_detail is None:
            detail = QueryDataTaskDetail(
                target="(请说明该任务的使用意图)" if target is None else target,
                tool_used="(希望使用哪些工具，如不知道也可不填写让AI组长助理自行判断)",
                query_parameters="(需要传入哪些参数，请用语言描述一下)",
                data_operation="(查询到结果之后希望进行哪些加工处理，请给出详细描述)"
            )

            create_ai_msg = AIMessage(content=f"任务模板如下\n\n任务名称：{task_name}\n{detail.to_desc()}\n请把任务内容补充到模板中")
            return {
                "messages": [create_ai_msg],
                "task_detail": detail,
            }
        else:
            # 后续根据用户提示信息更新模板
            parser = JsonOutputParser(pydantic_object=TaskSchema)

            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=f"""
                {self.basic_system_template}
                
                现在你要辅助用户把以下任务模板填写完整
                任务模板如下
                
                任务名称：{task_name}
                {state.task_detail}
                
                请询问引导用户更新模板以下四项内容：
                任务的目标、使用的工具、查询参数、从工具获取到结果之后进行以下数据加工这四项内容。
                
                如果用户给出了模板的更新信息，把用户给出的信息稍作整理之后更新到任务模板中，如果用户没给出某一项内容的更新信息，请填：无。
                把任务模板的四项内容按JSON格式输出任务详情。
                
                **重要说明**: 以下示例仅用于展示维护任务模板的问答逻辑，不是实际对话历史
                """),
                # 明确标识示例区
                MessagesPlaceholder("examples", optional=True),
                HumanMessage(content="{user_input}")  # 用户最后一条消息
            ])

            examples = [
                # 使用few-shot示例（强调AI必须返回JsonOutputParser的格式，不加AI会尝试返回自然语言的KV）：
                ("ai", """
                任务模板如下
                
                任务名称：员工岗位人效
                任务的目标:每日获取员工岗位人效
                使用的工具:查询当天全员的工作效率
                查询参数:(需要传入哪些参数，请用语言描述一下)
                调用工具后的加工逻辑:(查询到结果之后希望进行哪些加工处理，请给出详细描述)
                     
                请把任务内容补充到模板中
                """),
                ("human", "查询参数是工作日期和员工工号"),
                ("ai", "{\"target\": \"每日获取员工岗位人效\", \"tool_used\": \"查询当天全员的工作效率\", \"query_parameters\": \"工作日期、员工工号\", \"data_operation\": \"无\",\"guiding_language\":\"调用工具后的加工逻辑还需要添加吗？\"}"),
            ]

            chain = prompt | self.llm.bind_tools(self.tool_list)| parser
            response = chain.invoke({
                "user_input": last_human_message,
                "examples": examples,
            })

            task_detail = QueryDataTaskDetail.model_validate(response)

            is_finished_ai_message = AIMessage(content=f"""
            任务模板如下
                
            任务名称：{task_name}
            {task_detail.to_desc()}
            
            {response["guiding_language"]}
            """)

            print(is_finished_ai_message)
            return {
                "messages": [is_finished_ai_message],
            }


    # EDGES
    def intent_classifier_to_next(self, state: State) -> Literal[FIND_TASK_IN_DB, CREATE_TASK, QUERY_DATA_NODE, END]:
        if state.intent_type == OTHERS:
            return QUERY_DATA_NODE
        elif state.intent_type == EXECUTE or state.intent_type == EDIT:
            return FIND_TASK_IN_DB
        elif state.intent_type == CREATE:
            return CREATE_TASK
        elif state.intent_type == QUERY_DATA:
            return QUERY_DATA_NODE
        else:
            return END

    def need_to_find_store(self, state:State) -> Literal[FIND_TASK_IN_STORE, EXECUTE_TASK]:
        if state.task_detail is not None:
            return EXECUTE_TASK
        else:
            return FIND_TASK_IN_STORE


    def need_invoke_tool(self, state:State) -> Literal[TOOLS_FOR_TASK, TOOLS_FOR_QUERY_DATA, END]:
        last_message = state.messages[-1]
        if not isinstance(last_message, AIMessage):
            raise ValueError(
                f"Expected AIMessage in output edges, but got {type(last_message).__name__}"
            )

        if not last_message.tool_calls:
            return END
        elif state.intent_type == EXECUTE:
            return TOOLS_FOR_TASK
        elif state.intent_type == QUERY_DATA or state.intent_type == OTHERS:
            return TOOLS_FOR_QUERY_DATA
        else:
            return END


    # 创建Graph
    def create_graph(self, graph_name):
        builder = StateGraph(State, input_schema=InputState)
        # 新Graph

        builder.add_node(INTENT_CLASSIFIER, self.intent_classifier)
        builder.add_node(QUERY_DATA_NODE, self.query_data)
        # builder.add_node(PURE_CHAT, self.pure_chat)
        builder.add_node(FIND_TASK_IN_DB, self.find_task_in_db)
        builder.add_node(FIND_TASK_IN_STORE, self.find_task_in_store)
        builder.add_node(EXECUTE_TASK, self.execute_task)
        builder.add_node(CREATE_TASK, self.create_task)
        builder.add_node(TOOLS_FOR_TASK, ToolNode(self.tool_list))
        builder.add_node(TOOLS_FOR_QUERY_DATA, ToolNode(self.tool_list))

        builder.add_edge(START, INTENT_CLASSIFIER)
        builder.add_conditional_edges(INTENT_CLASSIFIER, self.intent_classifier_to_next)
        builder.add_conditional_edges(FIND_TASK_IN_DB, self.need_to_find_store)
        builder.add_edge(FIND_TASK_IN_STORE, EXECUTE_TASK)
        builder.add_edge(TOOLS_FOR_TASK, EXECUTE_TASK)
        builder.add_edge(TOOLS_FOR_QUERY_DATA, QUERY_DATA_NODE)
        builder.add_conditional_edges(EXECUTE_TASK, self.need_invoke_tool)
        builder.add_conditional_edges(QUERY_DATA_NODE, self.need_invoke_tool)

        # 记忆功能
        memory = InMemorySaver()
        graph = builder.compile(name=graph_name, checkpointer=memory)

        try:
            print(graph.get_graph().draw_ascii())
        except Exception:
            # This requires some extra dependencies and is optional
            pass

        return graph

    def stream_question(self, query, session_id):
        # 上下文配置
        config = {"configurable": {"thread_id": session_id}}

        stream = self.graph.stream(input = InputState(messages=[("user", query)]),
            config = config,
           stream_mode="messages")

        return stream



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
