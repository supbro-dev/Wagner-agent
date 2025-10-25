from dependency_injector import containers, providers
from sqlalchemy import create_engine

from config import Config
from dao.agent_def_dao import AgentDefDAO
from dao.llm_tool_dao import LLMToolDAO
from dao.query_data_task_dao import QueryDataTaskDAO
from dao.rag_file_dao import RagFileDAO
from dao.agent_llm_tool_dao import AgentLLMToolDAO
from service.agent.agent_def_service import AgentDefService
from service.tool.llm_tool_service import LLMToolService


class DaoContainer(containers.DeclarativeContainer):
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

    rag_file_dao = providers.Singleton(
        RagFileDAO,
        engine=engine
    )

    agent_llm_tool_dao = providers.Singleton(
        AgentLLMToolDAO,
        engine=engine
    )


class ServiceContainer(containers.DeclarativeContainer):
    # DAO容器依赖
    dao_container = providers.Container(DaoContainer)

    # 服务层提供者
    agent_def_service = providers.Singleton(
        AgentDefService,
        agent_def_dao=dao_container.agent_def_dao,
        agent_llm_tool_dao=dao_container.agent_llm_tool_dao
    )

    llm_tool_service = providers.Singleton(
        LLMToolService,
        llm_tool_dao=dao_container.llm_tool_dao
    )


# 全局容器实例
dao_container = DaoContainer()
service_container = ServiceContainer()