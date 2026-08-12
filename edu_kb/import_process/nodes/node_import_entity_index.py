# -*- coding: utf-8 -*-
from typing import List, Dict

from pymilvus import DataType

from edu_kb.config.config import edu_collection_config
from edu_kb.import_process.base import NodeBase
from edu_kb.import_process.state import ImportGraphState
from edu_kb.tool.logger import logger
from edu_kb.utils.embedding_utils import generate_embeddings
from edu_kb.utils.milvus_utils import get_milvus_client, escape_milvus_string
from edu_kb.utils.text_utils import dedupe_preserve_order


class NodeImportEntityIndex(NodeBase):
    """
    知识实体索引节点：
      将导入过程中识别出的课程名 / 项目名 / 题库名写入 edu_entities 集合，
      用于查询侧实体对齐（确认用户提到的课程 / 项目 / 题库）。
    """

    name = "node_import_entity_index"

    BATCH_SIZE = 50

    def process(self, state: ImportGraphState):
        entities = state.get("entities") or []
        if not entities:
            logger.info("无知识实体需要索引，跳过实体索引节点")
            return {"entities": entities}

        # 1. 归一化去重（name + type）
        seen = set()
        unique_entities = []
        for ent in entities:
            key = (str(ent.get("name", "")).strip(), str(ent.get("type", "")).strip())
            if key[0] and key not in seen:
                seen.add(key)
                unique_entities.append({
                    "name": key[0],
                    "type": key[1],
                    "source_file": str(ent.get("source_file", "")),
                })

        if not unique_entities:
            return {"entities": entities}

        # 2. 向量化 + 入库
        collection_name = edu_collection_config.entity_collection
        milvus_client = get_milvus_client()
        if not milvus_client.has_collection(collection_name):
            self._create_entity_collection(collection_name, milvus_client)

        # 幂等清理：按来源文件清理该文件注册的实体
        source_files = dedupe_preserve_order(
            [str(e.get("source_file", "")) for e in unique_entities if e.get("source_file")]
        )
        for sf in source_files:
            safe_sf = escape_milvus_string(sf)
            milvus_client.delete(
                collection_name=collection_name,
                filter=f'source_file=="{safe_sf}"',
            )

        for i in range(0, len(unique_entities), self.BATCH_SIZE):
            batch = unique_entities[i:i + self.BATCH_SIZE]
            names = [f"{e['name']} {e['type']}" for e in batch]
            vectors = generate_embeddings(names)
            data = []
            for j, ent in enumerate(batch):
                data.append({
                    "entity_name": ent["name"],
                    "entity_type": ent["type"],
                    "source_file": ent["source_file"],
                    "dense_vector": vectors["dense"][j],
                    "sparse_vector": vectors["sparse"][j],
                })
            milvus_client.insert(collection_name=collection_name, data=data)

        logger.info(f"知识实体索引完成，共{len(unique_entities)}条 -> {collection_name}")
        return {"entities": unique_entities}

    def _create_entity_collection(self, collection_name, milvus_client):
        schema = milvus_client.create_schema(auto_id=True, enable_dynamic_field=True)
        schema.add_field(field_name="pk", datatype=DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field(field_name="entity_name", datatype=DataType.VARCHAR, max_length=255)
        schema.add_field(field_name="entity_type", datatype=DataType.VARCHAR, max_length=50)
        schema.add_field(field_name="source_file", datatype=DataType.VARCHAR, max_length=255)
        schema.add_field(field_name="dense_vector", datatype=DataType.FLOAT_VECTOR, dim=1024)
        schema.add_field(field_name="sparse_vector", datatype=DataType.SPARSE_FLOAT_VECTOR)

        index_params = milvus_client.prepare_index_params()
        index_params.add_index(
            field_name="dense_vector",
            index_name="dense_vector_index",
            index_type="IVF_FLAT",
            metric_type="COSINE",
            params={"nlist": 128},
        )
        index_params.add_index(
            field_name="sparse_vector",
            index_name="sparse_vector_index",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="IP",
            params={
                "inverted_index_algo": "DAAT_MAXSCORE",
                "normalize": True,
                "quantization": "none",
            },
        )
        milvus_client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params,
        )
        logger.info(f"知识实体集合创建成功：{collection_name}")
