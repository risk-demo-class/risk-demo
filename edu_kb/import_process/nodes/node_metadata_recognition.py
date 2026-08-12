# -*- coding: utf-8 -*-
import json
from typing import Tuple, List, Dict

from langchain_core.messages import SystemMessage, HumanMessage

from edu_kb.config.config import lm_config
from edu_kb.config.constants import (
    CONTENT_TYPE_COURSE_DOC,
    CONTENT_TYPE_PROJECT_DOC,
    ENTITY_TYPE_COURSE,
    ENTITY_TYPE_PROJECT,
)
from edu_kb.import_process.base import NodeBase
from edu_kb.import_process.prompt import EDU_METADATA_RECOGNITION
from edu_kb.import_process.state import ImportGraphState
from edu_kb.tool.logger import logger
from edu_kb.utils.llm_utils import get_llm_client
from edu_kb.utils.text_utils import strip_filename_version


class NodeMetadataRecognition(NodeBase):
    """
    教育元数据识别节点：
      1. 调用 LLM 识别课程名 / 项目名 / 章节 / 知识点（JSON 输出）
      2. 识别失败时使用文件名规则兜底
      3. 回填元数据到每个 chunk
      4. 生成知识实体（课程名 / 项目名）
    """

    name = "node_metadata_recognition"

    DEFAULT_CHUNK_K = 3
    MAX_CHARS = 3000

    def process(self, state: ImportGraphState):
        # 1. 校验输入
        file_title, chunks, content_type = self._step1_get_inputs(state)

        # 2. 构建 LLM 上下文并识别元数据
        meta = self._step2_recognize_metadata(state, file_title, chunks, content_type)

        # 3. 文件名规则兜底
        meta = self._step3_fallback(file_title, content_type, meta)

        # 4. 回填元数据到切片
        chunks = self._step4_update_chunks(chunks, meta, content_type)

        # 5. 生成知识实体
        entities = self._step5_build_entities(state, meta, file_title)

        logger.info(f"教育元数据识别完成：{meta}")
        return {
            "chunks": chunks,
            "course_name": meta.get("course_name", ""),
            "project_name": meta.get("project_name", ""),
            "entities": entities,
        }

    def _step1_get_inputs(self, state: ImportGraphState) -> Tuple[str, List[Dict], str]:
        file_title = state.get("file_title")
        if not file_title:
            raise ValueError("文件标题不能为空")
        chunks = state.get("chunks")
        if not chunks:
            raise ValueError("文本切片不能为空")
        content_type = state.get("content_type") or CONTENT_TYPE_COURSE_DOC
        return file_title, chunks, content_type

    def _step2_recognize_metadata(self, state, file_title, chunks, content_type) -> Dict:
        context = self._build_context(chunks)
        content_type_cn = "课程文档" if content_type == CONTENT_TYPE_COURSE_DOC else "项目文档"
        try:
            prompt = EDU_METADATA_RECOGNITION.format(
                file_title=file_title,
                content_type_cn=content_type_cn,
                context=context,
            )
            llm = get_llm_client(model=lm_config.item_model, json_mode=True)
            messages = [
                SystemMessage(content="你是教育知识库元数据识别专家，只输出 JSON。"),
                HumanMessage(content=prompt),
            ]
            response = llm.invoke(messages)
            content = response.content.strip()
            if content.startswith("```json"):
                content = content.replace("```json", "").replace("```", "")
            result = json.loads(content)
            return {
                "course_name": str(result.get("course_name", "")).strip(),
                "project_name": str(result.get("project_name", "")).strip(),
                "chapter_names": [str(c).strip() for c in result.get("chapter_names", []) if c],
                "knowledge_points": [str(k).strip() for k in result.get("knowledge_points", []) if k],
            }
        except Exception as e:
            logger.exception(f"教育元数据识别失败：{e}")
            return {}

    def _build_context(self, chunks: List[Dict]) -> str:
        parts = []
        total_chars = 0
        for idx, chunk in enumerate(chunks[:self.DEFAULT_CHUNK_K], start=1):
            piece = f"【切片{idx}】\n标题：{chunk.get('title')}\n内容：{chunk.get('content')}"
            parts.append(piece)
            total_chars += len(piece)
            if total_chars > self.MAX_CHARS:
                break
        return "\n\n".join(parts).strip()[:self.MAX_CHARS]

    def _step3_fallback(self, file_title, content_type, meta) -> Dict:
        meta.setdefault("course_name", "")
        meta.setdefault("project_name", "")
        meta.setdefault("chapter_names", [])
        meta.setdefault("knowledge_points", [])

        if not meta["course_name"]:
            meta["course_name"] = strip_filename_version(file_title)

        if content_type == CONTENT_TYPE_PROJECT_DOC and not meta["project_name"]:
            meta["project_name"] = strip_filename_version(file_title)

        return meta

    def _step4_update_chunks(self, chunks, meta, content_type) -> List[Dict]:
        for chunk in chunks:
            chunk["course_name"] = meta.get("course_name", "")
            chunk["project_name"] = meta.get("project_name", "")
            chunk["chapter_name"] = chunk.get("parent_title") or chunk.get("title") or ""
            chunk["content_type"] = content_type
        return chunks

    def _step5_build_entities(self, state, meta, file_title) -> List[Dict]:
        entities = []
        seen = set()

        # 已有（入口节点根据文件名推导）的课程名优先保留
        for name in (state.get("course_name"), meta.get("course_name")):
            if name and (name, ENTITY_TYPE_COURSE) not in seen:
                seen.add((name, ENTITY_TYPE_COURSE))
                entities.append({
                    "name": name,
                    "type": ENTITY_TYPE_COURSE,
                    "source_file": file_title,
                })

        for name in (state.get("project_name"), meta.get("project_name")):
            if name and (name, ENTITY_TYPE_PROJECT) not in seen:
                seen.add((name, ENTITY_TYPE_PROJECT))
                entities.append({
                    "name": name,
                    "type": ENTITY_TYPE_PROJECT,
                    "source_file": file_title,
                })

        return entities
