
class GroupLeaderExample:

    def __init__(self, input, output):
        self.input = input
        self.output = output

    def to_dict(self):
        return self.__dict__

    def to_json(self):
        return {
            "input": {"input": self.input},
            "output": {"output": self.output},
        }


group_examples = [
    GroupLeaderExample("小组成员是？", "有3名组员，1.张三，工号:123。2.李四，工号:234。")
]