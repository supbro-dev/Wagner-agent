from __future__ import annotations

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
from langchain_core.runnables import RunnableConfig
from langchain_deepseek import ChatDeepSeek
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_store
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.graph import add_messages
from langgraph.managed import IsLastStep
from langgraph.prebuilt import ToolNode
from langgraph.store.memory import InMemoryStore
from typing_extensions import Annotated

from dao import ai_example_dao
from entity.ai_example_entity import AiExampleEntity
from model.work_group import WorkGroup
from model.workplace import Workplace
from service.example import ExampleTemplate, ToolInvoke
from service.wagner_tool_service import get_employee, get_group_employee, get_employee_time_on_task, \
    get_employee_efficiency
from util import datetime_util
from util.config_util import read_private_config

workflow_map = {}


# NODE_NAMES
CALL_MODEL = "call_model"
TOOLS = "tools"

@dataclass
class InputState:

    messages: Annotated[Sequence[AnyMessage], add_messages] = field(
        default_factory=list
    )


@dataclass
class State(InputState):

    is_last_step: IsLastStep = field(default=False)


def create_system_prompt(workplace, work_group):
    current_date = datetime_util.format_datatime(datetime.now())


    example_key = f"{workplace.code}_{work_group.code}"
    example_list = ai_example_dao.find_by_key(example_key)

    example_str_list :List[str] = []
    if len(example_list) > 0:
        for example in example_list:
            example_str_list.append(f"1. 用户提问：{example.human_message}")
            if example.tool_message is not None:
                example_str_list.append(f"2. 工具调用：{example.tool_message}")
            if example.tool_detail is not None:
                tool_detail_list = json.loads(example.tool_detail)
                for i in range(len(tool_detail_list)):
                    detail = tool_detail_list[i]
                    example_str_list.append(f"行动{i + 1}")
                    example_str_list.append(f"\tAction: {detail["tool_name"]}")
                    example_str_list.append(f"\tAction Input: {detail["invoke_args"]}")
                    example_str_list.append(f"\tAction Response: {detail["tool_res"]}")
            if example.data_operation is not None:
                example_str_list.append(f"4.数据加工逻辑: {example.data_operation}")
            example_str_list.append(f"5. AI返回: {example.ai_message}")

    example_template = "\n".join(example_str_list)

    system_template = (
        f"你的角色是{workplace.name}这个工作点的一名工作组:{work_group.name}的组长助理，该小组的工作岗位是:{work_group.position_name}。"
        f"{workplace.name}的工作点编码是{workplace.code}，具体介绍是【{workplace.desc}】。"
        f"你管理的小组的小组编码是:{work_group.code}，具体介绍是【{work_group.desc}】。"
        "你的日常工作就是辅助你的小组长一起管理这个小组，所有员工信息、员工出勤情况、作业数据、作业情况都会由专门的工具获取，不要随便编造数据。"
        f"当前日期是{current_date}"
        "所有需要根据工号查询的工具，都需要提前调用其他工具查询获取组员的工号"
        "解释一下一个特殊概念：AA问题。AA问题指的两个问题从语法上类似，可能都需要调用相同的工具，只是调用工具传入的参数不同"
        """
        1. 用户提问: 用户的问题
        2. 工具调用: 调用了哪些工具
        3. 行动: 如果需要使用了工具，会按照以下格式调用工具（可能有多条）
            Action: 工具名称
            Action Input: 工具的输入
            Action Response: 工具的返回
        4. 数据加工逻辑: 得到工具的返回之后需要怎么进行二次加工
        5. AI返回: 加工之后的数据根据确定的格式返回给用户
        
        """
        # """
        #     以下是一些示例：
        #
        #     示例1：
        #     用户：小组组员7.24工作效率是多少
        #     思考：根据小组编码查询小组组员的工号，再根据工号、日期查询小组组员的工作效率
        #     行动1：
        #        Action: get_group_employee
        #        Action Input: workplace_code=工作点编码, work_group_code=工作组编码
        #        Action Response：姓名:张三，工号:B1010，所属工作点编码:某个确定的工作点编码，所属工作组编码:某个确定的工作组编码
        #     行动2：
        #        Action: get_employee_efficiency
        #        Action Input: workplace_code=工作点编码, employee_number_list=员工工号(英文逗号分隔), operate_day具体日期(YYYY-MM-DD格式)
        #        Action Response：
        #            2025-07-24，张三在拣选环节上完成工作量{包裹数:60}, 工作1.5小时, 闲置2.5小时
        #            2025-07-24，张三在质检环节上工作2.1小时, 闲置0.5小时
        #        然后，当工具返回后，你只需要给用户返回（类似excel表头+数据）：
        #            日期\t员工\t环节\t工作量\t工作工时(小时)\t休息工时(小时)\t闲置工时(小时)
        #            2025-07-24\t张三\t拣选\t包裹数:60\t1.5\t\t2.5
        #            2025-07-24\t张三\t之间\t\t2.1\t\t0.5
        #     """
    )
    if len(example_str_list) > 0:
        system_template += "以下是示例:\n"
        system_template += example_template
    return system_template


