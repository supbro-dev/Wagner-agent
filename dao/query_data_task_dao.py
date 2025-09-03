from sqlalchemy import update, select
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


def save(task_entity:QueryDataTaskEntity) -> int:
    session = Session()
    try:
        if task_entity.id is None:
            session.add(task_entity)
        else:
            session.query(QueryDataTaskEntity).filter_by(id=task_entity.id).update({
                "task_detail": task_entity.task_detail
            })
        session.commit()
        return task_entity.id
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

def update_execute_times_once(id, business_key):
    stmt = (
        update(QueryDataTaskEntity)
        .where(QueryDataTaskEntity.id == id)
        .values(invoke_times=QueryDataTaskEntity.invoke_times + 1)
    )

    # 执行语句
    with Session() as session:
        session.execute(stmt)
        session.commit()  # 提交事务


def get_frequently_execute_top3_tasks(business_key, not_in_ids):
    with Session() as session:
        return session.query(QueryDataTaskEntity).where(QueryDataTaskEntity.id.not_in(not_in_ids)).filter_by(business_key = business_key, is_deleted = 0).order_by(QueryDataTaskEntity.invoke_times.desc()).limit(3).all()


def get_usually_execute_top3_tasks(business_key):
    with Session() as session:
        query = select(QueryDataTaskEntity).filter_by(business_key = business_key, is_deleted = 0).order_by(QueryDataTaskEntity.execute_time.desc()).limit(3)
        return session.scalars(query).all()