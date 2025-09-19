from pydantic import BaseModel


class Workplace(BaseModel):
    name:str
    code:str
    desc:str
