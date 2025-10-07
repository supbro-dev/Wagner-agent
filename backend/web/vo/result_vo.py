from typing import Any

from pydantic.alias_generators import to_camel
from pydantic import BaseModel, ConfigDict


class ResultVo(BaseModel):

    success:bool
    result:Any

    def to_json(self):
        return self.model_dump_json(by_alias=True)

    model_config = ConfigDict(
        # 设置别名生成器为驼峰命名
        alias_generator=to_camel,
        # 允许使用字段名和别名进行赋值
        populate_by_name=True,
    )