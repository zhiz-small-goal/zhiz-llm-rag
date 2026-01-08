
"""RAG 配置集中管理。

按需修改这里的常量，即可切换数据库路径、本地 LLM 端口等。
"""

# Chroma 向量库配置
CHROMA_DB_PATH = "chroma_db"
CHROMA_COLLECTION = "rag_chunks"

# 向量模型配置（需要与建库时保持一致）
EMBED_MODEL_NAME = "BAAI/bge-m3"
EMBED_DEVICE = "cpu"  # 或者 "cuda:0"
EMBED_BATCH = 32

# LLM 调用配置（假定为 OpenAI 兼容接口；本地 Qwen/LM Studio/Ollama 均可按此适配）
LLM_BASE_URL = "http://localhost:8000/v1"  # 示例：本地服务地址
LLM_API_KEY = "EMPTY"  # 部分本地部署会忽略 key，但字段仍需存在
LLM_MODEL = "qwen2.5-7b-instruct-q4_k_m.gguf"  # 按实际本地模型名称调整
LLM_MAX_TOKENS = 1024

# RAG 检索与上下文拼接配置
RAG_TOP_K = 5
RAG_MAX_CONTEXT_CHARS = 12000  # 控制拼接到 prompt 中的总字符数
