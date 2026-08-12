"""
DeepSeek 本地接口 - 订单备注语义分析.

识别黄牛暗号 / 违规拼团, 失败时兜底返回 0 分, 不阻断主链路.
"""

import json
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_RESULT = {
    "risk_level": "low",
    "risk_type": "normal",
    "score": 0,
    "reason": "LLM 不可用或未启用",
}

SYSTEM_PROMPT = (
    "你是旅游平台风控助手。只分析订单备注, 判断是否存在黄牛暗号或违规拼团风险。"
    "只输出 JSON, 格式: {\"risk_level\":\"low|medium|high\","
    "\"risk_type\":\"normal|scalper_code|illegal_group_buy\","
    "\"score\":0-100,\"reason\":\"简短原因\"}"
)


def _extract_json(content: str) -> dict[str, Any]:
    """从模型输出中提取 JSON, 兼容 markdown 代码块."""
    try:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            return json.loads(content[start : end + 1])
    except Exception:
        logger.exception("LLM 输出 JSON 解析失败")
    return dict(DEFAULT_RESULT)


def _normalize_result(raw: dict[str, Any]) -> dict[str, Any]:
    """校验并归一化 LLM 返回."""
    try:
        score = int(raw.get("score", 0))
        score = max(0, min(100, score))
        risk_type = raw.get("risk_type", "normal")
        if risk_type not in ("normal", "scalper_code", "illegal_group_buy"):
            risk_type = "normal"
        return {
            "risk_level": raw.get("risk_level", "low"),
            "risk_type": risk_type,
            "score": score,
            "reason": raw.get("reason", ""),
        }
    except Exception:
        logger.exception("LLM 结果归一化失败")
        return dict(DEFAULT_RESULT)


async def analyze_order_remark(remark: str) -> dict[str, Any]:
    """分析订单备注, 返回风险 JSON."""
    if not remark or not remark.strip():
        return dict(DEFAULT_RESULT)
    if not settings.LLM_ENABLED:
        logger.info("LLM_ENABLED=False, 跳过备注分析")
        return dict(DEFAULT_RESULT)

    url = settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.LLM_MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"订单备注: {remark}"},
        ],
        "temperature": settings.LLM_TEMPERATURE,
        "max_tokens": settings.LLM_MAX_TOKENS,
    }
    headers = {"Authorization": f"Bearer {settings.LLM_API_KEY or 'local'}"}

    try:
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SEC) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        content = data["choices"][0]["message"]["content"]
        raw = _extract_json(content)
        result = _normalize_result(raw)
        logger.info("备注分析完成: score=%s risk_type=%s", result["score"], result["risk_type"])
        return result
    except Exception:
        logger.exception("DeepSeek 备注分析失败, 使用兜底 0 分")
        return dict(DEFAULT_RESULT)
