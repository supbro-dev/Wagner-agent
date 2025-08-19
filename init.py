from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine

# db = SQLAlchemy()

# 创建引擎（连接数据库）
engine = create_engine('mysql+pymysql://wagner:wagner@127.0.0.1:3306/wagner?charset=utf8', echo=True)

def create_app(Config=None):
    """应用工厂函数"""
    app = Flask(__name__)
    app.config.from_object(Config)
    # app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://wagner:wagner@127.0.0.1:3306/wagner?charset=utf8'
    # app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # # 初始化扩展
    # db.init_app(app)

    # 注册蓝图
    from web.agent_controller import agentApi
    app.register_blueprint(agentApi, url_prefix='/agentApi/v1/agent')

    return app