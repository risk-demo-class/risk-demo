# -*- coding: utf-8 -*-
from pymilvus import MilvusClient, AnnSearchRequest, WeightedRanker

from edu_kb.config.config import milvus_config
from edu_kb.tool.logger import logger

# 1. 定义全局单例对象
_milvus_client = None


def get_milvus_client():
    """获取 Milvus 客户端对象（延迟加载单例）"""
    global _milvus_client
    if _milvus_client is not None:
        return _milvus_client

    if not milvus_config.milvus_url:
        raise ValueError("Milvus URL cannot be empty")

    _milvus_client = MilvusClient(uri=milvus_config.milvus_url)
    return _milvus_client


def escape_milvus_string(value: str) -> str:
    """Milvus 过滤表达式中字符串的安全转义（防止解析失败）"""
    if value is None:
        return ""
    value = str(value)
    value = value.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")
    return value


def create_hybrid_search_request(
        dense_vector, sparse_vector, dense_params=None, sparse_params=None,
        expr=None, limit=5,
):
    """组装混合向量搜索的搜索条件"""
    if dense_params is None:
        dense_params = {"metric_type": "COSINE"}
    if sparse_params is None:
        sparse_params = {"metric_type": "IP"}

    request_dense = AnnSearchRequest(
        data=[dense_vector],
        anns_field="dense_vector",
        param=dense_params,
        expr=expr,
        limit=limit,
    )
    request_sparse = AnnSearchRequest(
        data=[sparse_vector],
        anns_field="sparse_vector",
        param=sparse_params,
        expr=expr,
        limit=limit,
    )
    return [request_dense, request_sparse]


def hybrid_search(
        collection_name, reqs,
        ranker_weights=(0.8, 0.2), norm_score=True,
        limit=5, output_fields=None,
):
    """执行混合向量检索（稠密 + 稀疏）"""
    try:
        rerank = WeightedRanker(ranker_weights[0], ranker_weights[1], norm_score=norm_score)
        client = get_milvus_client()
        res = client.hybrid_search(
            collection_name=collection_name,
            reqs=reqs,
            ranker=rerank,
            limit=limit,
            output_fields=output_fields,
        )
        logger.info("混合向量搜索完毕")
        return res
    except Exception as e:
        logger.exception(f"混合向量搜索失败: {e}")
        raise RuntimeError("混合向量搜索失败") from e


def query_collection(collection_name, filter_expr, limit=10, output_fields=None):
    """标量过滤查询（用于课程/题库的精确匹配兜底）"""
    try:
        client = get_milvus_client()
        res = client.query(
            collection_name=collection_name,
            filter=filter_expr,
            limit=limit,
            output_fields=output_fields,
        )
        return res
    except Exception as e:
        logger.exception(f"集合查询失败: {e}")
        return []
