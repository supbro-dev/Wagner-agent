
class AnswerVo:
    message_id: str
    content:str
    last_human_message_id:str

    def __init__(self, message_id:str, content:str, last_human_message_id:str):
        self.message_id = message_id
        self.content = content
        self.last_human_message_id = last_human_message_id

    def to_dict(self):
        return {
            'messageId': self.message_id,
            'content': self.content,
            'lastHumanMessageId': self.last_human_message_id
        }

    def __json__(self):
        return self.to_dict()