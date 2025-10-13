from sqlalchemy.orm import sessionmaker

from dao.base_dao import BaseDAO
from entity.agent_llm_tool_entity import AgentLLMToolEntity
from entity.llm_tool_entity import LLMToolEntity


class LLMToolDAO(BaseDAO):

    def get_llm_tools_by_agent_id(self, agent_id):
        """
        根据agentId查询关联的LLM工具列表

       Args:
           agent_id (int): Agent的ID

       Returns:
           list: LLMToolEntity对象列表，包含该agent关联的所有LLM工具
       """

        def query(session):
            # 通过agent_llm_tool表关联查询llm_tool表
            result = session.query(LLMToolEntity) \
                .join(AgentLLMToolEntity,
                      LLMToolEntity.id == AgentLLMToolEntity.llm_tool_id) \
                .filter(AgentLLMToolEntity.agent_id == agent_id) \
                .all()
            return result

        return self.execute_in_session(query)
