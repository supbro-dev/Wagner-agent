from pydantic import BaseModel


class WorkGroup(BaseModel):
    name:str
    code:str
    position_name:str
    desc:str