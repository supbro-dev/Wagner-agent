from typing import Any

from pydantic import BaseModel


def success(data):
    return Res(code = 0, data = data, msg = "success")

def failure(ex:Exception):
    return Res(code = -1, data = ex.args, msg = "failure")

def failure():
    return Res(code = -1, data = "", msg = "failure")

class Res(BaseModel):
    code:int
    data:Any
    msg:str

    def to_dict(self):
        return self.model_dump(by_alias=True)