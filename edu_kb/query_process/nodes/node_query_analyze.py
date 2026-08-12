# -*- coding: utf-8 -*-
import json
from typing import Tuple, Dict, List

from langchain_core.messages import SystemMessage, HumanMessage

from edu_kb.config.config import lm_config, edu_collection_config
from edu_kb.config.constants import (
    INTENT_COURSE_INTRO,
    INTENT_COURSE_DETAIL,
    INTENT_DOC_RETRIEVAL,
    INTENT_QUESTION,
    INTENT_QA,
    ENTITY_CONFIRM_SCORE,
    ENTITY_CANDIDATE_SCORE,
)
from edu_kb.query_process.base import NodeBase
from edu_kb.query_process.prompt import (
    QUERY_ANALYZE_SYSTEM_PROMPT,
    QUERY_ANALYZE_TEMPLATE,
)
from edu_kb.query_process.state import QueryGraphState
from edu_kb.tool.logger import logger
from edu_kb.utils.embedding_utils import generate_query_embeddings
from edu_kb.utils.llm_utils import get_llm_client
from edu_kb.utils.milvus_utils import (
    create_hybrid_search_request,
    escape_milvus_string,
    hybrid_search,
    query_collection,
)
from edu_kb.utils.mongo_history_utils import (
    save_chat_message,
    format_json,
    get_recent_messages,
    update_message_entities,
)


