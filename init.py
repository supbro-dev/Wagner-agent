from flask import Flask
from sqlalchemy import create_engine

from config import Config

# 创建引擎（连接数据库）
engine = create_engine(Config.MYSQL_DATABASE, echo=True)

def create_app(Config=None):
    """应用工厂函数"""
    app = Flask(__name__)
    app.config.from_object(Config)

    # 注册蓝图
    from web.work_group_agent_controller import agentApi
    app.register_blueprint(agentApi, url_prefix='/agentApi/v1/agent')

    from web.admin_controller import adminApi
    app.register_blueprint(adminApi, url_prefix='/admin/')

    return app