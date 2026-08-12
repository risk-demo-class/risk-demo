# -*- coding: utf-8 -*-
from edu_kb.config.config import edu_collection_config
from edu_kb.config.constants import DOC_CONTENT_TYPES
from edu_kb.query_process.base import NodeBase
from edu_kb.query_process.prompt import HYDE_PROMPT
from edu_kb.query_process.state import QueryGraphState
from edu_kb.query_process.nodes.node_search_docs import DOC_OUTPUT_FIELDS
from edu_kb.tool.logger import logger
from edu_kb.utils.embedding_utils import generate_query_embeddings
from edu_kb.utils.llm_utils import get_llm_client
from edu_kb.utils.milvus_utils import (
    create_hybrid_search_request,
    escape_milvus_string,
    hybrid_search,
)


class NodeSearchDocsHyde(NodeBase):
    """
    节点功能：HyDE（Hypothetical Document Embedding）文档检索
    先让 LLM 生成假设性答案，再与改写问题拼接后进行向量检索，提高召回率。
    """

    name = "node_search_docs_hyde"

    def process(self, state: QueryGraphState):
        try:
            rewritten_query = state.get("rewritten_query") or state.get("original_query")
            course_names = state.get("course_names") or []
            project_names = state.get("project_names") or []

            hyde_doc = self._create_hyde_doc(rewritten_query)
            search_text = rewritten_query + "\n" + hyde_doc
            embeddings = generate_query_embeddings([search_text])
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
            logger.info(f"HyDE文档检索完成，返回{len(hits)}条")
            return {"hyde_embedding_chunks": hits}
        except Exception as e:
            logger.exception(f"HyDE文档检索失败: {e}")
            return {"hyde_embedding_chunks": []}

    def _create_hyde_doc(self, rewritten_query):
        try:
            llm = get_llm_client()
            hyde_prompt = HYDE_PROMPT.format(rewritten_query=rewritten_query)
            response = llm.invoke(hyde_prompt)
            return response.content or ""
        except Exception as e:
            logger.exception(f"假设性文档生成失败: {e}")
            return ""

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
