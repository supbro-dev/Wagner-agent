from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class WorkflowResume(BaseModel):
    resume_type:str
    resume_desc:str
    resume_mode:Literal["invoke", "stream"]

    model_config = ConfigDict(
        # 设置别名生成器为驼峰命名
        alias_generator=to_camel,
        # 允许使用字段名和别名进行赋值
        populate_by_name=True,
    )

    def to_dict(self):
        return self.model_dump(by_alias=True)

    def to_json(self):
        return self.model_dump_json(by_alias=True)
