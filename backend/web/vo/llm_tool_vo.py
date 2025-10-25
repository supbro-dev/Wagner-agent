from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class LLMToolVO(BaseModel):
    id: int
    name: str
    description: str
    args_dict: str
    tool_type: str
    content: str
    request_handle_script: str | None = None
    response_handle_script: str | None = None
    gmt_create: str | None = None
    gmt_modified: str | None = None

    def to_json(self):
        return self.model_dump_json(by_alias=True)

    def to_dict(self):
        return self.model_dump(by_alias=True)

    model_config = ConfigDict(
        # 设置别名生成器为驼峰命名
        alias_generator=to_camel,
        # 允许使用字段名和别名进行赋值
        populate_by_name=True,
    )