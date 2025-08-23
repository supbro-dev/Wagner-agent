from flask import Flask
from sqlalchemy import create_engine

# 创建引擎（连接数据库）
engine = create_engine('mysql+pymysql://wagner:wagner@127.0.0.1:3306/wagner?charset=utf8', echo=True)

def create_app(Config=None):
    """应用工厂函数"""
    app = Flask(__name__)
    app.config.from_object(Config)

    # 注册蓝图
    from web.agent_controller import agentApi
    app.register_blueprint(agentApi, url_prefix='/agentApi/v1/agent')

    return app