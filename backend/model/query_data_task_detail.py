from dataclasses import dataclass

from pydantic import BaseModel
from pydantic.alias_generators import to_camel

class QueryDataTaskDetail(BaseModel):

    target: str | None # 任务意图
    query_param: str | None # 查询参数
    data_operation:str | None # 数据二次加工
    data_format: str | None # 数据格式

    class Config:
        alias_generator = to_camel
        populate_by_name = True

    def to_desc(self):
        return f"""
        任务的目标:{self.target}\n
        查询参数:{self.query_param}\n
        数据格式:{self.data_format}\n
        获取到结果之后的数据加工逻辑:{self.data_operation}\n        
        """

    def to_desc_for_llm(self):
        return f"""
                任务的目标:{self.target}\n
                查询参数:{self.query_param}\n
                获取到结果之后的数据加工逻辑:{self.data_operation}\n        
                """

    def to_dict(self):
        return self.model_dump(by_alias=True)

    # 判断取数任务描述信息时完整的
    def is_integrated(self)->bool:
        return self.target is not None and self.data_operation is not None and self.data_operation is not None and self.data_format is not None