from typing import Callable
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable
from typing import Literal
from typing import Optional, cast
from typing import Sequence

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, SystemMessage
from langchain_core.messages import AnyMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool as create_tool
from langchain_core.tools import tool
from langchain_deepseek import ChatDeepSeek
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.graph import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.interrupt import HumanInterruptConfig, HumanInterrupt
from langgraph.types import interrupt, Command
from pydantic import BaseModel, Field
from typing_extensions import Annotated

from dao import query_data_task_dao
from entity.query_data_task_entity import QueryDataTaskEntity
from model.query_data_task_detail import QueryDataTaskDetail
from model.work_group import WorkGroup
from model.workplace import Workplace
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
SAME_NAME_WHEN_CREATE = "same_name_when_create" # 创建任务时查找到同名任务
EXECUTE_TASK = "execute_task" # 根据id或name查找并执行任务
CREATE_TASK = "create_task" # 创建一个新的取数任务
EDIT_TASK = "edit_task" # 根据id或name查找任务，并让用户进行编辑
DELETE_TASK = "delete_task" # 逻辑删除任务
TOOLS_FOR_TASK = "tools_for_task" # 所有数据查询工具，用来给EXECUTE_TASK节点执行任务
QUERY_DATA_NODE = "query_data_node" # 用来调用工具做简单的数据查询
TOOLS_FOR_QUERY_DATA = "tools_for_query_data" # 所有数据查询工具，用来给QUERY_DATA_NODE节点执行任务
TOOLS_FOR_SAVE_TASK = "tools_for_save_task" # 保存任务用的工具，包括人工审核
TOOLS_FOR_DELETE_TASK = "tools_for_delete_task" # 删除任务用的工具，包括人工审核
HOW_TO_IMPROVE_TASK = "how_to_improve_task" # 检查是否还需要用户进一步完善任务模板内容
UPDATE_TASK_DETAIL = "update_task_detail" # 编辑任务信息时更新任务信息对象



# 记录有AI逐步返回token返回的节点
AI_CHAT_NODES = [PURE_CHAT, EXECUTE_TASK, EDIT_TASK, QUERY_DATA_NODE, HOW_TO_IMPROVE_TASK, DELETE_TASK]
# 记录人工构造AI MSG
AI_MSG_NODES = [SAME_NAME_WHEN_CREATE]



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
    task_id: str|int = None
    #取数任务名称
    task_name: str |None = None
    # 第一次创建任务
    first_time_create: bool = True
    #已经查找到的任务明细
    task_detail: QueryDataTaskDetail | None = None
    #任务执行结果
    task_result: str | None = None
    #编辑时，任务信息是否被修改
    is_edited: bool = False


