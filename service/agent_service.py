import os
from datetime import datetime
from typing import Optional, Any, List

from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool
from langchain.agents import Agent, create_tool_calling_agent, AgentExecutor
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, FewShotChatMessagePromptTemplate, MessagesPlaceholder
from langchain_deepseek import ChatDeepSeek

from model.employee import Employee
from model.time_on_task import Scheduling, TimeOnTask, Attendance, Rest, ProcessDuration
from model.work_group import WorkGroup
from model.workplace import Workplace
from service.example import group_examples
from util import http_util, datetime_util
from util.config_util import read_private_config
from util.http_util import http_get
from service.wagner_tool_service import get_employee, get_group_employee, get_employee_time_on_task,get_employee_efficiency

# 暂存生成的agent_service
agent_map = {}

class AgentService:

    def __init__(self, workplace:Workplace, work_group:WorkGroup):
        self.workplace = workplace
        self.work_group = work_group
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

        self.system_template = (f"你的角色是{workplace.name}这个工作点的一名工作组:{work_group.name}的组长助理，该小组的工作岗位是:{work_group.position_name}。"
                                f"{workplace.name}的工作点编码是{workplace.code}，具体介绍是【{workplace.desc}】。"
                                f"你管理的小组的小组编码是:{work_group.code}，具体介绍是【{work_group.desc}】。"
                                "你的日常工作就是辅助你的小组长一起管理这个小组，所有员工信息、员工出勤情况、作业数据、作业情况都会由专门的工具获取，不要随便编造数据。"                                
                                "当用户提到相对日期（如'昨天'、'上周'）时，请将其转换为YYYY-MM-DD格式后再调用工具。当前日期是{currentDate}"
                                "所有需要根据工号查询的工具，都需要提前调用其他工具查询获取组员的工号"
                                "返回值用纯文本，不要使用Markdown格式")

    def question(self, question):
        tools = [get_employee, get_group_employee, get_employee_time_on_task]

        examples = [ex.to_json() for ex in group_examples]

        example_prompt = ChatPromptTemplate.from_messages(
            [
                ("human", "{input}"),
                ("ai", "{output}"),
            ]
        )
        few_shot_prompt = FewShotChatMessagePromptTemplate(
            example_prompt=example_prompt,
            examples=examples,
        )

        final_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", self.system_template),
                few_shot_prompt,
                ("human", question),
                MessagesPlaceholder(variable_name="agent_scratchpad")  # 关键：必须有这个占位符
            ]
        )

        agent = create_tool_calling_agent(self.llm, tools, final_prompt)

        # 然后创建agent执行器
        agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

        # 调用
        res = agent_executor.invoke({
            "currentDate":datetime.now().strftime("%Y-%m-%d"),
            "input": question
        })
        print(res)
        return res["output"]


def create_agent(workplace: Workplace, work_group: WorkGroup, session_id) -> AgentService:
    agent_service = AgentService(workplace, work_group)

    agent_map[f"{workplace.code}_{work_group.code}_{session_id}"] = agent_service
    return agent_service


def get_agent(workplace_code, work_group_code, session_id) -> AgentService:
    agent_service = agent_map[f"{workplace_code}_{work_group_code}_{session_id}"]
    return agent_service

# 工具执行器
def execute_tool_calls(tool_calls):
    results = []
    for tool_call in tool_calls['tool_calls']:
        tool_name = tool_call["name"]
        args = tool_call["args"]
        if tool_name == "get_employee":
            # 实际调用工具函数
            result = get_employee.invoke(args)
            results.append({
                "tool_call_id": tool_call["id"],
                "output": result
            })
    return results



