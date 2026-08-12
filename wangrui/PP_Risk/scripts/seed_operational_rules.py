"""Seed executable baseline rules that match the implemented feature names."""

from __future__ import annotations

import asyncio
import json

from sqlalchemy import select

from app.database import AsyncSessionLocal, create_schema
from app.models_risk import RiskRule


RULES = (
    ("PPR001", "制裁名单高置信命中", "制裁与非法用户", "通用", "user_screening_match_score", ">=", 0.95, "极高", 100, "拒绝"),
    ("PPR002", "名单筛查需要增强审核", "制裁与非法用户", "通用", "user_screening_match_score", ">=", 0.75, "高", 85, "人工审核"),
    ("PPR003", "KYC人脸分过低", "身份欺诈", "下单", "user_kyc_face_score", "<", 0.70, "极高", 95, "拒绝"),
    ("PPR004", "KYC活体分过低", "身份欺诈", "下单", "user_kyc_liveness_score", "<", 0.70, "极高", 95, "拒绝"),
    ("PPR005", "模拟器设备交易", "账户接管", "支付", "device_is_emulator", ">=", 1, "高", 80, "人工审核"),
    ("PPR006", "Root设备交易", "账户接管", "支付", "device_is_rooted", ">=", 1, "高", 80, "人工审核"),
    ("PPR007", "超大额交易", "AML", "支付", "transaction_amount", ">=", 10000, "高", 80, "人工审核"),
    ("PPR008", "大额跨境交易", "AML", "支付", "transaction_is_cross_border", ">=", 1, "高", 75, "人工审核"),
    ("PPR009", "深夜资金交易", "支付欺诈", "支付", "transaction_is_night", ">=", 1, "中", 45, "标记"),
    ("PPR010", "资金进出事件", "AML", "支付", "transaction_is_cash_movement", ">=", 1, "中", 40, "标记"),
    ("PPR011", "用户历史交易额异常", "AML", "通用", "user_transaction_amount", ">=", 100000, "高", 75, "人工审核"),
    ("PPR012", "用户历史交易频次异常", "反欺诈", "通用", "user_transaction_count", ">=", 500, "高", 70, "人工审核"),
)


async def seed_rules() -> int:
    await create_schema()
    inserted = 0
    async with AsyncSessionLocal() as db:
        existing = set((await db.execute(select(RiskRule.rule_id))).scalars())
        for index, rule in enumerate(RULES):
            rule_id, name, category, event_type, feature, operator, value, level, score, action = rule
            if rule_id in existing:
                continue
            db.add(
                RiskRule(
                    rule_id=rule_id,
                    rule_name=name,
                    rule_category=category,
                    event_type=event_type,
                    rule_condition=json.dumps(
                        {"feature": feature, "operator": operator, "value": value},
                        ensure_ascii=False,
                    ),
                    risk_level=level,
                    risk_score=score,
                    action=action,
                    is_enabled=True,
                    priority=100 - index,
                    description="PP_Risk executable baseline rule",
                )
            )
            inserted += 1
        await db.commit()
    return inserted


if __name__ == "__main__":
    print(f"Inserted {asyncio.run(seed_rules())} operational rules")

