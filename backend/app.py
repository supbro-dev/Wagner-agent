from config import Config
from init import create_app

app = create_app(Config)

if __name__ == '__main__':
    isDebug = False
    if Config.DEBUG != None:
        isDebug = Config.DEBUG
        app.run(host="127.0.0.1", debug=isDebug)




