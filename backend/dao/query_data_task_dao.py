from sqlalchemy import select, update
from dao.base_dao import BaseDAO
from entity.query_data_task_entity import QueryDataTaskEntity


class QueryDataTaskDAO(BaseDAO):
    def find_by_name(self, business_key, name) -> QueryDataTaskEntity | None:
        """
        根据business_key和name查询QueryDataTask记录

        Args:
            business_key (str): 业务键
            name (str): 任务名称

        Returns:
            QueryDataTaskEntity: 查询到的QueryDataTaskEntity对象，未找到则返回None
        """
        def query(session):
            query = select(QueryDataTaskEntity).where(
                QueryDataTaskEntity.business_key == business_key,
                QueryDataTaskEntity.name == name,
                QueryDataTaskEntity.is_deleted == 0
            )
            result = session.execute(query).scalar_one_or_none()
            return result

        return self.execute_in_session(query)

    def find_by_id(self, id) -> QueryDataTaskEntity:
        """
        根据id查询QueryDataTask记录

        Args:
            id (int): 任务ID

        Returns:
            QueryDataTaskEntity: 查询到的QueryDataTaskEntity对象，未找到则返回None
        """
        def query(session):
            query = select(QueryDataTaskEntity).where(
                QueryDataTaskEntity.id == id,
                QueryDataTaskEntity.is_deleted == 0
            )
            result = session.execute(query).scalar_one_or_none()
            return result

        return self.execute_in_session(query)

    def save(self, task_entity: QueryDataTaskEntity) -> int:
        """
        保存QueryDataTask记录

        Args:
            task_entity (QueryDataTaskEntity): 任务实体对象

        Returns:
            int: 保存的任务ID
        """
        def query(session):
            if task_entity.id is None:
                session.add(task_entity)
            else:
                query = update(QueryDataTaskEntity).where(
                    QueryDataTaskEntity.id == task_entity.id
                ).values(
                    task_detail=task_entity.task_detail
                )
                session.execute(query)
            session.commit()
            return task_entity.id

        return self.execute_in_session(query)

    def delete(self, id, business_key):
        """
        删除QueryDataTask记录（逻辑删除）

        Args:
            id (int): 任务ID
            business_key (str): 业务键
        """
        def query(session):
            query = update(QueryDataTaskEntity).where(
                QueryDataTaskEntity.id == id,
                QueryDataTaskEntity.business_key == business_key
            ).values(
                is_deleted=1
            )
            session.execute(query)
            session.commit()

        self.execute_in_session(query)

    def update_execute_times_once(self, id, business_key):
        """
        更新任务执行次数+1

        Args:
            id (int): 任务ID
            business_key (str): 业务键
        """
        def query(session):
            stmt = (
                update(QueryDataTaskEntity)
                .where(
                    QueryDataTaskEntity.id == id,
                    QueryDataTaskEntity.business_key == business_key
                )
                .values(invoke_times=QueryDataTaskEntity.invoke_times + 1)
            )
            session.execute(stmt)
            session.commit()

        self.execute_in_session(query)

    def get_frequently_execute_top3_tasks(self, business_key, not_in_ids):
        """
        获取执行次数最多的前3个任务

        Args:
            business_key (str): 业务键
            not_in_ids (list): 排除的任务ID列表

        Returns:
            list: QueryDataTaskEntity对象列表
        """
        def query(session):
            query = select(QueryDataTaskEntity).where(
                QueryDataTaskEntity.id.not_in(not_in_ids),
                QueryDataTaskEntity.business_key == business_key,
                QueryDataTaskEntity.is_deleted == 0
            ).order_by(QueryDataTaskEntity.invoke_times.desc()).limit(3)
            return session.execute(query).scalars().all()

        return self.execute_in_session(query)

    def get_usually_execute_top3_tasks(self, business_key):
        """
        获取最近执行时间最靠前的前3个任务

        Args:
            business_key (str): 业务键

        Returns:
            list: QueryDataTaskEntity对象列表
        """
        def query(session):
            query = select(QueryDataTaskEntity).where(
                QueryDataTaskEntity.business_key == business_key,
                QueryDataTaskEntity.is_deleted == 0
            ).order_by(QueryDataTaskEntity.execute_time.desc()).limit(3)
            return session.execute(query).scalars().all()

        return self.execute_in_session(query)

    def get_all_tasks(self, business_key):
        """
        获取所有任务

        Args:
            business_key (str): 业务键

        Returns:
            list: QueryDataTaskEntity对象列表
        """
        def query(session):
            query = select(QueryDataTaskEntity).where(
                QueryDataTaskEntity.business_key == business_key,
                QueryDataTaskEntity.is_deleted == 0
            )
            return session.execute(query).scalars().all()

        return self.execute_in_session(query)
