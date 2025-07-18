class Employee:
    def __init__(self, name, number, workplace_code, work_group_code):
        self.name = name
        self.number = number
        self.workplace_code = workplace_code
        self.work_group_code = work_group_code

    def to_dict(self):
        return self.__dict__