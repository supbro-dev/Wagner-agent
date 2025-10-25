from typing import List, Optional
from dao.agent_def_dao import AgentDefDAO
from entity.agent_def_entity import AgentDefEntity


class AgentDefService:
    def __init__(self, agent_def_dao: AgentDefDAO):
        self.agent_def_dao = agent_def_dao

    def create_agent_def(self, business_key: str, name: str, system_prompt: str, agent_type: str) -> AgentDefEntity:
        """
        创建新的Agent定义
        
        Args:
            business_key: 业务键
            name: 名称
            system_prompt: 系统提示词
            agent_type: 类型
            
        Returns:
            AgentDefEntity: 创建的实体
        """
        # 检查是否已存在相同business_key和agent_type的记录
        existing = self.agent_def_dao.find_by_business_key_and_type(business_key, agent_type)
        if existing:
            raise ValueError(f"业务键为 '{business_key}' 且类型为 '{agent_type}' 的Agent定义已存在")

        # 创建新实体
        agent_def = AgentDefEntity()
        agent_def.business_key = business_key
        agent_def.name = name
        agent_def.system_prompt = system_prompt
        agent_def.agent_type = agent_type

        # 保存到数据库
        return self.agent_def_dao.save(agent_def)

    def update_agent_def(self, agent_id: int, business_key: str = None, name: str = None, 
                         system_prompt: str = None, agent_type: str = None):
        """
        更新Agent定义
        
        Args:
            agent_id: Agent ID
            business_key: 业务键（可选）
            name: 名称（可选）
            system_prompt: 系统提示词（可选）
            agent_type: 类型（可选）
            
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
        if name is not None:
            agent_def.name = name
        if system_prompt is not None:
            agent_def.system_prompt = system_prompt
        if agent_type is not None:
            agent_def.agent_type = agent_type

        # 保存更新
        self.agent_def_dao.update(agent_def)

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
        
        return self.agent_def_dao.delete(agent_def)

    def get_agent_def_by_id(self, agent_id: int) -> Optional[AgentDefEntity]:
        """
        根据ID获取Agent定义
        
        Args:
            agent_id: Agent ID
            
        Returns:
            AgentDefEntity: Agent定义实体
        """
        return self.agent_def_dao.get_by_id(agent_id)

    def list_agent_defs(self, business_key: str = None, name: str = None, agent_type: str = None, 
                        page: int = 1, page_size: int = 20) -> List[AgentDefEntity]:
        """
        列出符合条件的Agent定义
        
        Args:
            business_key: 业务键（可选）
            name: 名称（可选）
            agent_type: 类型（可选）
            page: 页码，默认为1
            page_size: 每页数量，默认为20
            
        Returns:
            List[AgentDefEntity]: Agent定义实体列表
        """
        return self.agent_def_dao.list_agent_defs(business_key, name, agent_type, page, page_size)

    def get_agent_def_by_business_key_and_type(self, business_key: str, agent_type: str) -> Optional[AgentDefEntity]:
        """
        根据business_key和type获取Agent定义
        
        Args:
            business_key: 业务键
            agent_type: 类型
            
        Returns:
            AgentDefEntity: Agent定义实体
        """
        return self.agent_def_dao.find_by_business_key_and_type(business_key, agent_type)