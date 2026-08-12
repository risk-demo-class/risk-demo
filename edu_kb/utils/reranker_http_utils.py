# -*- coding: utf-8 -*-
from http import HTTPStatus
from typing import List

import dashscope

from edu_kb.config.config import reranker_http_config
from edu_kb.tool.logger import logger


def rerank_documents(query: str, documents: list) -> List[float]:
    """调用 DashScope 重排序模型对候选文档打分"""
    if not reranker_http_config.api_key or not reranker_http_config.model:
        raise RuntimeError("reranker 未配置（缺少 OPENAI_API_KEY 或 TEXT_RERANK_MODEL）")

    dashscope.api_key = reranker_http_config.api_key

    resp = dashscope.TextReRank.call(
        model=reranker_http_config.model,
        query=query,
        documents=documents,
        top_n=len(documents),
        return_documents=False,
        instruct=reranker_http_config.instruct,
    )

    if resp.status_code != HTTPStatus.OK:
        message = resp.message
        raise RuntimeError(
            f"reranker调用失败: status_code={resp.status_code}；message={message}"
        )

    results = resp.output.results
    scores = [0.0] * len(documents)
    for item in results:
        scores[item.index] = item.relevance_score
    return scores
