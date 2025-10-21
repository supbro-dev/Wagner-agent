from dataclasses import field, dataclass
from typing import Sequence

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages
from typing_extensions import Annotated

from model.query_data_task_detail import QueryDataTaskDetail
from service.agent.model.state import InputState


@dataclass
class AssistantState(InputState):

    # 用户意图
    intent_type: None |str = None

    # 查询任务相关
    task_names: list[str] = field(default_factory=list)
    task_details: list[QueryDataTaskDetail] = field(default_factory=list)
    task_content: str = ""

    # 推理内容
    reasoning_context : str = ""

    # rag内容
    rag_docs: list = field(default_factory=list)

    # 查询的记忆内容
    memories:list = field(default_factory=list)
    memory_content: str = ""
    # 生成的记忆内容
    saved_memories:list = field(default_factory=list)
    saved_memory_content: str = ""
    msg_id_saved_memories: str = ""

