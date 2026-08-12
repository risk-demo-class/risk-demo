"""
Agent 对话处理:
  - 配置了 LLM_API_KEY → 走 LLM 大模型 (带会话记忆 + 系统风控数据上下文)
  - 未配置 / LLM 调用失败 → 自动降级为本地规则式问答, 保证功能可用
"""
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import chat_completion, llm_configured
from app.agent.tools import (
    count_enabled_rules,
    explain_features,
    list_rules_summary,
    risk_distribution,
    search_rules,
)

logger = logging.getLogger(__name__)

# 会话记忆 (进程内存, 每个 session_id 最多保留 5 轮)
_SESSIONS: dict[str, list[dict]] = {}
_MAX_HISTORY = 10


async def handle_chat(db: AsyncSession, message: str, session_id: str = "default") -> dict:
    """统一对话入口: LLM 优先, 降级规则问答兜底."""
    msg = (message or "").strip()
    if not msg:
        return {"reply": "请描述你的问题, 例如: 有哪些风险规则? / 搜索退改规则 / 查看决策分布", "session_id": session_id, "mode": "rule"}

    if llm_configured():
        try:
            return await _handle_with_llm(db, msg, session_id)
        except Exception as e:
            logger.exception("LLM 调用失败, 降级本地规则问答: %s", e)
            reply = await _rule_reply(db, msg)
            return {
                "reply": f"（LLM 暂时不可用，已切换本地规则问答）\n\n{reply}",
                "session_id": session_id,
                "mode": "rule",
            }

    return {"reply": await _rule_reply(db, msg), "session_id": session_id, "mode": "rule"}


async def _handle_with_llm(db: AsyncSession, msg: str, session_id: str) -> dict:
    """LLM 路径: 系统提示词注入实时风控数据 + 会话记忆."""
    history = _SESSIONS.setdefault(session_id, [])
    context = await _build_system_context(db)
    system = (
        "你是旅游平台的风控专家助手。回答用户关于风控规则、风险画像、决策结果、"
        "业务数据的问题。必须严格遵守:\n"
        "1. 直接回答用户的问题, 不要反问、不要寒暄客套;\n"
        "2. 优先引用【系统实时风控数据】里的真实数据作答, 例如规则场景分布要逐条列出;\n"
        "3. 数据里没有的信息, 明确说明系统里没有该数据;\n"
        "4. 简洁、准确、用中文。\n"
        f"【系统实时风控数据】\n{context}"
    )
    messages = [{"role": "system", "content": system}]
    messages.extend(history)
    messages.append({"role": "user", "content": msg})

    reply = await chat_completion(messages)

    history.append({"role": "user", "content": msg})
    history.append({"role": "assistant", "content": reply})
    if len(history) > _MAX_HISTORY:
        del history[: len(history) - _MAX_HISTORY]
    return {"reply": reply, "session_id": session_id, "mode": "llm"}


async def _build_system_context(db: AsyncSession) -> str:
    """把规则清单 + 决策分布 + 特征清单注入系统提示词, 让 LLM 的回答贴合系统真实数据."""
    try:
        rule_list = await list_rules_summary(db)
        dist = await risk_distribution(db)
        rule_lines = "\n".join(
            f"- {r['rule_id']} {r['rule_name']} [{r['rule_category']}/{r['risk_level']}/{r['risk_score']}分 → {r['action']}]: {r['description'] or ''}"
            for r in rule_list
        )
        feature_text = await explain_features()
        return (
            "【规则清单】(共 " + str(len(rule_list)) + " 条, 按优先级排列)\n"
            + rule_lines
            + "\n【决策分布】" + json.dumps(dist, ensure_ascii=False)
            + "\n【特征清单】" + feature_text
        )
    except Exception:
        logger.exception("构建 LLM 上下文失败")
        return "（暂无实时数据）"


async def _rule_reply(db: AsyncSession, msg: str) -> str:
    """本地规则式问答 (LLM 未配置/失败时的兜底)."""
    if any(k in msg for k in ("搜索", "查一下", "找规则")):
        keyword = msg
        for k in ("请帮我", "帮我", "搜索", "查一下", "找一下", "找规则", "规则"):
            keyword = keyword.replace(k, "")
        keyword = keyword.strip() or "退改"
        rules = await search_rules(db, keyword)
        if not rules:
            return f"未找到与「{keyword}」相关的规则"
        lines = [f"找到 {len(rules)} 条相关规则:"]
        for r in rules:
            lines.append(
                f"- {r['rule_id']} {r['rule_name']} [{r['risk_level']}/{r['risk_score']}分 → {r['action']}]: {r['description']}"
            )
        return "\n".join(lines)

    if any(k in msg for k in ("规则", "场景", "多少条")):
        return _fmt(await count_enabled_rules(db))

    if any(k in msg for k in ("分布", "决策", "评估")):
        return _fmt(await risk_distribution(db))

    if any(k in msg for k in ("特征", "维度", "feature")):
        return await explain_features()

    return (
        "我是旅游风控助手。我可以帮你: 查看规则场景分布、搜索具体规则、"
        "查看评估决策分布、列出 28 维特征。\n"
        "示例: 「有哪些风险规则」「搜索退改规则」「查看决策分布」「列出特征」"
    )


def _fmt(data: dict) -> str:
    """dict → 可读文本"""
    lines = []
    for k, v in data.items():
        if isinstance(v, dict):
            lines.append(f"{k}:")
            for kk, vv in v.items():
                lines.append(f"  - {kk}: {vv}")
        else:
            lines.append(f"{k}: {v}")
    return "\n".join(lines)
