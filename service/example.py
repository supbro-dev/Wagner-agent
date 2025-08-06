from typing import List, Dict

from pydantic import BaseModel, GetCoreSchemaHandler
from pydantic_core import CoreSchema


class ToolInvoke(BaseModel):
    tool_name:str | None = None
    invoke_args:Dict[str, str] | None = None
    tool_res:str | None = None



class ExampleTemplate:
    # 使用的工具
    use_tools:List[str] = []
    # 用户输入
    human_input:str
    # ai输出
    ai_output:str
    # 工具调用完整信息
    tool_invoke_list:List[ToolInvoke] = []

    def to_dict(self):
        return self.__dict__


