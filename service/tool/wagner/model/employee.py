class Employee:
    def __init__(self, name, number, workplace_code, work_group_code):
        self.name = name
        self.number = number
        self.workplace_code = workplace_code
        self.work_group_code = work_group_code

    def to_dict(self):
        return self.__dict__

    def to_desc(self):
        return f"姓名:{self.name}，工号:{self.number}，所属工作点编码:{self.workplace_code}，所属工作组编码:{self.work_group_code}"