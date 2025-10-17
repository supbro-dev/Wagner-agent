from sqlalchemy import Column, BigInteger, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class AgentLLMToolEntity(Base):
    __tablename__ = 'agent_llm_tool'

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='id')
    gmt_create = Column(DateTime, default=func.current_timestamp(), nullable=False, comment='创建时间')
    gmt_modified = Column(DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp(), nullable=False, comment='修改时间')
    agent_id = Column(BigInteger, nullable=False, comment='agentId')
    llm_tool_id = Column(BigInteger, nullable=False, comment='llm工具id')
