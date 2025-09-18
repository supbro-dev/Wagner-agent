class Config:
    DEBUG  = True
    WAGNER_API_ENDPOINT = "http://localhost:8080/api/v1"
    MYSQL_DATABASE = "mysql+pymysql://wagner:wagner@127.0.0.1:3306/wagner?charset=utf8"
    REDIS_URL = "redis://127.0.0.1:6379"
    EMBEDDING_LOCAL_MODEL = "/embedding_models/bge-small-zh-v1.5/BAAI/bge-small-zh-v1___5"
    USE_VECTOR_STORE = False
    MEMORY_USE = "remote"
