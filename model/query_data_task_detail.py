from dataclasses import dataclass

from pydantic import BaseModel
from pydantic.alias_generators import to_camel

class QueryDataTaskDetail(BaseModel):

    target: str  # 任务意图
    data_operation:str # 数据二次加工

    class Config:
        alias_generator = to_camel
        populate_by_name = True

    def to_desc(self):
        return f"""
        任务的目标:{self.target}\n
        获取到结果之后的数据加工逻辑:{self.data_operation}\n        
        """

    def to_dict(self):
        return {
            'target': self.target,
            'data_operation': self.data_operation,
        }