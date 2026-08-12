# -*- coding: utf-8 -*-
import os
from dataclasses import dataclass
from dotenv import load_dotenv

# .env 位于项目根目录
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.env"))
load_dotenv(dotenv_path=env_path, override=True)


@dataclass
class LLMConfig:
    base_url: str
    api_key: str
    vl_model: str
    llm_model: str
    item_model: str
    llm_temperature: float


lm_config = LLMConfig(
    base_url=os.getenv("OPENAI_API_BASE"),
    api_key=os.getenv("OPENAI_API_KEY"),
    vl_model=os.getenv("VL_MODEL"),
    llm_model=os.getenv("LLM_DEFAULT_MODEL"),
    item_model=os.getenv("ITEM_MODEL"),
    llm_temperature=float(os.getenv("LLM_DEFAULT_TEMPERATURE", 0.1)),
)


@dataclass
class MinIOConfig:
    endpoint: str
    access_key: str
    secret_key: str
    bucket_name: str
    img_dir: str


minio_config = MinIOConfig(
    endpoint=os.getenv("MINIO_ENDPOINT"),
    access_key=os.getenv("MINIO_ACCESS_KEY"),
    secret_key=os.getenv("MINIO_SECRET_KEY"),
    bucket_name=os.getenv("MINIO_BUCKET_NAME"),
    img_dir=os.getenv("MINIO_IMG_DIR"),
)


@dataclass
class EmbeddingConfig:
    bge_m3_path: str
    bge_m3: str
    bge_device: str
    bge_fp16: bool


embedding_config = EmbeddingConfig(
    bge_m3_path=os.getenv("BGE_M3_PATH"),
    bge_m3=os.getenv("BGE_M3"),
    bge_device=os.getenv("BGE_DEVICE"),
    # 特殊处理：将 .env 中的 1/0 转为布尔值，兼容常见的数字/字符串格式
    bge_fp16=os.getenv("BGE_FP16") in ("1", "True", "true", 1),
)


@dataclass
class MilvusConfig:
    milvus_url: str
    chunks_collection: str
    item_name_collection: str


milvus_config = MilvusConfig(
    milvus_url=os.getenv("MILVUS_URL"),
    # 兼容旧配置：CHUNKS_COLLECTION / ITEM_NAME_COLLECTION
    chunks_collection=os.getenv("EDU_CHUNKS_COLLECTION") or os.getenv("CHUNKS_COLLECTION"),
    item_name_collection=os.getenv("EDU_ENTITIES_COLLECTION") or os.getenv("ITEM_NAME_COLLECTION"),
)


@dataclass
class EduCollectionConfig:
    """教育知识库专用集合配置"""
    chunks_collection: str
    course_collection: str
    question_collection: str
    entity_collection: str


edu_collection_config = EduCollectionConfig(
    chunks_collection=os.getenv("EDU_CHUNKS_COLLECTION") or "edu_chunks",
    course_collection=os.getenv("EDU_COURSES_COLLECTION") or "edu_courses",
    question_collection=os.getenv("EDU_QUESTIONS_COLLECTION") or "edu_questions",
    entity_collection=os.getenv("EDU_ENTITIES_COLLECTION") or "edu_entities",
)


@dataclass
class MongoConfig:
    mongo_url: str
    mongo_db_name: str


mongo_config = MongoConfig(
    mongo_url=os.getenv("MONGO_URL"),
    mongo_db_name=os.getenv("MONGO_DB_NAME"),
)


# 定义 mcp 的服务配置（联网搜索，可选项）
@dataclass
class McpConfig:
    mcp_base_url: str
    api_key: str


mcp_config = McpConfig(
    mcp_base_url=os.getenv("MCP_DASHSCOPE_BASE_URL"),
    api_key=os.getenv("OPENAI_API_KEY"),
)


@dataclass
class RerankerHttpConfig:
    model: str
    instruct: str
    api_key: str
    base_url: str


reranker_http_config = RerankerHttpConfig(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL_DASHSCOPE"),
    model=os.getenv("TEXT_RERANK_MODEL"),
    instruct=os.getenv("TEXT_RERANK_INSTRUCT"),
)


@dataclass
class ChunkConfig:
    max_length: int
    min_length: int
    window_overlap: int


chunk_config = ChunkConfig(
    max_length=int(os.getenv("DEFAULT_MAX_CONTENT_LENGTH", 1200)),
    min_length=int(os.getenv("DEFAULT_MIN_CONTENT_LENGTH", 200)),
    window_overlap=int(os.getenv("DEFAULT_WINDOW_OVERLAP", 100)),
)


@dataclass
class FileUploadConfig:
    data_based_root_dir: str


file_upload_config = FileUploadConfig(
    data_based_root_dir=os.getenv("DATA_BASED_ROOT_DIR"),
)
