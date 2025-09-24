from typing import Optional, Literal

from pydantic import BaseModel, Field

# 确定的几种意图
QUERY_DATA: str = "query_data"
EXECUTE: str = "execute"
CREATE: str = "create"
EDIT: str = "edit"
DELETE: str = "delete"
OTHERS: str = "others"
TEST_RUN: str = "test_run"
SAVE: str = "save"
DEFAULT: str = "default" # 当意图识别出现错误时，提示用户当前已有能力
# 定义意图分类规范
class IntentSchema(BaseModel):
    intent_type: Literal[QUERY_DATA, EXECUTE, CREATE, EDIT, DELETE, OTHERS] = Field(
        description="用户请求的核心意图类型"
    )
    task_id: Optional[str] = Field(
        default=None,
        description="涉及的任务ID（如果是执行/编辑）"
    )
    task_name: Optional[str] = Field(
        default=None,
        description="涉及的任务名称（如果是执行/新建/编辑）"
    )


# 任务的模板
class TaskSchema(BaseModel):
    target: Optional[str] = Field(
        description="任务的目标"
    )
    query_param:  Optional[str] = Field(
        default=None,
        description="查询参数"
    )
    data_operation: Optional[str] = Field(
        default=None,
        description="调用工具后的加工逻辑"
    )

# 表格的模板
class TableSchema(BaseModel):
    header_list: Optional[list[str]] = Field(
        default=None,
        description="表格的表头"
    )
    data_list: Optional[list[list[str]]] = Field(
        default=None,
        description="表格的数据"
    )
class LineChartSchema(BaseModel):
    x_axis: Optional[list[str]] = Field(
        default=None,
        description="折线图的X轴"
    )
    x_name: Optional[str] = Field(
        default=None,
        description="折线图的X轴名称"
    )
    y_axis: Optional[list[float]] = Field(
        default=None,
        description="折线图的Y轴"
    )
    y_name: Optional[str] = Field(
        default=None,
        description="折线图的Y轴名称"
    )