from typing import List, TypeVar, Generic

from pydantic.alias_generators import to_camel
from pydantic import BaseModel, ConfigDict

T = TypeVar('T')

class Page(BaseModel):
    page: int
    page_size: int
    total: int

    model_config = ConfigDict(
        # 设置别名生成器为驼峰命名
        alias_generator=to_camel,
        # 允许使用字段名和别名进行赋值
        populate_by_name=True,
    )

class PageResultVO(BaseModel, Generic[T]):
    success: bool
    list: List[T]
    pagination: Page

    def to_json(self):
        return self.model_dump_json(by_alias=True)

    model_config = ConfigDict(
        # 设置别名生成器为驼峰命名
        alias_generator=to_camel,
        # 允许使用字段名和别名进行赋值
        populate_by_name=True,
    )