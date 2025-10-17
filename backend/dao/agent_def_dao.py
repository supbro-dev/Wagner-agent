from sqlalchemy import select

from dao.base_dao import BaseDAO
from entity.agent_def_entity import AgentDefEntity


class AgentDefDAO(BaseDAO):
    def find_by_business_key_and_type(self, business_key, agent_type) -> AgentDefEntity:
        """
        根据business_key和type查询AgentDef记录

        Args:
            business_key (str): 业务键
            agent_type (str): 类型

        Returns:
            AgentDef: 查询到的AgentDefEntity对象，未找到则返回None
        """
        def query(session):
            query = select(AgentDefEntity).where(
                AgentDefEntity.business_key == business_key,
                AgentDefEntity.agent_type == agent_type
            )
            result = session.execute(query).scalar_one_or_none()
            return result

        return self.execute_in_session(query)
