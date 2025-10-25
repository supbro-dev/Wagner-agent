from typing import List

from sqlalchemy import select, delete

from dao.base_dao import BaseDAO
from entity.agent_llm_tool_entity import AgentLLMToolEntity


class AgentLLMToolDAO(BaseDAO):
    def get_tool_ids_by_agent_id(self, agent_id: int) -> List[int]:
        """
        根据agent_id获取关联的工具ID列表

        Args:
            agent_id (int): Agent ID

        Returns:
            List[int]: 工具ID列表
        """
        def query(session):
            query = select(AgentLLMToolEntity.llm_tool_id).where(
                AgentLLMToolEntity.agent_id == agent_id
            )
            result = session.execute(query).scalars().all()
            return list(result)

        return self.execute_in_session(query)

    def get_agent_ids_by_tool_id(self, tool_id: int) -> List[int]:
        """
        根据tool_id获取关联的Agent ID列表

        Args:
            tool_id (int): 工具ID

        Returns:
            List[int]: Agent ID列表
        """
        def query(session):
            query = select(AgentLLMToolEntity.agent_id).where(
                AgentLLMToolEntity.llm_tool_id == tool_id
            )
            result = session.execute(query).scalars().all()
            return list(result)

        return self.execute_in_session(query)

    def save_relationships(self, agent_id: int, tool_ids: List[int]) -> None:
        """
        保存agent和tool的关联关系

        Args:
            agent_id (int): Agent ID
            tool_ids (List[int]): 工具ID列表
        """
        def query(session):
            # 先删除原有的关系
            del_query = delete(AgentLLMToolEntity).where(
                AgentLLMToolEntity.agent_id == agent_id
            )
            session.execute(del_query)
            
            # 添加新的关系
            for tool_id in tool_ids:
                relationship = AgentLLMToolEntity()
                relationship.agent_id = agent_id
                relationship.llm_tool_id = tool_id
                session.add(relationship)
            
            session.flush()

        self.execute_in_session(query)

    def add_relationship(self, agent_id: int, tool_id: int) -> AgentLLMToolEntity:
        """
        添加agent和tool的关联关系

        Args:
            agent_id (int): Agent ID
            tool_id (int): 工具ID

        Returns:
            AgentLLMToolEntity: 关联关系实体
        """
        def query(session):
            relationship = AgentLLMToolEntity()
            relationship.agent_id = agent_id
            relationship.llm_tool_id = tool_id
            session.add(relationship)
            session.flush()
            session.refresh(relationship)
            return relationship

        return self.execute_in_session(query)

    def remove_relationship(self, agent_id: int, tool_id: int) -> bool:
        """
        移除agent和tool的关联关系

        Args:
            agent_id (int): Agent ID
            tool_id (int): 工具ID

        Returns:
            bool: 是否删除成功
        """
        def query(session):
            query = delete(AgentLLMToolEntity).where(
                AgentLLMToolEntity.agent_id == agent_id,
                AgentLLMToolEntity.llm_tool_id == tool_id
            )
            result = session.execute(query)
            session.flush()
            return result.rowcount > 0

        return self.execute_in_session(query)

    def remove_all_relationships_for_agent(self, agent_id: int) -> int:
        """
        移除指定agent的所有关联关系

        Args:
            agent_id (int): Agent ID

        Returns:
            int: 删除的记录数
        """
        def query(session):
            query = delete(AgentLLMToolEntity).where(
                AgentLLMToolEntity.agent_id == agent_id
            )
            result = session.execute(query)
            session.flush()
            return result.rowcount

        return self.execute_in_session(query)

    def remove_all_relationships_for_tool(self, tool_id: int) -> int:
        """
        移除指定tool的所有关联关系

        Args:
            tool_id (int): 工具ID

        Returns:
            int: 删除的记录数
        """
        def query(session):
            query = delete(AgentLLMToolEntity).where(
                AgentLLMToolEntity.llm_tool_id == tool_id
            )
            result = session.execute(query)
            session.flush()
            return result.rowcount

        return self.execute_in_session(query)