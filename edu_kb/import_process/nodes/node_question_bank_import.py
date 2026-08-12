# -*- coding: utf-8 -*-
from typing import List, Dict

from pymilvus import DataType

from edu_kb.config.config import edu_collection_config
from edu_kb.config.constants import (
    CONTENT_TYPE_QUESTION,
    ENTITY_TYPE_QUESTION_BANK,
)
from edu_kb.import_process.base import NodeBase
from edu_kb.import_process.state import ImportGraphState
from edu_kb.tool.logger import logger
from edu_kb.utils.embedding_utils import generate_embeddings
from edu_kb.utils.milvus_utils import get_milvus_client, escape_milvus_string
from edu_kb.utils.question_bank_parser import (
    parse_question_bank,
    build_question_search_text,
)


class NodeQuestionBankImport(NodeBase):
    """
    题库入库节点：
      1. 解析题库 Markdown -> 题目记录（含题型/选项/答案/解析）
      2. 向量化题干 + 选项 + 题库名
      3. 写入 Milvus 的 edu_questions 集合
      4. 注册题库名知识实体
    """

    name = "node_question_bank_import"

    BATCH_SIZE = 20

    def process(self, state: ImportGraphState):
        md_content = state.get("md_content")
        file_title = state.get("file_title")
        if not md_content:
            raise ValueError("题库内容不能为空")

        question_records = parse_question_bank(md_content, source_file=file_title)
        logger.info(f"题库解析完成，共{len(question_records)}道题")
        if not question_records:
            raise ValueError("题库解析结果为空，请检查文件格式")

        updated_records = self._vectorize_and_save(question_records, file_title)

        # 注册题库名实体
        entities = []
        seen = set()
        for rec in question_records:
            bank_name = rec.get("bank_name", "")
            if bank_name and (bank_name, ENTITY_TYPE_QUESTION_BANK) not in seen:
                seen.add((bank_name, ENTITY_TYPE_QUESTION_BANK))
                entities.append({
                    "name": bank_name,
                    "type": ENTITY_TYPE_QUESTION_BANK,
                    "source_file": file_title,
                })

        return {
            "question_records": updated_records,
            "entities": entities,
            "question_bank_name": question_records[0].get("bank_name", ""),
            "content_type": CONTENT_TYPE_QUESTION,
        }

    def _vectorize_and_save(self, question_records: List[Dict], file_title: str) -> List[Dict]:
        collection_name = edu_collection_config.question_collection
        milvus_client = get_milvus_client()
        if not milvus_client.has_collection(collection_name):
            self._create_question_collection(collection_name, milvus_client)

        safe_file = escape_milvus_string(file_title)
        milvus_client.delete(
            collection_name=collection_name,
            filter=f'source_file=="{safe_file}"',
        )

        updated_records = []
        for i in range(0, len(question_records), self.BATCH_SIZE):
            batch = question_records[i:i + self.BATCH_SIZE]
            texts = [build_question_search_text(rec) for rec in batch]
            vectors = generate_embeddings(texts)

            data = []
            for j, rec in enumerate(batch):
                row = {
                    "question_code": rec.get("question_code", ""),
                    "bank_name": rec.get("bank_name", ""),
                    "bank_code": rec.get("bank_code", ""),
                    "question_type": rec.get("question_type", ""),
                    "question_text": rec.get("question_text", ""),
                    "options": "\n".join(rec.get("options", [])),
                    "answer": rec.get("answer", ""),
                    "analysis": rec.get("analysis", ""),
                    "source_file": file_title,
                    "search_text": texts[j],
                    "dense_vector": vectors["dense"][j],
                    "sparse_vector": vectors["sparse"][j],
                }
                data.append(row)
            result = milvus_client.insert(collection_name=collection_name, data=data)
            inserted_ids = result.get("ids", [])
            for j, rec in enumerate(batch):
                rec["question_id"] = inserted_ids[j] if j < len(inserted_ids) else None
                updated_records.append(rec)

        logger.info(f"题目入库完成，共{len(updated_records)}条 -> {collection_name}")
        return updated_records

    def _create_question_collection(self, collection_name, milvus_client):
        schema = milvus_client.create_schema(auto_id=True, enable_dynamic_field=True)
        schema.add_field(field_name="question_id", datatype=DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field(field_name="question_code", datatype=DataType.VARCHAR, max_length=255)
        schema.add_field(field_name="bank_name", datatype=DataType.VARCHAR, max_length=255)
        schema.add_field(field_name="bank_code", datatype=DataType.VARCHAR, max_length=255)
        schema.add_field(field_name="question_type", datatype=DataType.VARCHAR, max_length=50)
        schema.add_field(field_name="question_text", datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(field_name="options", datatype=DataType.VARCHAR, max_length=16384)
        schema.add_field(field_name="answer", datatype=DataType.VARCHAR, max_length=8192)
        schema.add_field(field_name="analysis", datatype=DataType.VARCHAR, max_length=16384)
        schema.add_field(field_name="source_file", datatype=DataType.VARCHAR, max_length=255)
        schema.add_field(field_name="search_text", datatype=DataType.VARCHAR, max_length=65535)
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
        logger.info(f"题库集合创建成功：{collection_name}")
