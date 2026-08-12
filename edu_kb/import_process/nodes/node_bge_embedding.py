# -*- coding: utf-8 -*-
from typing import List, Dict

from edu_kb.import_process.base import NodeBase
from edu_kb.import_process.state import ImportGraphState
from edu_kb.tool.logger import logger
from edu_kb.utils.embedding_utils import generate_embeddings


class NodeBGEEmbedding(NodeBase):
    """
    混合向量化节点：使用 BGE-M3 模型将切片转换为稠密 + 稀疏向量
    文本构造：课程名 / 项目名 / 章节标题 前置，增强语义。
    """

    name = "node_bge_embedding"

    BATCH_SIZE = 3

    def process(self, state: ImportGraphState):
        chunks = self._step1_validate_input(state)
        output_data = self._step2_generate_embeddings(chunks)
        return {"chunks": output_data}

    def _step1_validate_input(self, state: ImportGraphState) -> List[Dict]:
        chunks = state.get("chunks")
        if not chunks:
            raise ValueError("chunks不能为空")
        if not isinstance(chunks, list):
            raise ValueError("chunks数据类型不正确")
        return chunks

    def _step2_generate_embeddings(self, chunks: List[Dict[str, str]]) -> List[Dict[str, str]]:
        output_data = []
        for i in range(0, len(chunks), self.BATCH_SIZE):
            batch_chunks = chunks[i:i + self.BATCH_SIZE]
            texts = [self._build_text(chunk) for chunk in batch_chunks]
            vectors = generate_embeddings(texts)
            dense_vectors = vectors["dense"]
            sparse_vectors = vectors["sparse"]

            for j, chunk in enumerate(batch_chunks):
                chunk["dense_vector"] = dense_vectors[j]
                chunk["sparse_vector"] = sparse_vectors[j]
                output_data.append(chunk)
        return output_data

    @staticmethod
    def _build_text(chunk: Dict[str, str]) -> str:
        meta_parts = [
            chunk.get("course_name", ""),
            chunk.get("project_name", ""),
            chunk.get("chapter_name", ""),
            chunk.get("title", ""),
        ]
        meta = " ".join(p for p in meta_parts if p)
        return f"{meta} \n {chunk.get('content', '')}"
