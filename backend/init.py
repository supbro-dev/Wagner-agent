from quart import Quart


def create_app(Config=None):
    """应用工厂函数"""
    app = Quart(__name__)
    app.config.from_object(Config)
    # 必须设置，推理模型推理过程可能很长，默认1分钟超时
    app.config['RESPONSE_TIMEOUT'] = 600

    # # 注册蓝图
    from web.data_analyst_controller import dataAnalystApi
    app.register_blueprint(dataAnalystApi, url_prefix='/agentApi/v1/dataAnalyst/')

    from web.admin_controller import adminApi
    app.register_blueprint(adminApi, url_prefix='/admin/')

    from web.assistant_controller import assistantApi
    app.register_blueprint(assistantApi, url_prefix='/agentApi/v1/assistant/')
    
    from web.json_file_controller import jsonFileApi
    app.register_blueprint(jsonFileApi,  url_prefix='/api/v1/mocks')

    return app