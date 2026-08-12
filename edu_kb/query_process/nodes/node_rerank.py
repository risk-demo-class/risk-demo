# -*- coding: utf-8 -*-
from typing import Any, Dict, List

from edu_kb.query_process.base import NodeBase
from edu_kb.query_process.state import QueryGraphState
from edu_kb.tool.logger import logger
from edu_kb.utils.reranker_http_utils import rerank_documents


class NodeRerank(NodeBase):
    """
    节点功能：重排序
    使用 Cross-Encoder（DashScope rerank）对 RRF 结果精排 + 断崖截断。
    未配置 reranker 时按 RRF 顺序兜底，不中断主流程。
    """

    name = "node_rerank"

    RERANK_MAX_TOPK = 10
    RERANK_MIN_TOPK = 2
    RERANK_GAP_RATIO = 0.25
    RERANK_GAP_ABS = 0.10
    SCORE_MIN = 0.8

    def process(self, state: QueryGraphState):
        merged_multi_docs = self._step1_merge_multi_source_docs(state)
        reranked_docs = self._step2_rerank_merged_docs(state, merged_multi_docs)
        cutoff_docs = self._step3_cliff_cutoff(reranked_docs)
        return {"reranked_docs": cutoff_docs}

    def _step1_merge_multi_source_docs(self, state):
        merged_multi_docs = []
        for rrf_doc in state.get("rrf_chunks") or []:
            merged_multi_docs.append({
                "title": rrf_doc.get("chapter_name") or rrf_doc.get("file_title") or rrf_doc.get("title"),
                "content": rrf_doc.get("content"),
                "chunk_id": rrf_doc.get("chunk_id"),
                "url": rrf_doc.get("source_path"),
                "source": "local",
                "course_name": rrf_doc.get("course_name", ""),
                "project_name": rrf_doc.get("project_name", ""),
                "chapter_name": rrf_doc.get("chapter_name", ""),
                "file_title": rrf_doc.get("file_title", ""),
                "content_type": rrf_doc.get("content_type", ""),
            })

        for web_doc in state.get("web_search_docs") or []:
            merged_multi_docs.append({
                "title": web_doc.get("title"),
                "content": web_doc.get("snippet"),
                "chunk_id": None,
                "url": web_doc.get("url"),
                "source": "web",
            })
        return merged_multi_docs

    def _step2_rerank_merged_docs(self, state, merged_multi_docs):
        if not merged_multi_docs:
            return []
        user_query = state.get("rewritten_query") or state.get("original_query")
        contents = [doc.get("content") or "" for doc in merged_multi_docs]

        try:
            rerank_scores = rerank_documents(user_query, contents)
            reranked_docs = [
                {"score": score, **doc}
                for doc, score in zip(merged_multi_docs, rerank_scores)
            ]
        except Exception as e:
            logger.warning(f"reranker 不可用，使用 RRF 顺序兜底：{e}")
            reranked_docs = [
                {"score": 1.0 - idx * 0.01, **doc}
                for idx, doc in enumerate(merged_multi_docs)
            ]

        return sorted(reranked_docs, key=lambda x: x.get("score"), reverse=True)

    def _step3_cliff_cutoff(self, ranked_docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not ranked_docs:
            return []

        # 兜底分数（RRF 顺序）不执行断崖截断
        if ranked_docs[0].get("score") > 0.99 and ranked_docs[0].get("chunk_id") is None:
            return ranked_docs[:self.RERANK_MAX_TOPK]

        if ranked_docs[0].get("score") < self.SCORE_MIN:
            return []

        upper_bound = min(self.RERANK_MAX_TOPK, len(ranked_docs))
        lower_bound = min(self.RERANK_MIN_TOPK, upper_bound)
        cutoff_pos = upper_bound

        for index in range(lower_bound - 1, upper_bound - 1):
            current_score = ranked_docs[index].get("score")
            next_score = ranked_docs[index + 1].get("score")
            abs_gap = current_score - next_score
            rel_gap = abs_gap / (abs(current_score) + 1e-6)
            if abs_gap >= self.RERANK_GAP_ABS or rel_gap >= self.RERANK_GAP_RATIO:
                cutoff_pos = index + 1
                break
        return ranked_docs[:cutoff_pos]
