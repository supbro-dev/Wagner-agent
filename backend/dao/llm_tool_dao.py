from typing import List, Optional

from sqlalchemy import update
from sqlalchemy.orm import sessionmaker

from dao.base_dao import BaseDAO
from entity.agent_llm_tool_entity import AgentLLMToolEntity
from entity.llm_tool_entity import LLMToolEntity


class LLMToolDAO(BaseDAO):

    def get_by_id(self, tool_id: int) -> Optional[LLMToolEntity]:
        """
        根据ID获取LLM工具

        Args:
            tool_id (int): 工具ID

        Returns:
            LLMToolEntity: LLM工具实体，如果未找到则返回None
        """

        def query(session):
            return session.query(LLMToolEntity).filter(LLMToolEntity.id == tool_id).first()

        return self.execute_in_session(query)

    def save(self, llm_tool: LLMToolEntity) -> LLMToolEntity:
        """
        保存新的LLM工具

        Args:
            llm_tool (LLMToolEntity): 要保存的LLM工具实体

        Returns:
            LLMToolEntity: 保存后的LLM工具实体
        """

        def query(session):
            session.add(llm_tool)
            session.flush()  # 获取插入记录的ID
            session.refresh(llm_tool)  # 刷新以获取完整数据
            return llm_tool

        return self.execute_in_session(query)

    def update(self, llm_tool: LLMToolEntity) -> None:
        """
        更新LLM工具

        Args:
            llm_tool (LLMToolEntity): 要更新的LLM工具实体
        """
        def query(session):
            query = update(LLMToolEntity).where(
                LLMToolEntity.id == llm_tool.id
            ).values(
                name=llm_tool.name,
                description=llm_tool.description,
                args_dict=llm_tool.args_dict,
                tool_type=llm_tool.tool_type,
                content=llm_tool.content,
                request_handle_script=llm_tool.request_handle_script,
                response_handle_script=llm_tool.response_handle_script
            )
            session.execute(query)
            session.flush()

        self.execute_in_session(query)

    def delete(self, llm_tool: LLMToolEntity) -> bool:
        """
        删除LLM工具

        Args:
            llm_tool (LLMToolEntity): 要删除的LLM工具实体

        Returns:
            bool: 删除成功返回True，否则返回False
        """

        def query(session):
            session.delete(llm_tool)
            return True

        return self.execute_in_session(query)

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

    def find_by_name(self, name: str) -> Optional[LLMToolEntity]:
        """
        根据名称查找LLM工具

        Args:
            name (str): 工具名称

        Returns:
            LLMToolEntity: LLM工具实体，如果未找到则返回None
        """

        def query(session):
            return session.query(LLMToolEntity).filter(LLMToolEntity.name == name).first()

        return self.execute_in_session(query)

    def list_llm_tools(self, name: str = None, tool_type: str = None, page: int = 1, page_size: int = 20) -> List[LLMToolEntity]:
        """
        列出LLM工具

        Args:
            name (str, optional): 工具名称筛选条件
            tool_type (str, optional): 工具类型筛选条件
            page (int): 页码
            page_size (int): 每页数量

        Returns:
            list: LLMToolEntity对象列表
        """

        def query(session):
            query = session.query(LLMToolEntity)
            
            if name:
                query = query.filter(LLMToolEntity.name.like(f"%{name}%"))
            
            if tool_type:
                query = query.filter(LLMToolEntity.tool_type == tool_type)
                
            # 分页
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)
            
            return query.all()

        return self.execute_in_session(query)