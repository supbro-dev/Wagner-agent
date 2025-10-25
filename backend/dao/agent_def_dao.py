from sqlalchemy import select, and_, or_, update

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

    def save(self, agent_def: AgentDefEntity) -> AgentDefEntity:
        """
        保存AgentDef记录

        Args:
            agent_def (AgentDefEntity): 要保存的AgentDef实体

        Returns:
            AgentDefEntity: 保存后的实体
        """
        def query(session):
            session.add(agent_def)
            session.flush()  # 获取ID
            session.refresh(agent_def)  # 刷新以获取完整数据
            return agent_def

        return self.execute_in_session(query)

    def get_by_id(self, agent_id: int) -> AgentDefEntity:
        """
        根据ID获取AgentDef记录

        Args:
            agent_id (int): ID

        Returns:
            AgentDefEntity: 查询到的AgentDefEntity对象，未找到则返回None
        """
        def query(session):
            return session.get(AgentDefEntity, agent_id)

        return self.execute_in_session(query)

    def update(self, agent_def: AgentDefEntity):
        """
        更新AgentDef记录

        Args:
            agent_def (AgentDefEntity): 要更新的AgentDef实体

        Returns:
            AgentDefEntity: 更新后的实体
        """
        def query(session):
            query = update(AgentDefEntity).where(
                AgentDefEntity.id == agent_def.id
            ).values(
                business_key=agent_def.business_key,
                agent_type=agent_def.agent_type,
                name=agent_def.name,
                system_prompt=agent_def.system_prompt
            )
            session.execute(query)
            session.flush()

        self.execute_in_session(query)

    def delete(self, agent_def: AgentDefEntity) -> bool:
        """
        删除AgentDef记录

        Args:
            agent_def (AgentDefEntity): 要删除的AgentDef实体

        Returns:
            bool: 是否删除成功
        """
        def query(session):
            session.delete(agent_def)
            return True

        return self.execute_in_session(query)

    def list_agent_defs(self, business_key: str = None, name: str = None, agent_type: str = None,
                       page: int = 1, page_size: int = 20) -> list:
        """
        列出符合条件的AgentDef记录

        Args:
            business_key (str, optional): 业务键
            name (str, optional): 名称
            agent_type (str, optional): 类型
            page (int): 页码
            page_size (int): 每页数量

        Returns:
            list: 符合条件的AgentDefEntity列表
        """
        def query(session):
            query = select(AgentDefEntity)
            
            conditions = []
            if business_key:
                conditions.append(AgentDefEntity.business_key.like(f"%{business_key}%"))
            if name:
                conditions.append(AgentDefEntity.name.like(f"%{name}%"))
            if agent_type:
                conditions.append(AgentDefEntity.agent_type == agent_type)
                
            if conditions:
                query = query.where(and_(*conditions))
                
            # 添加分页
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)
            
            result = session.execute(query).scalars().all()
            return result

        return self.execute_in_session(query)


