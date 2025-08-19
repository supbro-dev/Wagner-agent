from pydantic import BaseModel
from pydantic.alias_generators import to_camel


class QueryDataTaskDetail(BaseModel):

    target: str  # 任务意图
    tool_used:str # 工具使用
    query_parameters:str # 查询参数
    data_operation:str # 数据二次加工

    class Config:
        alias_generator = to_camel
        populate_by_name = True

    def to_desc(self):
        return f"""
        任务的目标:{self.target}\n
        使用的工具:{self.tool_used}\n
        查询参数:{self.query_parameters}\n
        调用工具后的加工逻辑:{self.data_operation}\n        
        """