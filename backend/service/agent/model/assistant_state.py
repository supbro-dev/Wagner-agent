from dataclasses import field, dataclass
from typing import Sequence

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages
from typing_extensions import Annotated

from service.agent.model.state import InputState


@dataclass
class AssistantState(InputState):

    # rag内容
    rag_dosc: list = field(default_factory=list)

    # 记忆内容
    memori_content:str = ""

