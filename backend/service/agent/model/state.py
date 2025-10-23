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
    session_id: str | None = None

@dataclass
class DataAnalystState(InputState):
    # 用户请求的意图类型
    intent_type: str | None = None
    # 取数任务的目的
    target: str | None = None
    # 取数任务id
    task_id: int | None = None
    # 取数任务名称
    task_name: str | None = None
    # 执行/试运行时可选的查询条件
    params: str | None = None
    # 第一次创建任务
    first_time_create: bool = True
    # 已经查找到的任务明细
    task_detail: QueryDataTaskDetail | None = None
    # 如果有确定格式的输出，则保存msgId和标准输出格式
    last_run_msg_id: str | None = None
    last_standard_data: str | None = None

    def clear_state(self):
        # 清空上下文
        self.intent_type = None
        self.last_run_msg_id = None
        self.last_standard_data = None
        self.task_detail = None
        self.first_time_create = True
        self.target = None
        self.task_id = None
        self.task_name = None
        self.params = None


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
    rag_content: str = ""

    # 查询的记忆内容
    memories:list = field(default_factory=list)
    memory_content: str = ""
    # 生成的记忆内容
    saved_memories:list = field(default_factory=list)
    saved_memory_content: str = ""
    msg_id_saved_memories: str = ""

