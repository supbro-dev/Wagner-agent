from pydantic import BaseModel
from pydantic.alias_generators import to_camel


class LLMHTTPToolContent(BaseModel):
    # HTTP请求url
    url:str
    # GET/POST
    method:str

    class Config:
        alias_generator = to_camel
        populate_by_name = True

