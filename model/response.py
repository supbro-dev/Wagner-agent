def success(data):
    return Res(0, data, "success")

def failure(ex:Exception):
    return Res(-1, ex.args, "failure")

def failure():
    return Res(-1, "", "failure")

class Res:
    def __init__(self, code, data, msg):
        self.code = code
        self.data = data
        self.msg = msg

    def to_dict(self):
        return self.__dict__