from dependency_injector import containers, providers
from sqlalchemy import create_engine

from config import Config
from dao.agent_def_dao import AgentDefDAO
from dao.llm_tool_dao import LLMToolDAO
from dao.query_data_task_dao import QueryDataTaskDAO


class DaoContainer(containers.DeclarativeContainer):
    """核心依赖容器"""
    # 配置项
    config = providers.Configuration()

    # 数据库引擎（单例）
    engine = providers.Singleton(
        create_engine,
        Config.MYSQL_DATABASE,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True
    )

    agent_def_dao = providers.Singleton(
        AgentDefDAO,
        engine=engine
    )

    query_data_task_dao = providers.Singleton(
        QueryDataTaskDAO,
        engine=engine
    )

    llm_tool_dao = providers.Singleton(
        LLMToolDAO,
        engine=engine
    )




# 全局容器实例
dao_container = DaoContainer()
