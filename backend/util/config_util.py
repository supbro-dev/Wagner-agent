import configparser
import os

# 项目根目录下自行放置private_config.ini，用来存放秘钥
config_path = os.path.join(os.path.dirname(__file__), '../private_config.ini')

# 2. 创建 ConfigParser 对象
config = configparser.ConfigParser()

# 3. 读取配置文件
try:
    config.read(config_path)
except Exception as e:
    print(f"读取配置文件失败: {e}")
    exit(1)

def read_private_config(section, key) -> str:
    return config.get(section, key)
