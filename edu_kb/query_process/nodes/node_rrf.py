# -*- coding: utf-8 -*-
from typing import List

from edu_kb.query_process.base import NodeBase
from edu_kb.query_process.state import QueryGraphState
from edu_kb.tool.logger import logger


class NodeRrf(NodeBase):
    """
    节点功能：Reciprocal Rank Fusion（倒排融合）
    将多路召回结果（向量检索、HyDE 检索）按排名融合排序。
    """

    name = "node_rrf"

    def process(self, state: QueryGraphState):
        embedding_chunks = state.get("embedding_chunks") or []
        hyde_embedding_chunks = state.get("hyde_embedding_chunks") or []

        embedding_search_list = [
            doc.get("entity") for doc in embedding_chunks if isinstance(doc, dict)
        ]
        hyde_search_list = [
            doc.get("entity") for doc in hyde_embedding_chunks if isinstance(doc, dict)
        ]

        rrf_inputs = [
            (embedding_search_list, 1.0),
            (hyde_search_list, 0.8),
        ]
        rrf_merge_results = self._rrf_merge(rrf_inputs, max_results=5)
        rrf_chunks = [doc for doc, _ in rrf_merge_results]
        return {"rrf_chunks": rrf_chunks}

    def _rrf_merge(self, rrf_inputs, k: int = 60, max_results: int = None) -> List:
        chunk_scores = {}
        chunk_data = {}

        for rrf_input, weight in rrf_inputs:
            for rank, doc in enumerate(rrf_input, start=1):
                chunk_id = doc.get("chunk_id")
                if chunk_id is None:
                    continue
                chunk_scores[chunk_id] = chunk_scores.get(chunk_id, 0.0) + weight / (k + rank)
                chunk_data.setdefault(chunk_id, doc)

        unsorted_results = [(chunk_data[cid], score) for cid, score in chunk_scores.items()]
        sorted_results = sorted(unsorted_results, key=lambda x: x[1], reverse=True)
        return sorted_results[:max_results] if max_results else sorted_results