QUERY_DATA = "query_data"
EXECUTE = "execute"
CREATE = "create"
EDIT = "edit"
DELETE = "delete"
OTHERS = "others"
# 定义意图分类规范
class IntentSchema(BaseModel):
    intent_type: Literal[EXECUTE, CREATE, EDIT, DELETE, OTHERS] = Field(
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
    # tool_used: Optional[str] = Field(
    #     default=None,
    #     description="使用的工具"
    # )
    # query_parameters: Optional[str] = Field(
    #     default=None,
    #     description="查询参数"
    # )
    data_operation: Optional[str] = Field(
        default=None,
        description="调用工具后的加工逻辑"
    )
    # say_something: Optional[str] = Field(
    #     default=None,
    #     description="跟对话的用户继续说些什么：当用户填写了一些任务模板信息，你需要检查当前模板是否填写完整，然后提示用户还要完善哪些项内容，如果确认用户都填写完毕了，询问用户是否进行保存"
    # )

# 默认任务模板
default_task_template = QueryDataTaskDetail(
        target="无。(请说明该任务的使用意图)",
        data_operation="无。(请详细描述，查询到结果之后希望进行哪些加工处理)"
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

        self.basic_system_template = (f"你的角色是{workplace.name}这个工作点的一名工作组:{work_group.name}的组长助理，该小组的工作岗位是:{work_group.position_name}。"
        f"你所在的工作点为{workplace.name}，编码是：【{workplace.code}】，具体介绍是【{workplace.desc}】。你参与管理的小组，编码是【{work_group.code}】，具体介绍是【{work_group.desc}】。"
        "你的日常工作就是辅助你的小组长一起管理这个小组，所有员工信息、员工出勤情况、作业数据、作业情况都会由专门的工具获取，不要随便编造数据。"
        f"当前日期是{current_date}")

        # 设置业务用所有工具方法
        self.tool_list = [get_employee, get_group_employee, get_employee_time_on_task, get_employee_efficiency]

        # 保存任务用的工具列表
        self.save_task_tool_list = [add_human_in_the_loop(save_task, "保存", lambda tool_input : f"是否确定要保存任务：{tool_input["task_name"]}？")]

        # 删除任务的工具
        self.delete_task_tool_list = [add_human_in_the_loop(logical_delete_task, "删除", lambda tool_input: f"是否确定要删除任务：{tool_input["task_name"]}?")]

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
                       5. {DELETE} - 删除现有任务
                       6. {OTHERS} - 既不查询数据也和任务操作无关
                       按JSON格式输出分类结果，只有当用户明确提及创建、执行或修改任务时才归类为相应意图，无关话题一律归类为OTHERS。
                       **重要说明**: 以下示例仅用于展示分类逻辑，不是实际对话历史。
                       """),
            # 明确标识示例区
            MessagesPlaceholder("examples", optional=True),
            # 包含所有历史对话
            *state.messages
        ])

        examples = [
            # 使用few-shot示例（强调AI必须返回JsonOutputParser的格式，不加AI会尝试返回自然语言的KV）：
            ("human", "执行本小组上个月的月度人效报告"),
            ("ai", "{\"intent_type\": \"" + EXECUTE + "\", \"task_name\": \"月度人效报告\"}"),
            ("human", "运行本组上周的工时分析报表"),
            ("ai", "{\"intent_type\": \"" + EXECUTE + "\", \"task_name\": \"工时分析报表\"}"),
            ("human", "创建一个工时分析报表，用来分析每天组内员工的工时分布"),
            ("ai",
             "{\"intent_type\": \"" + CREATE + "\", \"task_name\": \"工时分析报表\"}"),
            ("human", "查一下员工工时信息"),
            ("ai",
             "{\"intent_type\": \"" + QUERY_DATA + "\"}"),
        ]

        parser = JsonOutputParser(pydantic_object=IntentSchema)
        chain = intent_prompt | self.llm | parser

        result = chain.invoke({
            "examples": examples,
        })

        # 更新状态
        intent_type = result["intent_type"]

        logging.info("推断出的intent_type:%s", intent_type)

        # 如果用户有明确意图且指定了任务名或任务id，才更新意图类型
        if intent_type in [EXECUTE, CREATE, EDIT, DELETE] and ("task_name" in result or "task_id" in result):
            state.intent_type = intent_type
            if "task_id" in result:
                state.task_id = result["task_id"]
            if "task_name" in result:
                state.task_name = result["task_name"]
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
            state.task_name = query_data_task.name
            state.task_id = query_data_task.id
            state.task_detail = detail
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

    def same_name_when_create(self, state:State):
        response = ("ai", f"查找到与【{state.task_name}】同名任务，是否修改该任务？")
        return {
            "messages": [cast(AIMessage, response)],
        }

    def update_task_detail(self, state: State):
        if not state.is_edited:
            return state

        parser = JsonOutputParser(pydantic_object=TaskSchema)

        prompt = ChatPromptTemplate.from_messages([
            ("system", f"""
                       {self.basic_system_template}

                       现在你要解析用户的输入，参考任务模板解析之后，按JSON格式输出用户给出的模板内容。
                       
                       任务id:{state.task_id}
                       任务名称:{state.task_name}

                       任务模板如下
                       {default_task_template.to_desc()}

                       **重要说明**: 以下示例仅用于展示维护任务模板的问答逻辑，不是实际对话历史
                       """),
            # 明确标识示例区
            MessagesPlaceholder("examples", optional=True),
            # 包含历史所有对话
            *state.messages
        ])

        examples = [
            ("human", "任务的目标：每日工作效率统计。数据加工逻辑：单加一列：工作量除以工作时长为工作效率"),
            ("ai",
             "{\"data_operation\": \"单加一列：工作量除以工作时长为工作效率\",  \"target\": \"每日工作效率统计\"}"),
        ]

        chain = prompt | self.llm | parser
        response = chain.invoke({
            "examples": examples,
        })

        task_detail = QueryDataTaskDetail.model_validate(response)

        if state.task_detail.to_dict() != task_detail.to_dict():
            state.task_detail = task_detail
            # 设置任务信息已被修改
            state.is_edited = True

        return state

    def edit_task(self, state:State):
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=f"""
                                    {self.basic_system_template}
                                    你现在要做的事情是辅助用户修改已有的取数任务，这里无需调用工具获取任务详情，任务信息已经在下面给出：
                                    
                                    取数任务的模板如下：
                                    {default_task_template.to_desc()}
                                    
                                    已有的取数任务如下：
                                    任务名称：{state.task_name}
                                    {state.task_detail.to_desc()}
                                    
                                    具体要做的事情如下：
                                    1.向用户展示详细的取数任务内容
                                    2.询问用户取数任务中有哪些项希望进行修改。不过，任务名称是不能修改的。
                                                                        
                                    请注意：{"由于之前用户已经修改过任务信息，直接进行保存。" if state.is_edited else "之前用户还未修改过任务信息"}                                    
                                    """),
            *state.messages])

        chain = prompt | self.llm.bind_tools(self.save_task_tool_list)

        response = chain.invoke({})

        return {
            "messages": [response],
        }


    def delete_task(self, state:State):
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=f"""
                                   {self.basic_system_template}
                                   你现在要做的事情是删除取数任务
                                   
                                   取数任务的模板如下：
                                   {default_task_template.to_desc()}
                                   
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

        response = chain.invoke({})

        return {
            "messages": [response],
        }

    # 解析用户输入中对任务模板的补充
    def create_task(self, state:State):
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
                {default_task_template.to_desc()}            
                
                用户给你的输入参考任务模板解析之后，按JSON格式输出用户给出的模板内容。
                **重要说明**: 以下示例仅用于展示维护任务模板的问答逻辑，不是实际对话历史
                """),
                # 明确标识示例区
                MessagesPlaceholder("examples", optional=True),
                # 包含历史所有对话
                *state.messages
            ])

            examples = [
                ("human", "任务的目标：每日工作效率统计。数据加工逻辑：单加一列：工作量除以工作时长为工作效率"),
                ("ai", "{\"data_operation\": \"单加一列：工作量除以工作时长为工作效率\",  \"target\": \"每日工作效率统计\"}"),
            ]

            chain = prompt | self.llm| parser
            response = chain.invoke({
               "examples": examples,
            })

            task_detail = QueryDataTaskDetail.model_validate(response)

            state.task_detail = task_detail

            return state


    # 在用户更新任务模板的过程中，对比模板是否填写完善
    def how_to_improve_task(self, state:State):
        if state.task_detail is not None and state.task_detail.target is not None and state.task_detail.data_operation is not None:
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=f"""
                                        {self.basic_system_template}
                                        用户给出的任务信息是：
                                        任务名称:{state.task_name}
                                        {state.task_detail.to_desc()}

                                        如果用户主动提出要保存任务，你可以使用工具进行保存任务
                                        """),
                *state.messages])

            chain = prompt | self.llm.bind_tools(self.save_task_tool_list)

            response = chain.invoke({})


            return {
                "messages": [response],
            }

        else:
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=f"""
                            {self.basic_system_template}
                            你的任务是对比：
                            任务模板：
                            {default_task_template.to_desc()}
                            当前任务信息：
                            {"无" if state.task_detail is None else state.task_detail.to_desc()}
                            
                            这两者之间的差别。
                            提示用户模板里还有哪些内容是需要填写的，如果确认用户已经全部填写完成，请询问用户是否保存。
                            """),
                *state.messages])

            chain = prompt | self.llm.bind_tools(self.tool_list)

            response = chain.invoke({})

            return {
                "messages": [response],
            }


    # EDGES
    def intent_classifier_to_next(self, state: State) -> Literal[FIND_TASK_IN_DB, CREATE_TASK, QUERY_DATA_NODE, END]:
        if state.intent_type == OTHERS:
            return QUERY_DATA_NODE
        elif state.intent_type in [EXECUTE, EDIT, CREATE, DELETE]:
            return FIND_TASK_IN_DB
        elif state.intent_type == QUERY_DATA:
            return QUERY_DATA_NODE
        else:
            return END

    def check_exist_and_next_node(self, state:State) -> Literal[FIND_TASK_IN_STORE, SAME_NAME_WHEN_CREATE, DELETE_TASK, EXECUTE_TASK, UPDATE_TASK_DETAIL, END]:
        if state.task_detail is None:
            return FIND_TASK_IN_STORE
        else:
            if state.intent_type == CREATE:
                return SAME_NAME_WHEN_CREATE
            elif state.intent_type == EXECUTE:
                return EXECUTE_TASK
            elif state.intent_type == EDIT:
                return UPDATE_TASK_DETAIL
            elif state.intent_type == DELETE:
                return DELETE_TASK
            else:
                return END



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

    def need_invoke_save_task_tool(self, state: State) -> Literal[TOOLS_FOR_SAVE_TASK, END]:
        last_message = state.messages[-1]
        if not isinstance(last_message, AIMessage):
            raise ValueError(
                f"Expected AIMessage in output edges, but got {type(last_message).__name__}"
            )

        if not last_message.tool_calls:
            return END
        else:
            return TOOLS_FOR_SAVE_TASK

    def need_invoke_delete_task_tool(self, state: State) -> Literal[TOOLS_FOR_DELETE_TASK, END]:
        last_message = state.messages[-1]
        if not isinstance(last_message, AIMessage):
            raise ValueError(
                f"Expected AIMessage in output edges, but got {type(last_message).__name__}"
            )

        if not last_message.tool_calls:
            return END
        else:
            return TOOLS_FOR_DELETE_TASK


    # 创建Graph
    def create_graph(self, graph_name):
        builder = StateGraph(State, input_schema=InputState)
        # 新Graph
        builder.add_node(INTENT_CLASSIFIER, self.intent_classifier)
        builder.add_node(QUERY_DATA_NODE, self.query_data)
        builder.add_node(FIND_TASK_IN_DB, self.find_task_in_db)
        builder.add_node(FIND_TASK_IN_STORE, self.find_task_in_store)
        builder.add_node(EXECUTE_TASK, self.execute_task)
        builder.add_node(CREATE_TASK, self.create_task)
        builder.add_node(TOOLS_FOR_TASK, ToolNode(self.tool_list))
        builder.add_node(TOOLS_FOR_QUERY_DATA, ToolNode(self.tool_list))
        builder.add_node(HOW_TO_IMPROVE_TASK, self.how_to_improve_task)
        builder.add_node(TOOLS_FOR_SAVE_TASK, ToolNode(self.save_task_tool_list))
        builder.add_node(SAME_NAME_WHEN_CREATE, self.same_name_when_create)
        builder.add_node(DELETE_TASK, self.delete_task)
        builder.add_node(EDIT_TASK, self.edit_task)
        builder.add_node(UPDATE_TASK_DETAIL, self.update_task_detail)
        builder.add_node(TOOLS_FOR_DELETE_TASK, ToolNode(self.delete_task_tool_list))

        # 起始节点，判断意图
        builder.add_edge(START, INTENT_CLASSIFIER)
        builder.add_conditional_edges(INTENT_CLASSIFIER, self.intent_classifier_to_next)
        builder.add_conditional_edges(FIND_TASK_IN_DB, self.check_exist_and_next_node)
        builder.add_edge(FIND_TASK_IN_STORE, EXECUTE_TASK)
        builder.add_edge(TOOLS_FOR_TASK, EXECUTE_TASK)
        builder.add_edge(TOOLS_FOR_QUERY_DATA, QUERY_DATA_NODE)
        builder.add_conditional_edges(EXECUTE_TASK, self.need_invoke_tool)
        builder.add_conditional_edges(QUERY_DATA_NODE, self.need_invoke_tool)
        builder.add_edge(CREATE_TASK, HOW_TO_IMPROVE_TASK)
        builder.add_conditional_edges(HOW_TO_IMPROVE_TASK, self.need_invoke_save_task_tool)
        builder.add_edge(TOOLS_FOR_SAVE_TASK, END)
        builder.add_edge(HOW_TO_IMPROVE_TASK, END)
        builder.add_edge(SAME_NAME_WHEN_CREATE, END)
        builder.add_edge(UPDATE_TASK_DETAIL, EDIT_TASK)
        builder.add_conditional_edges(EDIT_TASK, self.need_invoke_save_task_tool)
        builder.add_conditional_edges(DELETE_TASK, self.need_invoke_delete_task_tool)


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
           stream_mode=["messages", "tasks"])

        return stream



    async def question(self, query, session_id) -> str:
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

    def resume(self, resume_type, session_id) -> str:
        # 上下文配置
        config = {"configurable": {"thread_id": session_id}}

        res = self.graph.invoke(
            Command(resume=[{"resumeType": resume_type}]),
            config = config,
        )

        last_msg = res["messages"][-1]
        if isinstance(last_msg, ToolMessage):
            return last_msg.content
        else:
            return "error"

def create_workflow(workplace: Workplace, work_group: WorkGroup) -> WorkflowService:
    workflow_service = WorkflowService(workplace, work_group)

    workflow_map[f"{workplace.code}_{work_group.code}"] = workflow_service
    return workflow_service

def get_workflow(workplace_code, work_group_code) -> WorkflowService:
    workflow_service = workflow_map[f"{workplace_code}_{work_group_code}"]
    return workflow_service



def add_human_in_the_loop(
    tool: Callable | BaseTool,
    confirm_type:str,
    tool_input_2_desc: Callable[[{}], str],
    interrupt_config: HumanInterruptConfig = None,
) -> BaseTool:
    """Wrap a tool to support human-in-the-loop review."""
    if not isinstance(tool, BaseTool):
        tool = create_tool(tool)

    if interrupt_config is None:
        interrupt_config = {
            "allow_accept": True,
            "allow_edit": True,
            "allow_respond": True,
        }

    @create_tool(
        tool.name,
        description=tool.description,
        args_schema=tool.args_schema
    )
    def call_tool_with_interrupt(config: RunnableConfig, **tool_input):
        args = dict(tool_input)
        args["confirm_type"] = confirm_type
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

@tool
def save_task(id:int, task_name, task_target, data_operation, workplace_code, work_group_code) -> bool:
    """
       保存任务信息，结果返回是否保存成功

       输入参数：
       id：任务唯一id
       task_name：任务名称
       task_target：任务目标
       data_operation：调用工具后的加工逻辑
       workplace_code：工作点编码
       work_group_code：工作组编码
   """
    business_key = f"{workplace_code}_{work_group_code}"

    json_str = json.dumps(QueryDataTaskDetail(target=task_target, data_operation=data_operation).to_dict(), ensure_ascii=False)
    entity = QueryDataTaskEntity(
        name = task_name,
        business_key=business_key,
        task_detail= json_str
    )

    if id is not None:
        entity.id = id
    query_data_task_dao.save(entity)

    return True

@tool
def logical_delete_task(id:int, task_name, workplace_code, work_group_code):
    """
       删除任务信息，结果返回是否删除成功

       输入参数：
       id：任务唯一id
       task_name：任务名称
       workplace_code：工作点编码
       work_group_code：工作组编码
   """
    business_key = f"{workplace_code}_{work_group_code}"
    query_data_task_dao.delete(id, business_key)

    return True