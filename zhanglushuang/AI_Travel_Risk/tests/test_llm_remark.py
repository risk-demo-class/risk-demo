"""LLM 备注分析测试."""

import asyncio

from app.llm.remark_analyzer import (
    DEFAULT_RESULT,
    _extract_json,
    _normalize_result,
    analyze_order_remark,
)


def test_extract_json():
    content = '```json\n{"score": 85, "risk_type": "scalper_code"}\n```'
    result = _extract_json(content)
    assert result["score"] == 85


def test_normalize_result_clamps_score():
    result = _normalize_result({"score": 999, "risk_type": "unknown"})
    assert result["score"] == 100
    assert result["risk_type"] == "normal"


def test_analyze_disabled_returns_default():
    async def run():
        return await analyze_order_remark("多订几张，一起走")

    result = asyncio.run(run())
    assert result == DEFAULT_RESULT