class WorkflowService:
    def __init__(self, workplace: Workplace, work_group: WorkGroup):
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

        # 初始化系统提示词
        self.system_prompt = create_system_prompt(workplace, work_group)

        # 初始化工具列表
        self.tool_list = [get_employee, get_group_employee, get_employee_time_on_task, get_employee_efficiency]

        # 初始化langGraph
        self.graph = self.create_graph("work_group_agent", use_memory = True)
        self.train_graph = self.create_graph("train_agent")


    async def call_work_group_model(self, state: State) -> Dict[str, List[AIMessage]]:
        # Initialize the model with tool binding. Change the model or add more tools here.
        model = self.llm.bind_tools(self.tool_list)

        # Format the system prompt. Customize this to change the agent's behavior.
        system_message = self.system_prompt

        # Get the model's response
        response = cast(
            AIMessage,
            await model.ainvoke(
                [{"role": "system", "content": system_message}, *state.messages]
            ),
        )

        # Handle the case when it's the last step and the model still wants to use a tool
        if state.is_last_step and response.tool_calls:
            return {
                "messages": [
                    AIMessage(
                        id=response.id,
                        content="Sorry, I could not find an answer to your question in the specified number of steps.",
                    )
                ]
            }

        # Return the model's response as a list to be added to existing messages
        return {"messages": [response]}

    # 创建Graph
    def create_graph(self, graph_name, use_memory:bool = False):
        builder = StateGraph(State, input_schema=InputState)


        builder.add_node(CALL_MODEL, self.call_work_group_model)
        builder.add_node(TOOLS, ToolNode(self.tool_list))

        builder.add_edge(START, CALL_MODEL)


        builder.add_conditional_edges(
            CALL_MODEL,

            self.route_model_output,
        )

        # Add a normal edge from `tools` to `call_model`
        # This creates a cycle: after using tools, we always return to the model
        builder.add_edge(TOOLS, CALL_MODEL)

        # Compile the builder into an executable graph
        if use_memory:
            # 记忆功能
            memory = InMemorySaver()
            graph = builder.compile(name=graph_name, checkpointer = memory)
        else:
            graph = builder.compile(name=graph_name)

        return graph

    async def question(self, query, session_id) -> (str, str, str):
        # 上下文配置
        config = {"configurable": {"thread_id": session_id}}

        res = await self.graph.ainvoke(
            input = {"messages": [("user", query)]},
            config = config,
        )

        result = res["messages"][-1]
        content = str(result.content)
        id = str(result.id)

        if content == "":
            print("content is empty:", result)

        last_human_message_id = 0
        for i in range(len(res["messages"]) - 1, -1, -1):
            message = res["messages"][i]
            if isinstance(message, HumanMessage):
                last_human_message_id = message.id
                break

        return content, id, last_human_message_id

    # 是否为第一次提问的标识
    IS_ASK_SAME_QUESTION_BEFORE_FLAG = "N"

    # 训练AI助手
    def train(self, session_id, human_msg_id, human_content, ai_msg_id, ai_content):
        # 上下文配置
        config = {"configurable": {"thread_id": session_id}}
        state = self.graph.get_state(config = config)

        messages = state.values["messages"]

        # is_same, _, _ = asyncio.run(self.question(
        #     f"我提的这个问题:{human_content}\n之前我是否也提问这个问题的AA问题?",
        #     session_id))
        #
        # print(is_same)

        is_first_question_str, _, _ = asyncio.run(self.question(f"我提的这个问题:{human_content}\n之前我是否提问这个问题的AA问题？如果没提问过，请回答{self.IS_ASK_SAME_QUESTION_BEFORE_FLAG}；如果提问过，告诉我从第一次提出该AA问题，到你最终回答:{ai_content}\n中间的加工逻辑用简短语言概括一下。", session_id))

        is_first_question = is_first_question_str != self.IS_ASK_SAME_QUESTION_BEFORE_FLAG

        # 如果只提问了一次相关问题
        if is_first_question:
            example_template = self.__handle_invoke_once(messages, human_msg_id, ai_msg_id)
            self.__save_example(example_template)

    def __handle_invoke_once(self, messages, human_msg_id, ai_msg_id) -> ExampleTemplate:
        example_template = ExampleTemplate()
        tool_invoke = ToolInvoke()
        for i in range(len(messages)):
            message = messages[i]
            if isinstance(message, HumanMessage) and message.id == human_msg_id:
                example_template.human_input = message.content
            elif isinstance(message, AIMessage) and message.id == ai_msg_id:
                example_template.ai_output = message.content
                # 遍历到ai_msg_id直接退出
                break
            else:# 处理调用tool和toolMessage
                # 工具调用
                if isinstance(message, AIMessage):
                    tool_name = message.tool_calls[0]["name"]
                    tool_invoke.tool_name = tool_name
                    tool_invoke.invoke_args = message.tool_calls[0]["args"]
                    example_template.use_tools.append(tool_name)
                # 如果已经遍历了human_msg_id
                if example_template.human_input != "" and isinstance(message, ToolMessage):
                    tool_invoke.tool_res = message.content
                    example_template.tool_invoke_list.append(tool_invoke)
                    tool_invoke = ToolInvoke()

        return example_template




    def __save_example(self, example_template: ExampleTemplate):
        example_key = f"{self.workplace.code}_{self.work_group.code}"

        list = ai_example_dao.find_by_key(example_key)

        max_sort_index = 0
        for ex in list:
            max_sort_index = max(max_sort_index, ex.sort_index)

        entity = AiExampleEntity()
        entity.key = example_key
        entity.human_message = example_template.human_input
        entity.ai_message = example_template.ai_output
        entity.tool_message = example_template.use_tools

        detail_array = json.dumps(
            [detail.model_dump() for detail in example_template.tool_invoke_list],
            indent=2
        )
        entity.tool_detail = detail_array
        entity.sort_index = max_sort_index + 1

        ai_example_dao.insert(entity)


    def route_model_output(self, state: State) -> Literal[END, TOOLS]:
        last_message = state.messages[-1]
        if not isinstance(last_message, AIMessage):
            raise ValueError(
                f"Expected AIMessage in output edges, but got {type(last_message).__name__}"
            )
        # If there is no tool call, then we finish
        if not last_message.tool_calls:
            return END
        # Otherwise we execute the requested actions
        return TOOLS


def create_workflow(workplace: Workplace, work_group: WorkGroup) -> WorkflowService:
    workflow_service = WorkflowService(workplace, work_group)

    workflow_map[f"{workplace.code}_{work_group.code}"] = workflow_service
    return workflow_service

def get_workflow(workplace_code, work_group_code) -> WorkflowService:
    workflow_service = workflow_map[f"{workplace_code}_{work_group_code}"]
    return workflow_service
