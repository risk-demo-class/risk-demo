#!/usr/bin/env python3
"""重置/初始化教育风控数据库。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
import app.models  # noqa: E402,F401
from app.models_risk import RiskRule  # noqa: E402


RULE_SEEDS = [
    ("R001", "刷单式报名", "报名风险", "报名支付成功", {"field": "course_linked_new_student_count_7d", "op": ">=", "value": 3}, "极高", 100, "拒绝", 100),
    ("R002", "0学时退费", "退费风险", "退费申请提交", {"field": "study_minutes_before_refund", "op": "<", "value": 5}, "高", 80, "人工审核", 80),
    ("R005", "大额连报", "报名风险", "报名支付成功", {"field": "buyer_paid_amount_1h", "op": ">", "value": 30000}, "高", 80, "人工审核", 80),
    ("R008", "假学员代理", "设备风险", "设备关联更新", {"field": "device_student_count", "op": ">=", "value": 5}, "极高", 100, "拒绝", 100),
    ("R012", "退费连环", "退费风险", "退款成功", {"and": [{"field": "user_refund_count_90d", "op": ">=", "value": 3}, {"field": "user_refund_amount_90d", "op": ">", "value": 10000}]}, "中", 50, "标记", 50),
    ("R018", "直播打赏异常", "直播风险", "直播打赏变更", {"and": [{"field": "session_reward_net_amount", "op": ">", "value": 5000}, {"field": "account_age_days", "op": "<", "value": 30}]}, "中", 50, "标记", 50),
    ("R025", "学历认证冲突", "认证风险", "学历核验完成", {"field": "credential_mismatch", "op": "==", "value": 1}, "高", 80, "人工审核", 80),
    ("R030", "黑学员拦截", "黑名单风险", "通用", {"field": "student_blacklist_hit", "op": "==", "value": 1}, "极高", 100, "拒绝", 1000),
]


def seed_rules() -> None:
    with SessionLocal.begin() as db:
        for rid, name, category, event, condition, level, score, action, priority in RULE_SEEDS:
            db.add(RiskRule(
                rule_id=rid, rule_name=name, rule_category=category, event_type=event,
                rule_condition=condition, risk_level=level, risk_score=score,
                action=action, enabled=True, priority=priority, version=1,
                description=f"教育风控首期规则 {rid}",
            ))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="删除现有表后重建")
    parser.add_argument("--yes", action="store_true", help="确认破坏性重置")
    args = parser.parse_args()
    if args.reset and not args.yes:
        raise SystemExit("--reset 会删除 risk_proj 全部表，请同时传 --yes")
    if args.reset:
        with engine.begin() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
            Base.metadata.drop_all(conn)
            conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        has_rules = db.query(RiskRule).count() > 0
    if not has_rules:
        seed_rules()
    print(f"init_db OK: tables={len(Base.metadata.tables)}, rules=8, reset={args.reset}")


if __name__ == "__main__":
    main()
