from sqlalchemy import update, select
from sqlalchemy.orm import sessionmaker

from entity.agent_def_entity import AgentDefEntity
from entity.query_data_task_entity import QueryDataTaskEntity
from init import engine
# 创建会话类
Session = sessionmaker(bind=engine)


def find_by_business_key_and_type(business_key, type) -> AgentDefEntity:
    """
    根据business_key和type查询AgentDef记录

    Args:
        business_key (str): 业务键
        type (str): 类型

    Returns:
        AgentDef: 查询到的AgentDefEntity对象，未找到则返回None
    """
    with Session() as session:
        query = select(AgentDefEntity).where(
            AgentDefEntity.business_key == business_key,
            AgentDefEntity.type == type
        )
        result = session.execute(query).scalar_one_or_none()
        return result
