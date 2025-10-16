from dataclasses import field, dataclass
from typing import Sequence

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages
from typing_extensions import Annotated

from model.query_data_task_detail import QueryDataTaskDetail
from service.agent.model.state import InputState


@dataclass
class AssistantState(InputState):

    # 查询任务相关
    task_names: list[str] = field(default_factory=list)
    task_details: list[QueryDataTaskDetail] = field(default_factory=list)

    # 推理内容
    reasoning_context : str = ""

    # rag内容
    rag_docs: list = field(default_factory=list)

    # 记忆内容
    memories:list = field(default_factory=list)

