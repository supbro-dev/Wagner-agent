from typing import List, Optional
from dao.llm_tool_dao import LLMToolDAO
from entity.llm_tool_entity import LLMToolEntity


class LLMToolService:
    def __init__(self, llm_tool_dao: LLMToolDAO):
        self.llm_tool_dao = llm_tool_dao

    def create_llm_tool(self, name: str, description: str, args_dict: str, tool_type: str, 
                       content: str, request_handle_script: str = None, response_handle_script: str = None) -> LLMToolEntity:
        """
        创建新的LLM工具
        
        Args:
            name: 工具名称
            description: 工具描述
            args_dict: 参数字典
            tool_type: 工具类型
            content: 工具内容
            request_handle_script: 请求处理脚本（可选）
            response_handle_script: 响应处理脚本（可选）
            
        Returns:
            LLMToolEntity: 创建的实体
        """
        # 检查是否已存在同名工具
        existing = self.llm_tool_dao.find_by_name(name)
        if existing:
            raise ValueError(f"名为 '{name}' 的工具已存在")

        # 创建新实体
        llm_tool = LLMToolEntity()
        llm_tool.name = name
        llm_tool.description = description
        llm_tool.args_dict = args_dict
        llm_tool.tool_type = tool_type
        llm_tool.content = content
        llm_tool.request_handle_script = request_handle_script
        llm_tool.response_handle_script = response_handle_script

        # 保存到数据库
        return self.llm_tool_dao.save(llm_tool)

    def update_llm_tool(self, tool_id: int, name: str = None, description: str = None, 
                       args_dict: str = None, tool_type: str = None, content: str = None,
                       request_handle_script: str = None, response_handle_script: str = None):
        """
        更新LLM工具
        
        Args:
            tool_id: 工具ID
            name: 工具名称（可选）
            description: 工具描述（可选）
            args_dict: 参数字典（可选）
            tool_type: 工具类型（可选）
            content: 工具内容（可选）
            request_handle_script: 请求处理脚本（可选）
            response_handle_script: 响应处理脚本（可选）
            
        Returns:
            LLMToolEntity: 更新后的实体
        """
        # 查找现有实体
        llm_tool = self.llm_tool_dao.get_by_id(tool_id)
        if not llm_tool:
            raise ValueError(f"LLM tool with id {tool_id} not found")

        # 更新字段
        if name is not None:
            # 如果名称改变，检查新名称是否已存在
            if name != llm_tool.name:
                existing = self.llm_tool_dao.find_by_name(name)
                if existing:
                    raise ValueError(f"名为 '{name}' 的工具已存在")
            llm_tool.name = name
        if description is not None:
            llm_tool.description = description
        if args_dict is not None:
            llm_tool.args_dict = args_dict
        if tool_type is not None:
            llm_tool.tool_type = tool_type
        if content is not None:
            llm_tool.content = content
        if request_handle_script is not None:
            llm_tool.request_handle_script = request_handle_script
        if response_handle_script is not None:
            llm_tool.response_handle_script = response_handle_script

        # 保存更新
        self.llm_tool_dao.update(llm_tool)

    def delete_llm_tool(self, tool_id: int) -> bool:
        """
        删除LLM工具
        
        Args:
            tool_id: 工具ID
            
        Returns:
            bool: 是否删除成功
        """
        llm_tool = self.llm_tool_dao.get_by_id(tool_id)
        if not llm_tool:
            raise ValueError(f"LLM tool with id {tool_id} not found")
        
        return self.llm_tool_dao.delete(llm_tool)

    def get_llm_tool_by_id(self, tool_id: int) -> Optional[LLMToolEntity]:
        """
        根据ID获取LLM工具
        
        Args:
            tool_id: 工具ID
            
        Returns:
            LLMToolEntity: LLM工具实体
        """
        return self.llm_tool_dao.get_by_id(tool_id)

    def list_llm_tools(self, name: str = None, tool_type: str = None, 
                       page: int = 1, page_size: int = 20) -> List[LLMToolEntity]:
        """
        列出符合条件的LLM工具
        
        Args:
            name: 工具名称（可选）
            tool_type: 工具类型（可选）
            page: 页码，默认为1
            page_size: 每页数量，默认为20
            
        Returns:
            List[LLMToolEntity]: LLM工具实体列表
        """
        return self.llm_tool_dao.list_llm_tools(name, tool_type, page, page_size)

    def get_llm_tools_by_agent_id(self, agent_id: int) -> List[LLMToolEntity]:
        """
        根据agent_id获取关联的LLM工具列表
        
        Args:
            agent_id: Agent ID
            
        Returns:
            List[LLMToolEntity]: LLM工具实体列表
        """
        return self.llm_tool_dao.get_llm_tools_by_agent_id(agent_id)