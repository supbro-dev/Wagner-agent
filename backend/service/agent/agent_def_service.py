from typing import List

from dao.agent_def_dao import AgentDefDAO
from dao.agent_llm_tool_dao import AgentLLMToolDAO
from entity.agent_def_entity import AgentDefEntity


class AgentDefService:
    def __init__(self, agent_def_dao: AgentDefDAO, agent_llm_tool_dao: AgentLLMToolDAO):
        self.agent_def_dao = agent_def_dao
        self.agent_llm_tool_dao = agent_llm_tool_dao

    def create_agent_def(self, business_key: str, agent_type: str, name: str, 
                        system_prompt: str, tool_ids: List[int] = None) -> AgentDefEntity:
        """
        创建新的Agent定义
        
        Args:
            business_key: 业务键
            agent_type: Agent类型
            name: 名称
            system_prompt: 系统提示词
            tool_ids: 关联的工具ID列表
            
        Returns:
            AgentDefEntity: 创建的实体
        """
        # 检查是否已存在相同business_key和agent_type的记录
        existing = self.agent_def_dao.find_by_business_key_and_type(business_key, agent_type)
        if existing:
            raise ValueError(f"business_key为'{business_key}'且agent_type为'{agent_type}'的记录已存在")

        # 创建新实体
        agent_def = AgentDefEntity()
        agent_def.business_key = business_key
        agent_def.agent_type = agent_type
        agent_def.name = name
        agent_def.system_prompt = system_prompt

        # 保存到数据库
        created_agent = self.agent_def_dao.save(agent_def)
        
        # 如果提供了工具ID列表，保存关联关系
        if tool_ids is not None:
            self.agent_llm_tool_dao.save_relationships(created_agent.id, tool_ids)
            
        return created_agent

    def update_agent_def(self, agent_id: int, business_key: str = None, agent_type: str = None,
                        name: str = None, system_prompt: str = None, tool_ids: List[int] = None) -> AgentDefEntity:
        """
        更新Agent定义
        
        Args:
            agent_id: Agent ID
            business_key: 业务键（可选）
            agent_type: Agent类型（可选）
            name: 名称（可选）
            system_prompt: 系统提示词（可选）
            tool_ids: 关联的工具ID列表（可选）
            
        Returns:
            AgentDefEntity: 更新后的实体
        """
        # 查找现有实体
        agent_def = self.agent_def_dao.get_by_id(agent_id)
        if not agent_def:
            raise ValueError(f"Agent definition with id {agent_id} not found")

        # 更新字段
        if business_key is not None:
            agent_def.business_key = business_key
        if agent_type is not None:
            agent_def.agent_type = agent_type
        if name is not None:
            agent_def.name = name
        if system_prompt is not None:
            agent_def.system_prompt = system_prompt

        # 保存更新
        self.agent_def_dao.update(agent_def)
        
        # 如果提供了工具ID列表，更新关联关系
        if tool_ids is not None:
            from container import dao_container
            agent_llm_tool_dao = dao_container.agent_llm_tool_dao()
            agent_llm_tool_dao.save_relationships(agent_id, tool_ids)
            
        return agent_def

    def delete_agent_def(self, agent_id: int) -> bool:
        """
        删除Agent定义
        
        Args:
            agent_id: Agent ID
            
        Returns:
            bool: 是否删除成功
        """
        agent_def = self.agent_def_dao.get_by_id(agent_id)
        if not agent_def:
            raise ValueError(f"Agent definition with id {agent_id} not found")
        
        # 删除关联关系
        from container import dao_container
        agent_llm_tool_dao = dao_container.agent_llm_tool_dao()
        agent_llm_tool_dao.remove_all_relationships_for_agent(agent_id)
        
        return self.agent_def_dao.delete(agent_def)

    def get_agent_def_by_id(self, agent_id: int):
        """
        根据ID获取Agent定义
        
        Args:
            agent_id: Agent ID
            
        Returns:
            dict[agent_def:agent_def, tool_ids:[]]
        """
        agent_def = self.agent_def_dao.get_by_id(agent_id)
        if not agent_def:
            return None

        tool_ids = self.agent_llm_tool_dao.get_tool_ids_by_agent_id(agent_id)

        return {
            'agent_def': agent_def,
            'tool_ids': tool_ids
        }



    def list_agent_defs(self, business_key: str = None, name: str = None, agent_type: str = None,
                       page: int = 1, page_size: int = 20) -> List[dict]:
        """
        列出符合条件的Agent定义
        
        Args:
            business_key: 业务键（可选）
            name: 名称（可选）
            agent_type: Agent类型（可选）
            page: 页码，默认为1
            page_size: 每页数量，默认为20
            
        Returns:
            List[dict]: 包含Agent定义实体和关联工具ID的字典列表
        """
        agent_defs = self.agent_def_dao.list_agent_defs(business_key, name, agent_type, page, page_size)
        
        # 为每个agent获取关联的工具ID
        result = []
        for agent_def in agent_defs:
            tool_ids = self.agent_llm_tool_dao.get_tool_ids_by_agent_id(agent_def.id)
            result.append({
                'agent': agent_def,
                'tool_ids': tool_ids
            })
            
        return result