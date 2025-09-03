import json
import logging
import os
import queue
import threading
import time
from typing import Callable
from typing import List
from typing import Literal
from typing import Optional, cast

from langchain.output_parsers import OutputFixingParser
from langchain_core.callbacks import BaseCallbackHandler, CallbackManager
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool as create_tool
from langchain_core.tools import tool
from langchain_deepseek import ChatDeepSeek
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.interrupt import HumanInterruptConfig, HumanInterrupt
from langgraph.types import interrupt, Command, Interrupt
from pydantic import BaseModel, Field

from dao import query_data_task_dao
from entity.query_data_task_entity import QueryDataTaskEntity
from model.query_data_task_detail import QueryDataTaskDetail
from service.agent.model.interrupt import WorkflowInterrupt
from service.agent.model.json_output_schema import QUERY_DATA, EXECUTE, CREATE, EDIT, DELETE, OTHERS, IntentSchema, \
    TaskSchema
from service.agent.model.resume import WorkflowResume
from service.agent.model.state import State, InputState
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
BEFORE_TEST_RUN_OR_SAVE = "before_test_run_or_save" # 中断前的空节点，避免重放流
SAVE_TASK = "save_task" # 保存任务
TEST_RUN_TASK= "test_run_task" # 试跑任务
AFTER_EXECUTE_TASK = "after_execute_task"


# 记录有AI逐步返回token返回的节点
AI_CHAT_NODES = [EXECUTE_TASK, QUERY_DATA_NODE, HOW_TO_IMPROVE_TASK, DELETE_TASK, TEST_RUN_TASK]
# 记录人工构造AI MSG
AI_MSG_NODES = [SAME_NAME_WHEN_CREATE]

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
        data_operation="无。(请详细描述，查询到结果之后希望进行哪些加工处理)"
    )


class CustomCallbackHandler(BaseCallbackHandler):
    def on_chain_start(self, serialized, inputs, **kwargs):
        print(f"开始执行: {serialized.get('name')}")

    def on_chain_end(self, outputs, **kwargs):
        print(f"执行完成，输出: {outputs}")

    def on_chain_error(self, error, **kwargs):
        print(f"执行错误: {error}")

