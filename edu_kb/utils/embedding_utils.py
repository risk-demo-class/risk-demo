# -*- coding: utf-8 -*-
from pymilvus.model.hybrid import BGEM3EmbeddingFunction
from edu_kb.config.config import embedding_config
from edu_kb.tool.logger import logger

# 1. 定义模型单例对象，避免重复初始化
_bge_m3_ef = None


def get_bge_m3_ef():
    """获取 BGE-M3 模型单例对象，自动加载环境变量配置"""
    global _bge_m3_ef
    if _bge_m3_ef is not None:
        return _bge_m3_ef

    try:
        _bge_m3_ef = BGEM3EmbeddingFunction(
            model_name=embedding_config.bge_m3_path,
            device=embedding_config.bge_device,
            use_fp16=embedding_config.bge_fp16,
        )
    except Exception as e:
        logger.error(f"BGEM3初始化失败: {e}")
    return _bge_m3_ef


def generate_embeddings(texts):
    """为文本生成向量嵌入：包含 dense 和 sparse 向量"""
    model = get_bge_m3_ef()
    embeddings = model.encode_documents(texts)
    return {
        "dense": [emb.tolist() for emb in embeddings["dense"]],
        "sparse": [
            {int(k): float(v) for k, v in zip(row.indices, row.data)}
            for row in embeddings["sparse"]
        ],
    }


def generate_query_embeddings(texts):
    """为查询文本生成向量嵌入（与文档编码保持同一模型）"""
    model = get_bge_m3_ef()
    embeddings = model.encode_queries(texts)
    return {
        "dense": [emb.tolist() for emb in embeddings["dense"]],
        "sparse": [
            {int(k): float(v) for k, v in zip(row.indices, row.data)}
            for row in embeddings["sparse"]
        ],
    }
