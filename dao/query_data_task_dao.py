from sqlalchemy.orm import sessionmaker

from entity.query_data_task_entity import QueryDataTaskEntity
from init import engine

# 创建会话类
Session = sessionmaker(bind=engine)


def find_by_name(business_key, name) -> QueryDataTaskEntity | None:
    session = Session()
    try:
        entity = session.query(QueryDataTaskEntity).filter_by(business_key = business_key, name = name, is_deleted = 0).one_or_none()
        return entity
    finally:
        session.close()


def find_by_id(id) -> QueryDataTaskEntity:
    session = Session()
    try:
        entity = session.query(QueryDataTaskEntity).filter_by(id=id, is_deleted = 0).one_or_none()
        return entity
    finally:
        session.close()


def save(task_entity:QueryDataTaskEntity):
    session = Session()
    try:
        if task_entity.id is None:
            session.add(task_entity)
        else:
            session.query(QueryDataTaskEntity).filter_by(id=task_entity.id).update({
                "task_detail": task_entity.task_detail
            })
        session.commit()
    finally:
        session.close()


def delete(id, business_key):
    session = Session()
    try:
        session.query(QueryDataTaskEntity).filter_by(id=id, business_key = business_key).update({
            "is_deleted": 1
        })
        session.commit()
    finally:
        session.close()
