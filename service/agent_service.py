import os
from typing import Optional, Any

from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool
from langchain.agents import Agent
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, FewShotChatMessagePromptTemplate
from langchain_deepseek import ChatDeepSeek

from model.employee import Employee
from model.work_group import WorkGroup
from model.workplace import Workplace
from util import http_util
from util.config_util import read_private_config
from util.http_util import http_get

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
                                "你的日常工作就是辅助你的小组长一起管理这个小组，所有员工信息、员工出勤情况、作业数据、作业情况都会由专门的工具获取，不要随便编造数据")

    def welcome(self) -> str:
        user_text = "现在跟你对话的是小组长本人，请说一下你的问候语（越简洁越好）"

        examples = [
            {"input": user_text, "output": "上午好，准备开始一天的工作"},
            {"input": user_text, "output": "有什么需要我来做的，请告诉我"},
        ]

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
                ("human", user_text),
            ]
        )

        prompt = final_prompt.invoke({})

        res = self.llm.invoke(prompt)
        print(res)

        return res.content

    def question(self, question):
        tools = [get_employee]
        llm_with_tools = self.llm.bind_tools(tools)

        final_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", self.system_template),
                ("human", question),
            ]
        )


        chain = final_prompt | llm_with_tools | {
            # 解析工具调用请求
            "tool_calls": lambda msg: msg.tool_calls,
            "messages": lambda _: []
        } | RunnableLambda(execute_tool_calls)  # 执行工具

        res = chain.invoke({})

        print(res)
        return res




def create_agent(workplace:Workplace, work_group: WorkGroup) -> AgentService:
    agent_service = AgentService(workplace, work_group)
    if workplace.code not in agent_map:
        agent_map[workplace.code] = {work_group.code: agent_service}
    else :
        agent_map[workplace.code][work_group.code] = agent_service
    return agent_service


def get_agent(workplace_code, work_group_code) -> AgentService:
    agent_service = agent_map[workplace_code][work_group_code]
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


@tool
def get_employee(employee_name, workplace_code, work_group_code):
    """根据员工姓名，工作点编码，工作组编码查找员工信息，返回信息包括:
    员工工号:number
    员工姓名:name
    """
    res = http_get(f"/employee/findByInfo?workplaceCode={workplace_code}&workGroupCode={work_group_code}&employeeName={employee_name}")
    data: dict[str, Any] = res["data"]
    employee = Employee(data["name"], data["number"], data["workplaceCode"], data["workGroupCode"])

    return employee.to_dict()
