#!/usr/bin/env python3
"""生成 1000 条教育风控评估；按固定策略保证正例比例约 20%。"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.engine.ml_model import FEATURE_COLUMNS  # noqa: E402
from app.engine.decision import calculate_decision  # noqa: E402
from app.engine.rule import load_enabled_rules, match_rules  # noqa: E402
from app.models_business import UserInfo  # noqa: E402
from app.models_risk import RiskAssessment, RiskCase, RiskEvent, RiskFeature  # noqa: E402


POSITIVE_RULES = [
    ("R001", "报名支付成功"), ("R002", "退费申请提交"),
    ("R005", "报名支付成功"), ("R008", "设备关联更新"),
    ("R012", "退款成功"), ("R018", "直播打赏变更"),
    ("R025", "学历核验完成"), ("R030", "通用"),
]


def baseline() -> dict[str, float]:
    f = {name: 0.0 for name in FEATURE_COLUMNS}
    f.update({
        "account_age_days": 120.0, "is_student": 1.0,
        "is_real_name_verified": 1.0, "study_minutes_before_refund": 30.0,
        "completion_rate": 30.0, "order_course_price_ratio": 1.0,
    })
    return f


def inject_positive(features: dict[str, float], rule_id: str) -> None:
    values = {
        "R001": {"course_linked_new_student_count_7d": 3.0},
        "R002": {"study_minutes_before_refund": 2.0},
        "R005": {"buyer_paid_amount_1h": 35000.0},
        "R008": {"device_student_count": 5.0},
        "R012": {"user_refund_count_90d": 3.0, "user_refund_amount_90d": 12000.0},
        "R018": {"session_reward_net_amount": 6000.0, "account_age_days": 5.0},
        "R025": {"credential_mismatch": 1.0},
        "R030": {"student_blacklist_hit": 1.0},
    }
    features.update(values[rule_id])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=1000, choices=range(500, 2001), metavar="500..2000")
    args = parser.parse_args()
    with SessionLocal() as db:
        users = list(db.scalars(select(UserInfo.user_id).where(UserInfo.user_id.like("RISK-STU-%")).order_by(UserInfo.user_id)))
        if len(users) < 20:
            raise SystemExit("请先运行 python scripts/gen_risky_users.py")
        # 本脚本拥有评估演示数据，重跑时清空并重建这四张表的数据。
        db.execute(delete(RiskCase))
        db.execute(delete(RiskFeature))
        db.execute(delete(RiskAssessment))
        db.execute(delete(RiskEvent))
        db.commit()

        positive = 0
        now = datetime.now()
        for i in range(args.count):
            is_positive = i % 5 == 0
            rule_id, event_type = POSITIVE_RULES[(i // 5) % len(POSITIVE_RULES)] if is_positive else ("", POSITIVE_RULES[i % len(POSITIVE_RULES)][1])
            features = baseline()
            if is_positive:
                inject_positive(features, rule_id)
            user_id = users[i % len(users)]
            event_id, assessment_id = f"GEN-EVT-{i:06d}", f"GEN-ASMT-{i:06d}"
            occurred = now - timedelta(minutes=args.count - i)
            event = RiskEvent(
                event_id=event_id, event_type=event_type, event_source_id=f"GEN-SRC-{i:06d}",
                user_id=user_id, event_data={"generated": True, "target_rule": rule_id or None},
                occurred_at=occurred,
            )
            db.add(event)
            db.flush()
            rules = load_enabled_rules(db, event_type)
            hits = match_rules(rules, features)
            result = calculate_decision(hits)
            score, level, decision = result.score, result.risk_level, result.decision
            if decision != "通过":
                positive += 1
            db.add(RiskAssessment(
                assessment_id=assessment_id, event_id=event_id, user_id=user_id,
                feature_snapshot=features, rule_results=[hit.to_dict() for hit in hits],
                rule_count=len(hits), final_score=score, risk_level=level, decision=decision,
                blocked_by="学号" if any(hit.rule_id == "R030" for hit in hits) else None,
            ))
            for name, value in features.items():
                db.add(RiskFeature(
                    event_id=event_id, entity_type="用户", entity_id=user_id,
                    feature_name=name, feature_value=value, data_as_of=occurred,
                ))
            if decision == "人工审核":
                db.add(RiskCase(
                    case_id=f"GEN-CASE-{i:06d}", assessment_id=assessment_id,
                    user_id=user_id, case_category=event_type,
                    risk_detail={"rule_ids": [hit.rule_id for hit in hits]},
                ))
            if (i + 1) % 100 == 0:
                db.commit()
        db.commit()
    ratio = positive / args.count
    if ratio < 0.15:
        raise RuntimeError(f"正例比例不足: {ratio:.2%}")
    print(f"gen_risk_data OK: assessments={args.count}, positive={positive}, positive_ratio={ratio:.2%}")


if __name__ == "__main__":
    main()
