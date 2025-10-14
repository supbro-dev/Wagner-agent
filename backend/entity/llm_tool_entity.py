from sqlalchemy import Column, BigInteger, DateTime, String, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class LLMToolType:
    HTTP_TOOL = "httpTool"
    MCP = "mcp"


class LLMToolEntity(Base):
    __tablename__ = 'llm_tool'

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='id')
    gmt_create = Column(DateTime, default=func.current_timestamp(), nullable=False, comment='创建时间')
    gmt_modified = Column(DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp(), nullable=False, comment='修改时间')
    name = Column(String(128), nullable=False, comment='工具名称')
    description = Column(Text, nullable=False, comment='工具描述信息')
    args_dict = Column(String, nullable=False, comment='参数名及描述(参数名->描述信息)')
    tool_type = Column(String(16), nullable=False, comment='工具类型(http/mcp)')
    content = Column(String, nullable=False, comment='工具内容')
    request_handle_script = Column(String, nullable=True, comment='工具请求前的处理脚本')
    response_handle_script = Column(String, nullable=True, comment='工具返回结果处理脚本')
