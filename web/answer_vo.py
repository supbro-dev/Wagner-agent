
class AnswerVo:
    message_id: str
    content:str

    def __init__(self, message_id:str, content:str):
        self.message_id = message_id
        self.content = content

    def to_dict(self):
        return {
            'messageId': self.message_id,
            'content': self.content,
        }

    def __json__(self):
        return self.to_dict()