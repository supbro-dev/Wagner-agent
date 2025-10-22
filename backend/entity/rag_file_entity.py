# rag_file_entity.py
from sqlalchemy import Column, Integer, String, Text, DateTime, Index, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class RagFileEntity(Base):
    """
    简易rag文件记录实体类
    对应数据库表: rag_file
    """

    __tablename__ = 'rag_file'

    # id字段，主键，自增
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='id')

    # 文件名称，最大长度128字符
    file_name = Column(String, nullable=False, comment='文件名称')

    # 内容，文本类型
    content = Column(String, nullable=False, comment='内容')

    # 业务键，最大长度128字符
    business_key = Column(String, nullable=False, comment='业务键')

