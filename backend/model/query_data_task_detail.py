from dataclasses import dataclass

from pydantic import BaseModel
from pydantic.alias_generators import to_camel


class QueryDataTaskDetail(BaseModel):

    target: str | None # 任务内容
    query_param: str | None # 查询参数
    data_operation:str | None # 数据二次加工
    data_format: str | None # 数据格式

    class Config:
        alias_generator = to_camel
        populate_by_name = True

    def to_desc(self):
        return f"""
        任务目标和具体内容:{self.target}\n
        查询条件:{self.query_param}\n
        数据格式:{self.data_format}\n
        获取到结果之后的数据加工逻辑:{self.data_operation}\n        
        """

    def to_desc_for_llm(self):
        return f"""
                任务目标和具体内容:{self.target}\n
                查询条件:{self.query_param}\n
                获取到结果之后的数据加工逻辑:{self.data_operation}\n        
                """

    def to_dict(self):
        return self.model_dump(by_alias=True)

    # 判断取数任务描述信息时完整的
    def is_integrated(self)->bool:
        return self.target is not None and self.data_operation is not None and self.data_operation is not None and self.data_format is not None

# 默认任务模板
DEFAULT_TASK_TEMPLATE = QueryDataTaskDetail(
        target="无。(请说明该任务的使用意图)",
        query_param="无。(请说明该任务执行时需要使用哪些查询条件，例如查询日期为某年某月某日，如果查询日期希望在任务执行时再给出，可以注明查询日期待执行时给出)",
        data_operation="无。(请详细描述，查询到结果之后希望进行哪些加工处理)",
        data_format="无。(只能选用表格、折线图)"
    )