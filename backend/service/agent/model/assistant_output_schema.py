from typing import Literal

from pydantic import BaseModel, Field

# 确定的几种意图
QUERY_DATA: str = "query_data"
DEFAULT: str = "default" # 当意图识别出现错误时，提示用户当前已有能力

# 定义意图分类规范
class IntentSchema(BaseModel):
    intent_type: Literal[QUERY_DATA, DEFAULT] = Field(
        description="用户请求的核心意图类型"
    )
