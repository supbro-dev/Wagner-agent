from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated
from typing import Dict, Literal
from typing import List, Optional, cast
from typing import Sequence

from langchain_core.messages import AIMessage
from langchain_core.messages import AnyMessage
from langchain_deepseek import ChatDeepSeek
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.graph import add_messages
from langgraph.managed import IsLastStep
from langgraph.prebuilt import ToolNode
from typing_extensions import Annotated

from dao import ai_example_dao
from model.work_group import WorkGroup
from model.workplace import Workplace
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
    # example_list = ai_example_dao.find_by_key(example_key)
    # print(example_list)

    return  (
        f"你的角色是{workplace.name}这个工作点的一名工作组:{work_group.name}的组长助理，该小组的工作岗位是:{work_group.position_name}。"
        f"{workplace.name}的工作点编码是{workplace.code}，具体介绍是【{workplace.desc}】。"
        f"你管理的小组的小组编码是:{work_group.code}，具体介绍是【{work_group.desc}】。"
        "你的日常工作就是辅助你的小组长一起管理这个小组，所有员工信息、员工出勤情况、作业数据、作业情况都会由专门的工具获取，不要随便编造数据。"
        f"当用户提到相对日期（如'昨天'、'上周'）时，请将其转换为YYYY-MM-DD格式后再调用工具。当前日期是{current_date}"
        "所有需要根据工号查询的工具，都需要提前调用其他工具查询获取组员的工号"
        "返回值用纯文本，不要使用Markdown格式"
        """
        1. 用户：用户的问题
        2. 思考：根据对话历史和当前问题，思考需要做什么。
        3. 行动：如果需要使用工具，请按照以下格式调用工具：
            Action: 工具名称
            Action Input: 工具的输入
            Action Response: 工具的返回
        4. 得到工具返回后，请将结果根据确定的格式返回给用户。
        
        以下是一些示例：

        示例1：
        用户：小组组员7.24工作效率是多少
        思考：根据小组编码查询小组组员的工号，再根据工号、日期查询小组组员的工作效率
        行动1：
           Action: get_group_employee
           Action Input: workplace_code=工作点编码, work_group_code=工作组编码
           Action Response：姓名:张三，工号:B1010，所属工作点编码:某个确定的工作点编码，所属工作组编码:某个确定的工作组编码
        行动2：
           Action: get_employee_efficiency
           Action Input: workplace_code=工作点编码, employee_number_list=员工工号(英文逗号分隔), operate_day具体日期(YYYY-MM-DD格式)
           Action Response：
               2025-07-24，张三在拣选环节上完成工作量{包裹数:60}, 工作1.5小时, 闲置2.5小时
               2025-07-24，张三在质检环节上工作2.1小时, 闲置0.5小时
           然后，当工具返回后，你只需要给用户返回（类似excel表头+数据）：
               日期\t员工\t环节\t工作量\t工作工时(小时)\t休息工时(小时)\t闲置工时(小时)
               2025-07-24\t张三\t拣选\t包裹数:60\t1.5\t\t2.5
               2025-07-24\t张三\t之间\t\t2.1\t\t0.5
        """
    )


class WorkflowService:
    def __init__(self, workplace: Workplace, work_group: WorkGroup):
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
        self.graph = self.create_graph()

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

    def create_graph(self):
        # 记忆功能
        memory = InMemorySaver()
        # Define a new graph
        builder = StateGraph(State, input_schema=InputState)

        # Define the two nodes we will cycle between
        builder.add_node(CALL_MODEL, self.call_work_group_model)
        builder.add_node(TOOLS, ToolNode(self.tool_list))

        # Set the entrypoint as `call_model`
        # This means that this node is the first one called
        builder.add_edge(START, CALL_MODEL)

        # Add a conditional edge to determine the next step after `call_model`
        builder.add_conditional_edges(
            CALL_MODEL,
            # After call_model finishes running, the next node(s) are scheduled
            # based on the output from route_model_output
            self.route_model_output,
        )

        # Add a normal edge from `tools` to `call_model`
        # This creates a cycle: after using tools, we always return to the model
        builder.add_edge(TOOLS, CALL_MODEL)

        # Compile the builder into an executable graph
        graph = builder.compile(name="ReAct Agent", checkpointer = memory)

        return graph

    async def question(self, query, session_id) -> str:
        # 上下文配置
        config = {"configurable": {"thread_id": session_id}}

        res = await self.graph.ainvoke(
            input = {"messages": [("user", query)]},
            config = config,
        )

        content = str(res["messages"][-1].content).lower()

        return content



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