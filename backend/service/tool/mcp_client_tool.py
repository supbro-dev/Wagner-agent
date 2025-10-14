import json

from langchain_mcp_adapters.client import MultiServerMCPClient

from entity.llm_tool_entity import LLMToolEntity


async def create_mcp_client_tools(lms_tool_entity_list: list[LLMToolEntity]):
    """
    创建一个新的MCP客户端工具

    参数:
        lms_tool_entity (LLMToolEntity): 工具实体对象

    返回:
        BaseTool: 构造好的LangChain工具对象
    """
    connections = {}
    for tool_entity in lms_tool_entity_list:
        connections[tool_entity.name] = json.loads(tool_entity.content)

    client = MultiServerMCPClient(connections)
    tools = await client.get_tools()

    return tools