class NodeQueryAnalyze(NodeBase):
    """
    节点功能：问题分析与意图识别
      1. 校验 session_id / original_query
      2. 读取历史记录并保存用户消息
      3. 调用 LLM 提取意图 + 知识实体 + 问题改写（JSON）
      4. 通过 edu_entities 集合对齐确认课程/项目/题库实体
      5. 需要澄清时生成 answer，直接结束
      6. 写入历史
    """

    name = "node_query_analyze"

    def process(self, state: QueryGraphState):
        # 1. 参数校验
        session_id, original_query = self._step1_validate_param(state)

        # 2. 获取聊天历史
        history = get_recent_messages(session_id)

        # 3. 保存用户当前问题
        message_id = save_chat_message(session_id, "user", original_query)

        # 4. LLM 提取意图 + 实体 + 改写
        analyze_result = self._step2_analyze(original_query, history)
        intent = analyze_result.get("intent", INTENT_QA)
        rewritten_query = analyze_result.get("rewritten_query") or original_query

        # 5. 实体对齐（课程 / 项目 / 题库）
        aligned = self._step3_align_entities(analyze_result)

        # 6. 澄清 / 结束判断
        answer = ""
        if intent == INTENT_COURSE_INTRO and not aligned["course_names"]:
            if aligned["course_candidates"]:
                option_str = "、".join(aligned["course_candidates"][:5])
                answer = f"您是想查询以下哪个课程：{option_str}？请明确课程名称。"
            else:
                # 无明确课程时仍走课程检索，让检索节点兜底
                logger.info("未确认到具体课程，继续执行课程检索")

        # 7. 写入历史
        self._step4_write_history(
            dict_result={"answer": answer, "entities": aligned["all_entities"]},
            session_id=session_id,
            original_query=original_query,
            rewritten_query=rewritten_query,
            intent=intent,
            message_id=message_id,
        )

        return {
            "history": get_recent_messages(session_id),
            "intent": intent,
            "rewritten_query": rewritten_query,
            "course_names": aligned["course_names"],
            "project_names": aligned["project_names"],
            "bank_names": aligned["bank_names"],
            "knowledge_points": analyze_result.get("knowledge_points", []),
            "answer": answer,
        }

    def _step1_validate_param(self, state: QueryGraphState) -> Tuple[str, str]:
        session_id = state.get("session_id")
        if not session_id:
            raise ValueError("核心参数session_id缺失")
        original_query = state.get("original_query")
        if not original_query:
            raise ValueError("核心参数original_query缺失")
        return session_id, original_query

    def _step2_analyze(self, original_query, history) -> Dict:
        """调用 LLM 分析意图；失败时使用关键词规则兜底"""
        try:
            history_text = ""
            for msg in reversed(history):
                role = msg.get("role")
                text = msg.get("text")
                if role and text:
                    history_text += f"{role}: {text}\n"

            user_prompt = QUERY_ANALYZE_TEMPLATE.format(
                history_text=history_text or "暂无历史对话",
                original_query=original_query,
            )
            messages = [
                SystemMessage(content=QUERY_ANALYZE_SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ]
            llm_client = get_llm_client(model=lm_config.item_model, json_mode=True)
            response = llm_client.invoke(messages)
            content = response.content.strip()
            if content.startswith("```json"):
                content = content.replace("```json", "").replace("```", "")
            result = json.loads(content)

            return {
                "intent": str(result.get("intent", INTENT_QA)),
                "course_names": [str(c).strip() for c in result.get("course_names", []) if c],
                "project_names": [str(p).strip() for p in result.get("project_names", []) if p],
                "bank_names": [str(b).strip() for b in result.get("bank_names", []) if b],
                "knowledge_points": [str(k).strip() for k in result.get("knowledge_points", []) if k],
                "rewritten_query": str(result.get("rewritten_query", "")).strip() or original_query,
            }
        except Exception as e:
            logger.exception(f"意图分析失败：{e}")
            return self._heuristic_analyze(original_query)

    def _heuristic_analyze(self, query: str) -> Dict:
        """关键词规则兜底"""
        intent = INTENT_QA
        if any(k in query for k in ("课程", "推荐", "有哪些", "适合", "介绍", "学习目标")):
            intent = INTENT_COURSE_INTRO
        elif any(k in query for k in ("详情", "章节", "先修", "大纲", "目录")):
            intent = INTENT_COURSE_DETAIL
        elif any(k in query for k in ("题", "练习", "题库", "选择", "判断", "简答", "编程题")):
            intent = INTENT_QUESTION
        elif "项目" in query:
            intent = INTENT_DOC_RETRIEVAL
        return {
            "intent": intent,
            "course_names": [],
            "project_names": [],
            "bank_names": [],
            "knowledge_points": [],
            "rewritten_query": query,
        }

    def _step3_align_entities(self, analyze_result: Dict) -> Dict:
        """在 edu_entities 集合中对齐课程/项目/题库实体"""
        confirmed = {
            "course": [],
            "project": [],
            "question_bank": [],
        }
        candidates = {
            "course": [],
            "project": [],
            "question_bank": [],
        }

        groups = [
            ("course", analyze_result.get("course_names", [])),
            ("project", analyze_result.get("project_names", [])),
            ("question_bank", analyze_result.get("bank_names", [])),
        ]

        try:
            for entity_type, names in groups:
                for name in names:
                    if not name:
                        continue
                    # 优先精确匹配知识库中的实体名（避免向量相似度阈值导致反问）
                    if self._exact_entity_exists(name):
                        confirmed[entity_type].append(name)
                        continue
                    matches = self._search_entity(name)
                    high = [m for m in matches if m.get("score", 0) > ENTITY_CONFIRM_SCORE]
                    mid = [m for m in matches if m.get("score", 0) >= ENTITY_CANDIDATE_SCORE]
                    if high:
                        confirmed[entity_type].append(name)
                    elif mid:
                        candidates[entity_type].append(name)
        except Exception as e:
            logger.warning(f"实体对齐失败（知识库可能尚未导入），继续检索：{e}")

        all_entities = (
            confirmed["course"] + confirmed["project"] + confirmed["question_bank"]
        )
        return {
            "course_names": list(set(confirmed["course"])),
            "project_names": list(set(confirmed["project"])),
            "bank_names": list(set(confirmed["question_bank"])),
            "course_candidates": list(set(candidates["course"])),
            "all_entities": all_entities,
        }

    def _exact_entity_exists(self, name: str) -> bool:
        """在 edu_entities 中按实体名精确匹配（大小写不敏感兜底）"""
        try:
            safe = escape_milvus_string(name)
            hits = query_collection(
                collection_name=edu_collection_config.entity_collection,
                filter_expr='entity_name=="' + safe + '"',
                limit=1,
                output_fields=["entity_name"],
            )
            if hits:
                return True
            hits2 = query_collection(
                collection_name=edu_collection_config.entity_collection,
                filter_expr='lower(entity_name)=="' + safe.lower() + '"',
                limit=1,
                output_fields=["entity_name"],
            )
            return bool(hits2)
        except Exception as e:
            logger.warning(f"实体精确匹配失败: {e}")
            return False

    def _search_entity(self, name: str) -> List[Dict]:
        """对单个实体名做混合向量检索，返回 (entity_name, score) 匹配列表"""
        embeddings = generate_query_embeddings([name])
        reqs = create_hybrid_search_request(
            dense_vector=embeddings["dense"][0],
            sparse_vector=embeddings["sparse"][0],
        )
        try:
            result = hybrid_search(
                collection_name=edu_collection_config.entity_collection,
                reqs=reqs,
                ranker_weights=(0.8, 0.2),
                norm_score=True,
                output_fields=["entity_name", "entity_type"],
                limit=3,
            )
        except Exception:
            return []
        hits = result[0] if result else []
        return [
            {"entity_name": hit.get("entity", {}).get("entity_name"), "score": hit.get("distance")}
            for hit in hits
        ]

    def _step4_write_history(
            self, dict_result, session_id, original_query,
            rewritten_query, intent, message_id,
    ):
        if dict_result.get("answer"):
            save_chat_message(
                session_id=session_id,
                role="assistant",
                text=dict_result.get("answer"),
                rewritten_query="",
                entities=[],
                intent=intent,
            )

        save_chat_message(
            session_id=session_id,
            role="user",
            text=original_query,
            rewritten_query=rewritten_query,
            entities=dict_result.get("entities", []),
            intent=intent,
            message_id=message_id,
        )


if __name__ == "__main__":
    init_state = {
        "session_id": "test_001",
        "original_query": "有哪些 Python 相关的课程？",
    }
    node = NodeQueryAnalyze()
    result = node(init_state)
    print(format_json(result))
