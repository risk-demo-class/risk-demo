# -*- coding: utf-8 -*-
import re
from typing import List, Dict, Tuple

from edu_kb.config.constants import (
    INTENT_COURSE_DETAIL,
    INTENT_COURSE_INTRO,
    INTENT_QUESTION,
)
from edu_kb.query_process.base import NodeBase
from edu_kb.query_process.prompt import ANSWER_PROMPT
from edu_kb.query_process.state import QueryGraphState
from edu_kb.tool.logger import logger
from edu_kb.utils.llm_utils import get_llm_client
from edu_kb.utils.mongo_history_utils import save_chat_message
from edu_kb.utils.sse_utils_sync import push_sse_event, SSEEvent


class NodeAnswerOutput(NodeBase):
    """
    节点功能：答案生成
      1. 存在澄清 answer 时直接推送
      2. 按意图组装参考内容（课程 / 题目 / 文档片段）
      3. 流式调用 LLM 生成答案
      4. 提取引用信息与图片，写入历史，推送 final 事件
    """

    name = "node_answer_output"

    MAX_CONTEXT_CHARS = 12000

    def process(self, state: QueryGraphState):
        task_id = state.get("task_id")
        answer = state.get("answer")

        if answer:
            push_sse_event(task_id, SSEEvent.FINAL, {"answer": answer, "references": []})
            self._write_history(state, answer, [])
            return state

        prompt = self._step1_construct_prompt(state)
        state["prompt"] = prompt

        answer = self._step2_generate_response(state, prompt)
        state["answer"] = answer

        references = self._step3_build_references(state)
        image_urls = self._step4_extract_images_from_docs(state.get("reranked_docs") or [])

        if answer:
            self._write_history(state, answer, references, image_urls=image_urls)

        push_sse_event(task_id, SSEEvent.FINAL, {
            "answer": answer,
            "references": references,
            "image_urls": image_urls,
        })
        return state

    def _step1_construct_prompt(self, state: QueryGraphState) -> str:
        char_budget = self.MAX_CONTEXT_CHARS
        intent = state.get("intent")

        question = state.get("rewritten_query") or state.get("original_query")
        context_str, char_budget = self._format_context(state, intent, char_budget)
        history_str, char_budget = self._format_chat_history(
            state.get("history") or [], char_budget
        )

        courses = "、".join(state.get("course_names") or []) or "无"
        projects = "、".join(state.get("project_names") or []) or "无"
        banks = "、".join(state.get("bank_names") or []) or "无"

        prompt = ANSWER_PROMPT.format(
            context=context_str or "无参考内容",
            history=history_str if history_str else "暂无历史对话",
            courses=courses,
            projects=projects,
            banks=banks,
            question=question,
        )
        return prompt

    def _format_context(self, state, intent, char_budget: int) -> Tuple[str, int]:
        """按意图选择并格式化参考内容"""
        formatted_lines = []
        used_chars = 0

        if intent in (INTENT_COURSE_INTRO, INTENT_COURSE_DETAIL):
            course_results = state.get("course_results") or []
            for idx, hit in enumerate(course_results[:10], start=1):
                entity = hit.get("entity") if isinstance(hit, dict) and "entity" in hit else hit
                text = self._format_course_record(entity)
                entry = f"[{idx}] {text}"
                if used_chars + len(entry) > char_budget:
                    break
                formatted_lines.append(entry)
                used_chars += len(entry) + 2

        elif intent == INTENT_QUESTION:
            question_results = state.get("question_results") or []
            for idx, hit in enumerate(question_results[:10], start=1):
                entity = hit.get("entity") if isinstance(hit, dict) and "entity" in hit else hit
                text = self._format_question_record(entity)
                entry = f"[{idx}] {text}"
                if used_chars + len(entry) > char_budget:
                    break
                formatted_lines.append(entry)
                used_chars += len(entry) + 2

        else:
            reranked_docs = state.get("reranked_docs") or []
            for idx, doc in enumerate(reranked_docs, start=1):
                content = doc.get("content")
                if not content:
                    continue
                meta_tags = [f"[{idx}]"]
                for field, template in [
                    ("course_name", "[课程={}]"),
                    ("project_name", "[项目={}]"),
                    ("chapter_name", "[章节={}]"),
                    ("file_title", "[文件={}]"),
                    ("url", "[链接={}]"),
                    ("score", "[相关度={:.4f}]"),
                ]:
                    field_value = doc.get(field)
                    if field_value is None or field_value == "":
                        continue
                    if field == "score":
                        meta_tags.append(template.format(float(field_value)))
                    else:
                        meta_tags.append(template.format(field_value))
                doc_entry = " ".join(meta_tags) + "\n" + content
                if used_chars + len(doc_entry) > char_budget:
                    break
                formatted_lines.append(doc_entry)
                used_chars += len(doc_entry) + 2

        return "\n\n".join(formatted_lines), char_budget - used_chars

    def _format_course_record(self, entity: Dict) -> str:
        return (
            f"课程名：{entity.get('course_name', '')}；所属系列：{entity.get('series_name', '')}；"
            f"编码：{entity.get('course_code', '')}；课时：{entity.get('class_hours', '')}；"
            f"学时：{entity.get('period', '')}；课程定位：{entity.get('description', '')}；"
            f"系列描述：{entity.get('series_description', '')}；适合人群：{entity.get('suitable_for', '')}；"
            f"学习目标：{entity.get('goals', '')}；适合年级：{entity.get('grade', '')}"
        )

    def _format_question_record(self, entity: Dict) -> str:
        options = entity.get("options") or ""
        return (
            f"题库：{entity.get('bank_name', '')}；题目编码：{entity.get('question_code', '')}；"
            f"题型：{entity.get('question_type', '')}；\n题干：{entity.get('question_text', '')}\n"
            f"选项：\n{options}\n答案：{entity.get('answer', '')}\n解析：{entity.get('analysis', '')}"
        )

    def _format_chat_history(self, chat_history: List[Dict], char_budget: int) -> Tuple[str, int]:
        formatted_lines = []
        used_chars = 0
        role_label_map = {"user": "用户", "assistant": "助手"}

        for message in chat_history:
            role = message.get("role", "")
            text = message.get("text", "")
            if not text or role not in role_label_map:
                continue
            formatted_line = f"{role_label_map[role]}: {text}"
            used_chars += len(formatted_line) + 1
            if used_chars > char_budget:
                return "\n".join(formatted_lines), char_budget - used_chars
            formatted_lines.append(formatted_line)
        return "\n".join(formatted_lines), char_budget - used_chars

    def _step2_generate_response(self, state: QueryGraphState, prompt: str) -> str:
        llm = get_llm_client()
        task_id = state.get("task_id")
        final_text = ""
        try:
            for chunk in llm.stream(prompt):
                delta = chunk.content
                if delta:
                    push_sse_event(task_id, SSEEvent.DELTA, {"delta": delta})
                    final_text += delta
        except Exception as e:
            push_sse_event(task_id, SSEEvent.ERROR, {"error": str(e)})
            logger.error(f"流式生成出错: {e}", exc_info=True)
        return final_text

    def _step3_build_references(self, state: QueryGraphState) -> List[Dict]:
        """构建结构化引用信息（课程/项目/章节/文件/题库/题目编码）"""
        references = []
        intent = state.get("intent")

        if intent == INTENT_QUESTION:
            for hit in state.get("question_results") or []:
                entity = hit.get("entity") if isinstance(hit, dict) and "entity" in hit else hit
                references.append({
                    "type": "question",
                    "bank_name": entity.get("bank_name", ""),
                    "question_code": entity.get("question_code", ""),
                    "question_type": entity.get("question_type", ""),
                    "file_title": entity.get("source_file", ""),
                    "score": round(float(hit.get("distance", 0)), 4) if isinstance(hit, dict) else 0,
                    "content": entity.get("question_text", ""),
                })
        elif intent in (INTENT_COURSE_INTRO, INTENT_COURSE_DETAIL):
            for hit in state.get("course_results") or []:
                entity = hit.get("entity") if isinstance(hit, dict) and "entity" in hit else hit
                references.append({
                    "type": "course",
                    "course_name": entity.get("course_name", ""),
                    "series_name": entity.get("series_name", ""),
                    "file_title": entity.get("source_file", ""),
                    "score": round(float(hit.get("distance", 0)), 4) if isinstance(hit, dict) else 0,
                    "content": entity.get("description", ""),
                })
        else:
            for doc in state.get("reranked_docs") or []:
                references.append({
                    "type": "doc",
                    "course_name": doc.get("course_name", ""),
                    "project_name": doc.get("project_name", ""),
                    "chapter_name": doc.get("chapter_name", ""),
                    "file_title": doc.get("file_title", ""),
                    "url": doc.get("url", ""),
                    "score": round(float(doc.get("score", 0)), 4),
                    "content": (doc.get("content") or "")[:200],
                })
        return references

    def _step4_extract_images_from_docs(self, docs):
        images = []
        seen = set()
        md_img_pattern = re.compile(r"!\[.*?\]\((.*?)\)")
        for doc in docs:
            text = doc.get("content") or ""
            for img_url in md_img_pattern.findall(text):
                img_url = img_url.strip()
                if img_url and img_url not in seen:
                    seen.add(img_url)
                    images.append(img_url)
        return images

    def _write_history(self, state, answer, references, image_urls=None):
        session_id = state.get("session_id")
        try:
            if answer:
                save_chat_message(
                    session_id=session_id,
                    role="assistant",
                    text=answer,
                    rewritten_query="",
                    entities=(
                        state.get("course_names") or []
                    ) + (
                        state.get("project_names") or []
                    ) + (
                        state.get("bank_names") or []
                    ),
                    references=references,
                    image_urls=image_urls or [],
                    intent=state.get("intent", ""),
                )
        except Exception as e:
            logger.error(f"写入Mongo历史记录失败: {e}")
