from sqlalchemy.orm import sessionmaker

from entity.query_data_task_entity import QueryDataTaskEntity
from init import engine

# 创建会话类
Session = sessionmaker(bind=engine)
# 使用会话
session = Session()

def find_by_name(business_key, name) -> QueryDataTaskEntity:
    entity = session.query(QueryDataTaskEntity).filter_by(business_key = business_key, name = name).one_or_none()
    return entity

def find_by_id(id) -> QueryDataTaskEntity:
    entity = session.query(QueryDataTaskEntity).filter_by(id=id).one_or_none()
    return entity