from sqlalchemy import BigInteger, Column, String, Text, DateTime
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class AgentDefType:
    ASSISTANT = "assistant"
    DATA_ANALYST = "dataAnalyst"

class AgentDefEntity(Base):
    __tablename__ = 'agent_def'

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='id')
    gmt_create = Column(DateTime, default=datetime.now, nullable=False, comment='创建时间')
    gmt_modified = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='修改时间')
    business_key = Column(String(256), nullable=False, comment='业务键')
    name = Column(String(256), nullable=False, comment='名称')
    system_prompt = Column(Text, nullable=False, comment='系统提示词')
    agent_type = Column(String(32), nullable=False, comment='类型(数据员/助理)')