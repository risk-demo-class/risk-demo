# -*- coding: utf-8 -*-
from edu_kb.config.config import edu_collection_config
from edu_kb.config.constants import DOC_CONTENT_TYPES
from edu_kb.query_process.base import NodeBase
from edu_kb.query_process.state import QueryGraphState
from edu_kb.tool.logger import logger
from edu_kb.utils.embedding_utils import generate_query_embeddings
from edu_kb.utils.milvus_utils import (
    create_hybrid_search_request,
    escape_milvus_string,
    hybrid_search,
)


DOC_OUTPUT_FIELDS = [
    "chunk_id",
    "content",
    "title",
    "parent_title",
    "file_title",
    "content_type",
    "course_name",
    "project_name",
    "chapter_name",
    "source_path",
]


class NodeSearchDocs(NodeBase):
    """
    节点功能：文档/切片检索
    在 edu_chunks 集合中按向量相似度检索课程文档与项目文档切片，
    支持按课程名 / 项目名过滤。
    """

    name = "node_search_docs"

    def process(self, state: QueryGraphState):
        try:
            rewritten_query = state.get("rewritten_query") or state.get("original_query")
            course_names = state.get("course_names") or []
            project_names = state.get("project_names") or []

            embeddings = generate_query_embeddings([rewritten_query])
            expr = self._build_filter(course_names, project_names)
            reqs = create_hybrid_search_request(
                dense_vector=embeddings["dense"][0],
                sparse_vector=embeddings["sparse"][0],
                expr=expr,
                limit=10,
            )
            result = hybrid_search(
                collection_name=edu_collection_config.chunks_collection,
                reqs=reqs,
                ranker_weights=(0.8, 0.2),
                norm_score=True,
                output_fields=DOC_OUTPUT_FIELDS,
                limit=10,
            )
            hits = result[0] if result else []
            logger.info(f"文档检索完成，返回{len(hits)}条")
            return {"embedding_chunks": hits}
        except Exception as e:
            logger.exception(f"文档检索失败: {e}")
            return {"embedding_chunks": []}

    def _build_filter(self, course_names, project_names):
        conds = []
        type_escaped = ", ".join(f'"{t}"' for t in DOC_CONTENT_TYPES)
        conds.append(f"content_type in [{type_escaped}]")
        if course_names:
            escaped = ", ".join(f'"{escape_milvus_string(n)}"' for n in course_names)
            conds.append(f"course_name in [{escaped}]")
        if project_names:
            escaped = ", ".join(f'"{escape_milvus_string(n)}"' for n in project_names)
            conds.append(f"project_name in [{escaped}]")
        return " and ".join(conds)