class WorkflowService:
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

    def __init__(self, workflow_name, business_key:str, basic_system_template:str, business_tool_list:[]):
        self.business_key = business_key

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

        self.basic_system_template = basic_system_template

        # 设置业务用所有工具方法
        self.business_tool_list = [*business_tool_list, execute_once]

        # 删除任务的工具
        self.delete_task_tool_list = [add_human_in_the_loop(logical_delete_task, [WorkflowResume(resume_type="accept", resume_desc="删除", resume_mode="invoke")], lambda tool_input: f"是否确定要删除任务：{tool_input["task_name"]}?")]

        # 初始化langGraph
        self.graph = self.create_graph(workflow_name)

    def create_graph(self, graph_name):
        """
        创建Graph
        :param graph_name:
        :return: graph
        """
        builder = StateGraph(State, input_schema=InputState)
        # 新Graph
        builder.add_node(INTENT_CLASSIFIER, self.intent_classifier)
        builder.add_node(QUERY_DATA_NODE, self.query_data)
        builder.add_node(FIND_TASK_IN_DB, self.find_task_in_db)
        builder.add_node(FIND_TASK_IN_STORE, self.find_task_in_store)
        builder.add_node(EXECUTE_TASK, self.execute_task)
        builder.add_node(CREATE_TASK, self.create_task)
        builder.add_node(TOOLS_FOR_TASK, ToolNode(self.business_tool_list))
        builder.add_node(TOOLS_FOR_QUERY_DATA, ToolNode(self.business_tool_list))
        builder.add_node(HOW_TO_IMPROVE_TASK, self.how_to_improve_task)
        builder.add_node(SAME_NAME_WHEN_CREATE, self.same_name_when_create)
        builder.add_node(DELETE_TASK, self.delete_task)
        builder.add_node(EDIT_TASK, self.edit_task)
        builder.add_node(TOOLS_FOR_DELETE_TASK, ToolNode(self.delete_task_tool_list))
        builder.add_node(TEST_RUN_TASK, self.test_run_task)
        builder.add_node(SAVE_TASK, self.save_task)
        builder.add_node(BEFORE_TEST_RUN_OR_SAVE, self.before_test_run_or_save)

        # 起始节点，判断意图
        builder.add_edge(START, INTENT_CLASSIFIER)
        builder.add_conditional_edges(INTENT_CLASSIFIER, self.intent_classifier_to_next)
        builder.add_conditional_edges(FIND_TASK_IN_DB, self.check_exist_and_next_node)
        builder.add_conditional_edges(FIND_TASK_IN_STORE, self.check_exist_in_store_and_next_node)
        builder.add_conditional_edges(TOOLS_FOR_TASK, self.after_invoke_tool)
        builder.add_edge(TOOLS_FOR_QUERY_DATA, QUERY_DATA_NODE)
        builder.add_conditional_edges(EXECUTE_TASK, self.need_invoke_tool)
        builder.add_conditional_edges(QUERY_DATA_NODE, self.need_invoke_tool)
        builder.add_edge(CREATE_TASK, HOW_TO_IMPROVE_TASK)
        builder.add_edge(HOW_TO_IMPROVE_TASK, BEFORE_TEST_RUN_OR_SAVE)
        builder.add_conditional_edges(BEFORE_TEST_RUN_OR_SAVE, self.handle_integrated_task)
        builder.add_edge(SAME_NAME_WHEN_CREATE, END)
        builder.add_edge(EDIT_TASK, HOW_TO_IMPROVE_TASK)
        builder.add_conditional_edges(DELETE_TASK, self.need_invoke_delete_task_tool)
        builder.add_conditional_edges(TEST_RUN_TASK, self.need_invoke_tool)
        builder.add_edge(SAVE_TASK, END)

        # 记忆功能
        memory = InMemorySaver()
        graph = builder.compile(name=graph_name, checkpointer=memory)

        # todo 为什么没有打印出来？
        try:
            print(graph.get_graph().draw_ascii())
        except Exception:
            # This requires some extra dependencies and is optional
            pass

        return graph

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

        stream = self.graph.stream(
            input=InputState(messages=[("user", query)]),
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
    def intent_classifier(self, state: State):
        """
        意图判断节点
        :param state:
        :return: state
        """
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
        parser_with_llm = OutputFixingParser.from_llm(parser=parser, llm=self.llm)
        chain = intent_prompt | self.llm | parser_with_llm

        result = chain.invoke({
            "examples": examples,
        })

        # 更新状态
        intent_type = result["intent_type"]

        logging.info("推断出的intent_type:%s, result:%s", intent_type, result)

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


    def find_task_in_db(self, state: State):
        """
        根据任务名称/任务id查找任务详情
        :param state:
        :return:state
        """
        query_data_task = find_task_by_id_or_name(state.task_id, state.task_name, self.business_key)

        if query_data_task is not None:
            state.is_task_existed = True

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
        # todo 实现向量存储查询
        return state

    def execute_task(self, state:State):
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
            chain = prompt | self.llm.bind_tools(self.business_tool_list)
            response = chain.invoke({})
            return {
                "messages": [response],
            }
        else:
            last_human_message = state.messages[-1].content

            # 初次调用，使用原始用户查询
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=f"""
                {self.basic_system_template}

                任务ID:{state.task_id}
                                
                任务详情:
                {state.task_detail.to_desc()}
                
                注意：每次执行完任务的最后，一定要调用工具，传入任务id，把任务的执行次数加1
                """
                              ),
                HumanMessage(content="{user_input}")  # 用户最后一条消息
            ])

            chain = prompt | self.llm.bind_tools(self.business_tool_list)
            response = chain.invoke({"user_input": last_human_message})
            return {
                "messages": [response],
            }

    def query_data(self, state: State):
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
        response = chain.invoke({})

        return {
            "messages": [response],
        }

    def same_name_when_create(self, state:State):
        """
        创建任务时找到同名任务回复给用户
        :param state:
        :return:state
        """
        response = ("ai", f"查找到与【{state.task_name}】同名任务，是否修改该任务？")
        return {
            "messages": [cast(AIMessage, response)],
        }

    def edit_task(self, state: State):
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
        response = chain.invoke({
            "examples": examples,
        })

        task_detail = QueryDataTaskDetail.model_validate(response)

        if state.task_detail.to_dict() != task_detail.to_dict():
            state.task_detail = task_detail
        return state


    def delete_task(self, state:State):
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

        response = chain.invoke({})

        return {
            "messages": [response],
        }

    def create_task(self, state:State):
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
                ("human", "任务的目标：每日工作效率统计。数据加工逻辑：单加一列：工作量除以工作时长为工作效率"),
                ("ai", "{\"data_operation\": \"单加一列：工作量除以工作时长为工作效率\",  \"query_param\":\"查询昨天的数据\", \"target\": \"每日工作效率统计\"}"),
            ]

            chain = prompt | self.llm| parser
            response = chain.invoke({
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
            id = query_data_task_dao.save(entity)
        else:
            id = query_data_task_dao.save(entity)

        return {
            "task_id": id,
            "query_data_task": True,
            "intent_type": EDIT,
            "messages": [("ai", f"{state.task_name}保存成功")]
        }


    def test_run_task(self, state:State):
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
                
                只用返回按用户要求进行数据加工之后的结果。
                
                """),
                *all_messages  # 包含所有历史消息
            ])

            chain = prompt | self.llm.bind_tools(self.business_tool_list)
            response = chain.invoke({})
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
            response = chain.invoke({})

        return {
            "messages": [response],
            }


    def how_to_improve_task(self, state:State):
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

        response = chain.invoke({})

        return {
            "messages": [response],
        }

    def before_test_run_or_save(self, state: State):
        """
        空节点，避免中断恢复后重新执行前一个节点的流式输出
        :param state:
        :return:
        """
        return state

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

    def check_exist_and_next_node(self, state:State) -> Literal[FIND_TASK_IN_STORE, SAME_NAME_WHEN_CREATE, DELETE_TASK, EXECUTE_TASK, EDIT_TASK, END]:
        if not state.is_task_existed:
            return FIND_TASK_IN_STORE
        else:
            if state.intent_type == CREATE:
                return SAME_NAME_WHEN_CREATE
            elif state.intent_type == EXECUTE:
                return EXECUTE_TASK
            elif state.intent_type == EDIT:
                return EDIT_TASK
            elif state.intent_type == DELETE:
                return DELETE_TASK
            else:
                return END

    def check_exist_in_store_and_next_node(self, state:State) -> Literal[SAME_NAME_WHEN_CREATE, DELETE_TASK, EXECUTE_TASK, CREATE_TASK, EDIT_TASK, END]:
        if not state.is_task_existed:
            if state.intent_type == CREATE:
                return CREATE_TASK
            elif state.intent_type == EXECUTE:
                return CREATE_TASK
            elif state.intent_type == EDIT:
                return CREATE_TASK
            elif state.intent_type == DELETE:
                return CREATE_TASK
            else:
                return END
        else:
            if state.intent_type == CREATE:
                return SAME_NAME_WHEN_CREATE
            elif state.intent_type == EXECUTE:
                return EXECUTE_TASK
            elif state.intent_type == EDIT:
                return EDIT_TASK
            elif state.intent_type == DELETE:
                return DELETE_TASK
            else:
                return END



    def need_invoke_tool(self, state:State) -> Literal[TOOLS_FOR_TASK, TOOLS_FOR_QUERY_DATA, HOW_TO_IMPROVE_TASK, SAVE_TASK, TEST_RUN_TASK, END]:
        last_message = state.messages[-1]
        if not isinstance(last_message, AIMessage):
            raise ValueError(
                f"Expected AIMessage in output edges, but got {type(last_message).__name__}"
            )

        if not last_message.tool_calls:
            # 如果任务已经执行完毕，再次循环到试跑/保存的中断
            if state.intent_type == EDIT or state.intent_type == CREATE:
                return self.handle_integrated_task(state)
            # elif state.intent_type == EXECUTE:
            #     return AFTER_EXECUTE_TASK
            else:
                return END
        elif state.intent_type == EXECUTE:
            return TOOLS_FOR_TASK
        elif state.intent_type == QUERY_DATA or state.intent_type == OTHERS:
            return TOOLS_FOR_QUERY_DATA
        elif state.intent_type == EDIT or state.intent_type == CREATE:
            return TOOLS_FOR_TASK
        else:
            return END

    def after_invoke_tool(self, state:State)-> Literal[EXECUTE_TASK, TEST_RUN_TASK, END]:
        if state.intent_type == EXECUTE:
            return EXECUTE_TASK
        elif state.intent_type == EDIT or state.intent_type == CREATE:
            return TEST_RUN_TASK
        else:
            return END

    def handle_integrated_task(self, state:State) -> Literal[SAVE_TASK, TEST_RUN_TASK,END]:
        if state.task_detail is not None and state.task_detail.is_integrated():
            request: HumanInterrupt = {
                "action_request": {
                    "action": 'handle_integrated_task',
                    "args":{
                        "task_name":state.task_name,
                        "confirm_option_list":[WorkflowResume(resume_type="testRun", resume_desc="试跑", resume_mode="stream"), WorkflowResume(resume_type="save", resume_desc="保存", resume_mode="invoke")]
                    }
                },
                "config": DEFAULT_INTERRUPT_CONFIG,
                "description": "任务信息已填写完整，请问接下来希望进行哪一步操作?"
            }
            response = interrupt(request)[0]
            if response["resumeType"] == "save":
                return SAVE_TASK
            elif response["resumeType"] == "testRun":
                return TEST_RUN_TASK
            elif response["resumeType"] == "cancel":
                return END
        else:
            return END


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




    def get_frequently_and_usually_execute_tasks(self) -> set[str]:
        """
        获取最频繁/最近执行过的任务名称
        :return:任务名称列表
        """
        usually_execute_tasks = query_data_task_dao.get_usually_execute_top3_tasks(self.business_key)

        names = set()
        not_in_ids = []
        for t in usually_execute_tasks:
            names.add(t.name)
            not_in_ids.append(t.id)

        frequently_execute_tasks = query_data_task_dao.get_frequently_execute_top3_tasks(self.business_key, not_in_ids)

        for t in frequently_execute_tasks:
            names.add(t.name)

        return names

    def get_event_stream_function(self, input, session_id, stream_type:Literal["question", "resume"]):
        """
        获取流式方法，这个方法直接返回给前端使用
        :param input:
        :param session_id:
        :param stream_type; 是提问还是中断的回复
        :return: event_stream
        """
        def event_stream():

            # 为每个请求创建专用队列
            data_queue = queue.Queue()

            def run_workflow():
                try:
                    if stream_type == "question":
                        stream = self.stream_question(input, session_id)
                    else:
                        stream = self.stream_resume(input, session_id)

                    for stream_mode, detail in stream:
                        if stream_mode == "messages":
                            chunk, metadata = detail
                            if metadata['langgraph_node'] in AI_CHAT_NODES:
                                # print("question", stream_mode, detail)
                                content = chunk.content
                                data_queue.put({"token": content})
                        elif stream_mode == "tasks":
                            # print("question", stream_mode, detail)
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

        return event_stream


def get_tasks_mode_ai_msg_content(detail) -> str | None:
    """
    解析返回结构里强行解析消息内容（没想到更好的办法）
    :param detail:
    :return:
    """
    if "result" in detail:
        msgs = detail["result"][0]
        if msgs[0] == "messages":
            msg_list = msgs[1]
            for m in msg_list:
                if m[0] == "ai":
                    return m[1]
    return None


def create_workflow(workflow_name, business_key, basic_system_template, business_tool_list) -> WorkflowService:
    """
    创建并缓存工作流
    # Todo 记忆使用分布式缓存存储后，工作流缓存可放置到分布式缓存中
    :param workflow_name: 工作流名称
    :param business_key: 业务键
    :param basic_system_template:基础系统提示词
    :param business_tool_list: 业务工具列表
    :return: 工作流实例
    """
    workflow_service = WorkflowService(workflow_name, business_key, basic_system_template, business_tool_list)
    workflow_map[business_key] = workflow_service
    return workflow_service

def get_workflow(business_key) -> WorkflowService|None:
    """
    根据业务键从缓存中获取工作流实例
    :param business_key:
    :return:工作流实例
    """
    if business_key not in workflow_map:
        return None
    else:
        workflow_service = workflow_map[business_key]
        return workflow_service

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


def find_task_by_id_or_name(task_id:int, task_name:str|None, business_key:str) -> QueryDataTaskEntity:
    """
    根据按优先级根据task_id,task_name查询db中的任务对象
    :param task_id:
    :param task_name:
    :param business_key:业务键
    :return: 任务对象
    """
    if task_id is not None:
        entity = query_data_task_dao.find_by_id(task_id)
    elif task_name is not None:
        entity = query_data_task_dao.find_by_name(business_key, task_name)
    else:
        entity = None

    return entity


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


@tool
def logical_delete_task(id:int, task_name, business_key:str):
    """
       删除任务信息，结果返回是否删除成功

       输入参数：
       id：任务唯一id
       task_name：任务名称
       business_key：业务键
   """
    query_data_task_dao.delete(id, business_key)

    return True

@tool
def execute_once(id:int, business_key:str):
    """
          当执行任务时，把执行任务的次数+1

          输入参数：
          id：任务唯一id
          business_key：业务键
      """
    query_data_task_dao.update_execute_times_once(id, business_key)