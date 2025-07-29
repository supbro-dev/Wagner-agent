from typing import List

from entity.ai_example_entity import AiExampleEntity



def find_by_key(key:str) -> List[AiExampleEntity]:
    list = AiExampleEntity.query.filter_by(key = key).all()

    return list