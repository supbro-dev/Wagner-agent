from dataclasses import field, dataclass
from typing import Sequence

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages
from typing_extensions import Annotated


@dataclass
class AssistantState:
    messages: Annotated[Sequence[AnyMessage], add_messages] = field(
        default_factory=list
    )