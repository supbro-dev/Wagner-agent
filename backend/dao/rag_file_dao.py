# rag_file_dao.py
from sqlalchemy import select

from dao.base_dao import BaseDAO
from entity.rag_file_entity import RagFileEntity


class RagFileDAO(BaseDAO):
    def find_by_business_key(self, business_key) -> list[RagFileEntity]:
        """
        根据business_key查询RagFile记录

        Args:
            business_key (str): 业务键

        Returns:
            list[RagFileEntity]: 查询到的RagFileEntity对象列表
        """
        def query(session):
            query = select(RagFileEntity).where(RagFileEntity.business_key == business_key)
            result = session.execute(query).scalars().all()
            return result

        return self.execute_in_session(query)

    def find_by_business_key_and_file_name(self, business_key, file_name) -> RagFileEntity:
        """
        根据business_key和file_name查询RagFile记录

        Args:
            business_key (str): 业务键
            file_name (str): 文件名称

        Returns:
            RagFileEntity: 查询到的RagFileEntity对象，未找到则返回None
        """
        def query(session):
            query = select(RagFileEntity).where(
                RagFileEntity.business_key == business_key,
                RagFileEntity.file_name == file_name
            )
            result = session.execute(query).scalar_one_or_none()
            return result

        return self.execute_in_session(query)

    def add_rag_file(self, rag_file_entity: RagFileEntity) -> RagFileEntity:
        """
        添加一个新的RagFile记录

        Args:
            rag_file_entity (RagFileEntity): 要添加的RagFile实体对象

        Returns:
            RagFileEntity: 添加后的RagFile实体对象
        """
        def query(session):
            session.add(rag_file_entity)
            session.flush()  # 确保获取到ID等数据库生成的字段
            return rag_file_entity

        return self.execute_in_session(query)

    def find_by_id(self, file_id):
        """
        根据ID查询RagFile记录

        Args:
            file_id (int): 文件ID

        Returns:
            RagFileEntity: 查询到的RagFileEntity对象，未找到则返回None
        """
        def query(session):
            query = select(RagFileEntity).where(RagFileEntity.id == file_id)
            result = session.execute(query).scalar_one_or_none()
            return result
        return self.execute_in_session(query)

    def delete_by_id(self, file_id):
        """
        根据ID删除RagFile记录

        Args:
            file_id (int): 文件ID

        Returns:
            int: 删除的记录数
        """
        def query(session):
            query = select(RagFileEntity).where(RagFileEntity.id == file_id)
            result = session.execute(query).scalar_one_or_none()
            if result:
                session.delete(result)
                session.flush()
                return 1
            return 0
        return self.execute_in_session(query)

