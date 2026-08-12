# -*- coding: utf-8 -*-
from edu_kb.config.config import edu_collection_config
from edu_kb.config.constants import (
    INTENT_COURSE_DETAIL,
    INTENT_COURSE_INTRO,
)
from edu_kb.query_process.base import NodeBase
from edu_kb.query_process.state import QueryGraphState
from edu_kb.tool.logger import logger
from edu_kb.utils.embedding_utils import generate_query_embeddings
from edu_kb.utils.milvus_utils import (
    create_hybrid_search_request,
    escape_milvus_string,
    hybrid_search,
)


COURSE_INTENTS = {INTENT_COURSE_INTRO, INTENT_COURSE_DETAIL}

COURSE_OUTPUT_FIELDS = [
    "course_id",
    "course_code",
    "course_name",
    "series_name",
    "series_code",
    "category",
    "suitable_for",
    "goals",
    "grade",
    "class_hours",
    "period",
    "description",
    "series_description",
    "source_file",
]


class NodeSearchCourse(NodeBase):
    """
    节点功能：课程检索
    在 edu_courses 集合中按向量相似度检索课程介绍/详情；
    若已确认课程名，则追加标量过滤，提升精度。
    """

    name = "node_search_course"

    def process(self, state: QueryGraphState):
        intent = state.get("intent")
        if intent not in COURSE_INTENTS:
            return {"course_results": []}

        try:
            rewritten_query = state.get("rewritten_query") or state.get("original_query")
            course_names = state.get("course_names") or []
            project_names = state.get("project_names") or []

            embeddings = generate_query_embeddings([rewritten_query])

            # 课程介绍/推荐类问题：不做课程名硬过滤，直接语义检索更符合“有哪些/推荐”场景；
            # 课程详情类问题：使用课程名过滤，过滤不到时自动回退到全量检索。
            use_filter = intent == INTENT_COURSE_DETAIL
            expr = self._build_filter(course_names, project_names) if use_filter else None

            hits = self._search(embeddings, expr)
            if not hits and expr:
                logger.info("课程名过滤无结果，回退到全量课程检索")
                hits = self._search(embeddings, None)

            logger.info(f"课程检索完成，返回{len(hits)}条")
            return {"course_results": hits}
        except Exception as e:
            logger.exception(f"课程检索失败: {e}")
            return {"course_results": []}

    def _search(self, embeddings, expr):
        reqs = create_hybrid_search_request(
            dense_vector=embeddings["dense"][0],
            sparse_vector=embeddings["sparse"][0],
            expr=expr,
            limit=10,
        )
        result = hybrid_search(
            collection_name=edu_collection_config.course_collection,
            reqs=reqs,
            ranker_weights=(0.8, 0.2),
            norm_score=True,
            output_fields=COURSE_OUTPUT_FIELDS,
            limit=10,
        )
        return result[0] if result else []

    def _build_filter(self, course_names, project_names):
        conds = []
        if course_names:
            escaped = ", ".join(f'"{escape_milvus_string(n)}"' for n in course_names)
            conds.append(f'(course_name in [{escaped}] or series_name in [{escaped}])')
        if project_names:
            escaped = ", ".join(f'"{escape_milvus_string(n)}"' for n in project_names)
            conds.append(f'course_name in [{escaped}]')
        return " and ".join(conds) if conds else None
