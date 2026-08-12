# -*- coding: utf-8 -*-
from typing import Dict, Any

from pymilvus import DataType

from edu_kb.config.config import edu_collection_config
from edu_kb.import_process.base import NodeBase
from edu_kb.import_process.state import ImportGraphState
from edu_kb.tool.logger import logger
from edu_kb.utils.milvus_utils import get_milvus_client, escape_milvus_string


class NodeImportMilvus(NodeBase):
    """
    导入向量库节点：教育文档切片数据持久化到 Milvus
    集合：edu_chunks，字段覆盖课程名 / 项目名 / 章节名 / 内容类型 / 来源信息。
    """

    name = "node_import_milvus"

    def process(self, state: ImportGraphState):
        file_title, chunks, vector_dimension, content_type = self._step1_check_input(state)
        self._step2_prepare_collection(vector_dimension)
        self._step3_clean_old_data(file_title, content_type)
        updated_chunks = self._step4_insert_data(state, chunks)
        return {"chunks": updated_chunks}

    def _step1_check_input(self, state: Dict[str, Any]):
        file_title = state.get("file_title")
        if not file_title:
            raise ValueError("file_title不能为空")
        chunks = state.get("chunks")
        if not chunks:
            raise ValueError("chunks不能为空")
        if not isinstance(chunks, list):
            raise ValueError("chunks数据类型不正确")

        first_chunk = chunks[0]
        if "dense_vector" not in first_chunk:
            raise ValueError("错误: 数据中缺失dense_vector字段")
        if "sparse_vector" not in first_chunk:
            raise ValueError("错误: 数据中缺失sparse_vector字段")

        vector_dimension = len(first_chunk["dense_vector"])
        content_type = state.get("content_type") or "course_doc"
        return file_title, chunks, vector_dimension, content_type

    def _step2_prepare_collection(self, vector_dimension: int):
        milvus_client = get_milvus_client()
        collection_name = edu_collection_config.chunks_collection
        if not milvus_client.has_collection(collection_name):
            self._create_chunks_collection(collection_name, milvus_client, vector_dimension)

    def _create_chunks_collection(self, collection_name, milvus_client, vector_dimension):
        schema = milvus_client.create_schema(auto_id=True, enable_dynamic_field=True)
        schema.add_field(field_name="chunk_id", datatype=DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field(field_name="content", datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(field_name="title", datatype=DataType.VARCHAR, max_length=255)
        schema.add_field(field_name="parent_title", datatype=DataType.VARCHAR, max_length=255)
        schema.add_field(field_name="part", datatype=DataType.INT8)
        schema.add_field(field_name="file_title", datatype=DataType.VARCHAR, max_length=255)
        schema.add_field(field_name="content_type", datatype=DataType.VARCHAR, max_length=50)
        schema.add_field(field_name="course_name", datatype=DataType.VARCHAR, max_length=255)
        schema.add_field(field_name="project_name", datatype=DataType.VARCHAR, max_length=255)
        schema.add_field(field_name="chapter_name", datatype=DataType.VARCHAR, max_length=255)
        schema.add_field(field_name="question_bank_name", datatype=DataType.VARCHAR, max_length=255)
        schema.add_field(field_name="question_code", datatype=DataType.VARCHAR, max_length=255)
        schema.add_field(field_name="question_type", datatype=DataType.VARCHAR, max_length=50)
        schema.add_field(field_name="source_path", datatype=DataType.VARCHAR, max_length=500)
        schema.add_field(field_name="sparse_vector", datatype=DataType.SPARSE_FLOAT_VECTOR)
        schema.add_field(field_name="dense_vector", datatype=DataType.FLOAT_VECTOR, dim=vector_dimension)

        index_params = milvus_client.prepare_index_params()
        index_params.add_index(
            field_name="dense_vector",
            index_name="dense_vector_index",
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )
        index_params.add_index(
            field_name="sparse_vector",
            index_name="sparse_inverted_index",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="IP",
            params={"inverted_index_algo": "DAAT_MAXSCORE", "normalize": True, "quantization": "none"},
        )
        milvus_client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params,
        )
        logger.info(f"教育文档切片集合创建成功：{collection_name}")

    def _step3_clean_old_data(self, file_title, content_type):
        safe_file_title = escape_milvus_string(file_title)
        safe_content_type = escape_milvus_string(content_type)
        filter_expr = f'file_title=="{safe_file_title}" and content_type=="{safe_content_type}"'
        milvus_client = get_milvus_client()
        milvus_client.delete(
            collection_name=edu_collection_config.chunks_collection,
            filter=filter_expr,
        )

    def _step4_insert_data(self, state, chunks):
        # 补齐集合 Schema 中声明的教育元数据字段（防止缺字段导致入库失败）
        defaults = {
            "content_type": state.get("content_type") or "course_doc",
            "question_bank_name": state.get("question_bank_name") or "",
            "question_code": "",
            "question_type": "",
            "source_path": state.get("source_path") or "",
        }
        for chunk in chunks:
            for key, value in defaults.items():
                chunk.setdefault(key, value)

        milvus_client = get_milvus_client()
        result = milvus_client.insert(
            collection_name=edu_collection_config.chunks_collection,
            data=chunks,
        )
        inserted_ids = result.get("ids")
        for idx, item in enumerate(chunks):
            item["chunk_id"] = inserted_ids[idx] if idx < len(inserted_ids) else None
        return chunks
