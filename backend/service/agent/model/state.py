from dataclasses import dataclass, field
from typing import Sequence, Dict

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages
from typing_extensions import Annotated

from model.query_data_task_detail import QueryDataTaskDetail


@dataclass()
class InputState:
    """
    必须使用InputState,否则每次graph.invoke的时候如果传State，会覆盖当前上下文中state的属性
    """
    messages: Annotated[Sequence[AnyMessage], add_messages] = field(
        default_factory=list
    )

@dataclass
class State(InputState):
    # 用户请求的意图类型
    intent_type: str | None = None
    # 取数任务的目的
    target: str | None = None
    # 取数任务id
    task_id: int | None = None
    # 取数任务名称
    task_name: str | None = None
    # 第一次创建任务
    first_time_create: bool = True
    # 已经查找到的任务明细
    task_detail: QueryDataTaskDetail = None
    # 如果有确定格式的输出，则保存在ai_id_2_data中
    ai_id_2_data = {}

    last_standard_data:str = "none"

