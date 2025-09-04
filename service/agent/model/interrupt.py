
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from service.agent.model.resume import WorkflowResume


# 工作流中断对象
class WorkflowInterrupt(BaseModel):
    action:str
    task_name:str
    description:str
    confirm_option_list:list[WorkflowResume]

    model_config = ConfigDict(
        # 设置别名生成器为驼峰命名
        alias_generator=to_camel,
        # 允许使用字段名和别名进行赋值
        populate_by_name=True,
    )

    def to_json(self):
        return self.model_dump_json(by_alias=True)