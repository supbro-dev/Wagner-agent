class Config:
    DEBUG  = True
    WAGNER_API_ENDPOINT = "http://localhost:8080/api/v1"
    MYSQL_DATABASE = "mysql+pymysql://wagner:wagner@127.0.0.1:3306/wagner?charset=utf8"
    REDIS_URL = "redis://127.0.0.1:6379"
    EMBEDDING_LOCAL_MODEL = "/embedding_models/bge-small-zh-v1.5/BAAI/bge-small-zh-v1___5"
    USE_VECTOR_STORE = False
    MEMORY_USE = "local"
    LLM_MODEL = "deepseek-chat"
    REASONER_LLM_MODEL = "deepseek-reasoner"
    ASSISTANT_RAG_TOP_K = 5
    ASSISTANT_RAG_SCORE_THRESHOLD = 0.5
    MD_DOC_VECTOR_CHUNK_SIZE = 1500
    MD_DOC_VECTOR_CHUNK_OVERLAP = 300
    MD_DOC_VECTOR_SEPARATORS = ["\n## ", "\n# "]

