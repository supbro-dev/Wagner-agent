from quart import Quart


def create_app(Config=None):
    """应用工厂函数"""
    app = Quart(__name__)
    app.config.from_object(Config)
    # 必须设置，推理模型推理过程可能很长，默认1分钟超时
    app.config['RESPONSE_TIMEOUT'] = 600

    # # 注册蓝图
    from web.data_analyst_controller import data_analyst_api
    app.register_blueprint(data_analyst_api, url_prefix='/agentApi/v1/dataAnalyst/')

    from web.admin_controller import admin_api
    app.register_blueprint(admin_api, url_prefix='/admin/')

    from web.assistant_controller import assistant_api
    app.register_blueprint(assistant_api, url_prefix='/agentApi/v1/assistant/')
    
    from web.json_file_controller import json_file_api
    app.register_blueprint(json_file_api, url_prefix='/api/v1/mocks')

    from web.agent_def_controller import agent_def_api
    app.register_blueprint(agent_def_api, url_prefix='/agentApi/v1/agentDef')

    return app