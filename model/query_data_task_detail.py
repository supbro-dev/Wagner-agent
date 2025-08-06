from pydantic import BaseModel
from pydantic.alias_generators import to_camel


class QueryDataTaskDetail(BaseModel):

    intent: str  # 任务意图
    tool_used:str # 工具使用
    query_parameters:str # 查询参数
    data_operation:str # 数据二次加工

    class Config:
        alias_generator = to_camel
        populate_by_name = True

    def to_desc(self):
        return f"""
        任务的意图是:{self.intent}\n
        使用的工具是:{self.tool_used}\n
        查询参数是:{self.query_parameters}\n
        从工具获取到结果之后进行以下数据加工:\n
        {self.data_operation}        
        """