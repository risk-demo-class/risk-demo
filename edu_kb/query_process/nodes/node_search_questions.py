# -*- coding: utf-8 -*-
from edu_kb.config.config import edu_collection_config
from edu_kb.config.constants import INTENT_QUESTION
from edu_kb.query_process.base import NodeBase
from edu_kb.query_process.state import QueryGraphState
from edu_kb.tool.logger import logger
from edu_kb.utils.embedding_utils import generate_query_embeddings
from edu_kb.utils.milvus_utils import (
    create_hybrid_search_request,
    escape_milvus_string,
    hybrid_search,
)


QUESTION_OUTPUT_FIELDS = [
    "question_id",
    "question_code",
    "bank_name",
    "bank_code",
    "question_type",
    "question_text",
    "options",
    "answer",
    "analysis",
    "source_file",
]


class NodeSearchQuestions(NodeBase):
    """
    节点功能：题目检索
    在 edu_questions 集合中按向量相似度检索题目；
    若已确认题库名，则追加标量过滤。
    """

    name = "node_search_questions"

    def process(self, state: QueryGraphState):
        intent = state.get("intent")
        if intent != INTENT_QUESTION:
            return {"question_results": []}

        try:
            rewritten_query = state.get("rewritten_query") or state.get("original_query")
            bank_names = state.get("bank_names") or []
            knowledge_points = state.get("knowledge_points") or []

            search_text = rewritten_query
            if knowledge_points:
                search_text = rewritten_query + " " + " ".join(knowledge_points)

            embeddings = generate_query_embeddings([search_text])
            expr = self._build_filter(bank_names)
            reqs = create_hybrid_search_request(
                dense_vector=embeddings["dense"][0],
                sparse_vector=embeddings["sparse"][0],
                expr=expr,
                limit=10,
            )
            result = hybrid_search(
                collection_name=edu_collection_config.question_collection,
                reqs=reqs,
                ranker_weights=(0.8, 0.2),
                norm_score=True,
                output_fields=QUESTION_OUTPUT_FIELDS,
                limit=10,
            )
            hits = result[0] if result else []
            logger.info(f"题目检索完成，返回{len(hits)}条")
            return {"question_results": hits}
        except Exception as e:
            logger.exception(f"题目检索失败: {e}")
            return {"question_results": []}

    def _build_filter(self, bank_names):
        if bank_names:
            escaped = ", ".join(f'"{escape_milvus_string(n)}"' for n in bank_names)
            return f"bank_name in [{escaped}]"
        return None
