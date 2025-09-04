# 定义基类
from pydantic import BaseModel
from sqlalchemy import BigInteger, Column, String, Integer
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class QueryDataTaskEntity(Base):
    __tablename__ = 'query_data_task'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    business_key = Column(String)
    name = Column(String)
    task_detail = Column(String)
    invoke_times = Column(Integer, default=0)
    is_deleted = Column(Integer, default=0)
    execute_time = Column(String)

