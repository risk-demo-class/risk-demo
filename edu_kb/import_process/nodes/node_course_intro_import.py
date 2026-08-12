# -*- coding: utf-8 -*-
import json
from typing import List, Dict

from pymilvus import DataType

from edu_kb.config.config import edu_collection_config
from edu_kb.config.constants import (
    CONTENT_TYPE_COURSE_INTRO,
    ENTITY_TYPE_COURSE,
)
from edu_kb.import_process.base import NodeBase
from edu_kb.import_process.state import ImportGraphState
from edu_kb.tool.logger import logger
from edu_kb.utils.course_intro_parser import (
    parse_course_intro,
    build_course_search_text,
)
from edu_kb.utils.embedding_utils import generate_embeddings
from edu_kb.utils.milvus_utils import get_milvus_client, escape_milvus_string


class NodeCourseIntroImport(NodeBase):
    """
    课程介绍入库节点：
      1. 解析课程介绍 Markdown -> 课程记录（每门课程一条）
      2. 向量化课程检索文本
      3. 写入 Milvus 的 edu_courses 集合
      4. 注册课程名 / 系列名知识实体
    """

    name = "node_course_intro_import"

    BATCH_SIZE = 20

    def process(self, state: ImportGraphState):
        md_content = state.get("md_content")
        file_title = state.get("file_title")
        if not md_content:
            raise ValueError("课程介绍内容不能为空")

        # 1. 解析课程介绍
        course_records = parse_course_intro(md_content, source_file=file_title)
        logger.info(f"课程介绍解析完成，共{len(course_records)}门课程")
        if not course_records:
            raise ValueError("课程介绍解析结果为空，请检查文件格式")

        # 2. 向量化 + 入库
        updated_records = self._vectorize_and_save(course_records, file_title)

        # 3. 注册知识实体（系列名 + 课程名）
        entities = []
        seen = set()
        for rec in course_records:
            for name in (rec.get("series_name"), rec.get("course_name")):
                if name and (name, ENTITY_TYPE_COURSE) not in seen:
                    seen.add((name, ENTITY_TYPE_COURSE))
                    entities.append({
                        "name": name,
                        "type": ENTITY_TYPE_COURSE,
                        "source_file": file_title,
                    })

        return {
            "course_records": updated_records,
            "entities": entities,
            "content_type": CONTENT_TYPE_COURSE_INTRO,
        }

    def _vectorize_and_save(self, course_records: List[Dict], file_title: str) -> List[Dict]:
        collection_name = edu_collection_config.course_collection
        milvus_client = get_milvus_client()
        if not milvus_client.has_collection(collection_name):
            self._create_course_collection(collection_name, milvus_client)

        # 幂等清理：同来源文件的历史课程记录
        safe_file = escape_milvus_string(file_title)
        milvus_client.delete(
            collection_name=collection_name,
            filter=f'source_file=="{safe_file}"',
        )

        updated_records = []
        for i in range(0, len(course_records), self.BATCH_SIZE):
            batch = course_records[i:i + self.BATCH_SIZE]
            texts = [build_course_search_text(rec) for rec in batch]
            vectors = generate_embeddings(texts)

            data = []
            for j, rec in enumerate(batch):
                row = {
                    "course_code": rec.get("course_code", ""),
                    "course_name": rec.get("course_name", ""),
                    "series_name": rec.get("series_name", ""),
                    "series_code": rec.get("series_code", ""),
                    "category": rec.get("category", ""),
                    "suitable_for": rec.get("suitable_for", ""),
                    "goals": rec.get("goals", ""),
                    "grade": rec.get("grade", ""),
                    "class_hours": rec.get("class_hours", ""),
                    "period": rec.get("period", ""),
                    "description": rec.get("description", ""),
                    "series_description": rec.get("series_description", ""),
                    "source_file": file_title,
                    "search_text": texts[j],
                    "dense_vector": vectors["dense"][j],
                    "sparse_vector": vectors["sparse"][j],
                }
                data.append(row)
            result = milvus_client.insert(collection_name=collection_name, data=data)
            inserted_ids = result.get("ids", [])
            for j, rec in enumerate(batch):
                rec["course_id"] = inserted_ids[j] if j < len(inserted_ids) else None
                updated_records.append(rec)

        logger.info(f"课程记录入库完成，共{len(updated_records)}条 -> {collection_name}")
        return updated_records

    def _create_course_collection(self, collection_name, milvus_client):
        schema = milvus_client.create_schema(auto_id=True, enable_dynamic_field=True)
        schema.add_field(field_name="course_id", datatype=DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field(field_name="course_code", datatype=DataType.VARCHAR, max_length=255)
        schema.add_field(field_name="course_name", datatype=DataType.VARCHAR, max_length=255)
        schema.add_field(field_name="series_name", datatype=DataType.VARCHAR, max_length=255)
        schema.add_field(field_name="series_code", datatype=DataType.VARCHAR, max_length=255)
        schema.add_field(field_name="category", datatype=DataType.VARCHAR, max_length=500)
        schema.add_field(field_name="suitable_for", datatype=DataType.VARCHAR, max_length=500)
        schema.add_field(field_name="goals", datatype=DataType.VARCHAR, max_length=500)
        schema.add_field(field_name="grade", datatype=DataType.VARCHAR, max_length=500)
        schema.add_field(field_name="class_hours", datatype=DataType.VARCHAR, max_length=50)
        schema.add_field(field_name="period", datatype=DataType.VARCHAR, max_length=50)
        schema.add_field(field_name="description", datatype=DataType.VARCHAR, max_length=2000)
        schema.add_field(field_name="series_description", datatype=DataType.VARCHAR, max_length=2000)
        schema.add_field(field_name="source_file", datatype=DataType.VARCHAR, max_length=255)
        schema.add_field(field_name="search_text", datatype=DataType.VARCHAR, max_length=16384)
        schema.add_field(field_name="sparse_vector", datatype=DataType.SPARSE_FLOAT_VECTOR)
        schema.add_field(field_name="dense_vector", datatype=DataType.FLOAT_VECTOR, dim=1024)

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
        logger.info(f"课程集合创建成功：{collection_name}")
