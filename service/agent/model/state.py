from dataclasses import dataclass, field
from typing import Sequence

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages
from typing_extensions import Annotated

from model.query_data_task_detail import QueryDataTaskDetail



@dataclass
class State():
    messages: Annotated[Sequence[AnyMessage], add_messages] = field(
        default_factory=list
    )
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
    # 查询db或向量存储中的是否存在任务信息
    is_task_existed: bool = False