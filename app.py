from flask import Blueprint, jsonify, request
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from config import Config
from web.agent_controller import agentApi

app = Flask(__name__)
app.config.from_object(Config)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://wagner:wagner@127.0.0.1:3306/wagner?charset=utf8'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 初始化 SQLAlchemy
db = SQLAlchemy(app)
db.init_app(app)

# 注册蓝图
app.register_blueprint(agentApi, url_prefix='/agentApi/v1/agent')

if __name__ == '__main__':
    isDebug = False
    if Config.DEBUG != None:
        isDebug = Config.DEBUG
    app.run(host="127.0.0.1", debug=isDebug)



