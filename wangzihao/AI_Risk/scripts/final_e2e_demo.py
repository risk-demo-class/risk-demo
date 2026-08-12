"""Step 7 制造业端到端 Demo（仅允许在非默认独立数据库运行）。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.tools import _biz_risk_assessment_evidence
from app.config import settings
from app.engine.decision import calculate_final_score, check_veto
from app.engine.ml_model import FEATURE_COLUMNS, get_model, load_model
from app.models import (
    CrossRegionReport, Dealer, Device, PurchaseOrder, RiskCase,
    WarrantyClaim,
)
from app.schemas import RiskCheckRequest
from app.service.event import process_event


KEY_FEATURES = (
    "user_cancel_count", "user_orders_7d", "user_postsale_count",
    "user_refund_amount", "user_complaint_count", "order_total_amount",
    "order_sku_count", "order_category_count", "addr_is_new",
)


async def _dealer_by_mode(db, mode: str) -> Dealer:
    return (await db.execute(
        select(Dealer).where(Dealer.name.like(f"ML-{mode}-%"))
        .order_by(Dealer.dealer_id).limit(1)
    )).scalar_one()


async def _device_for_dealer(db, dealer_id: str) -> Device:
    return (await db.execute(
        select(Device).where(Device.dealer_id == dealer_id)
        .order_by(Device.device_id).limit(1)
    )).scalar_one()


async def _reset_demo_scope(db) -> None:
    """只清理 D7* Demo 来源；调用方已拒绝默认生产数据库。"""
    await db.execute(text("""
        DELETE FROM risk_action_log WHERE target_type='case' AND target_id IN (
          SELECT case_id FROM risk_case WHERE source_id LIKE 'D7%'
        )
    """))
    await db.execute(text("DELETE FROM risk_case WHERE source_id LIKE 'D7%'"))
    await db.execute(text("""
        DELETE FROM risk_assessment WHERE event_id IN (
          SELECT event_id FROM risk_event WHERE event_source_id LIKE 'D7%'
        )
    """))
    await db.execute(text("""
        DELETE FROM risk_feature WHERE event_id IN (
          SELECT event_id FROM risk_event WHERE event_source_id LIKE 'D7%'
        )
    """))
    await db.execute(text("DELETE FROM risk_event WHERE event_source_id LIKE 'D7%'"))
    await db.execute(text("DELETE FROM cross_region_report WHERE report_id LIKE 'D7%'"))
    await db.execute(text("DELETE FROM warranty_claim WHERE claim_id LIKE 'D7%'"))
    await db.execute(text("DELETE FROM purchase_order WHERE po_id LIKE 'D7%'"))
    await db.commit()


async def _prepare_sources(db) -> list[dict]:
    normal = await _dealer_by_mode(db, "NORMAL_LONG")
    new_large = await _dealer_by_mode(db, "RISK_NEW_LARGE")
    warranty_risk = await _dealer_by_mode(db, "RISK_WARRANTY")
    cross_risk = await _dealer_by_mode(db, "RISK_CROSS_REGION")
    blacklisted = await _dealer_by_mode(db, "BLACKLISTED")
    normal_device = await _device_for_dealer(db, normal.dealer_id)
    warranty_device = await _device_for_dealer(db, warranty_risk.dealer_id)
    cross_device = await _device_for_dealer(db, cross_risk.dealer_id)

    now = datetime.now()
    rows = [
        PurchaseOrder(
            po_id="D7PO_NORMAL", dealer_id=normal.dealer_id,
            total_amount=Decimal("160000"),
            items=[{"model": "MX-DEMO", "quantity": 2}],
            ship_to=normal.region, payment_term="账期30天", create_time=now,
        ),
        PurchaseOrder(
            po_id="D7PO_NEW_LARGE", dealer_id=new_large.dealer_id,
            total_amount=Decimal("1350000"),
            items=[{"model": "MX-DEMO", "quantity": 12}],
            ship_to=new_large.region, payment_term="预付", create_time=now,
        ),
        PurchaseOrder(
            po_id="D7PO_BLACKLIST", dealer_id=blacklisted.dealer_id,
            total_amount=Decimal("180000"),
            items=[{"model": "MX-DEMO", "quantity": 1}],
            ship_to=blacklisted.region, payment_term="预付", create_time=now,
        ),
        WarrantyClaim(
            claim_id="D7CLM_NORMAL", device_id=normal_device.device_id,
            dealer_id=normal.dealer_id, fault_desc="常规传感器校准",
            claim_amount=Decimal("8000"), photos=["normal-1.jpg"], create_time=now,
        ),
        WarrantyClaim(
            claim_id="D7CLM_RISK", device_id=warranty_device.device_id,
            dealer_id=warranty_risk.dealer_id, fault_desc="高金额重复保修且材料缺失",
            claim_amount=Decimal("180000"), photos=None, create_time=now,
        ),
        CrossRegionReport(
            report_id="D7CRR_CROSS", device_id=cross_device.device_id,
            expected_region=cross_risk.region, actual_region="境外异常区域",
            reporter_id="D7-INSPECTOR", create_time=now,
        ),
    ]
    db.add_all(rows)
    await db.commit()
    return [
        {"demo": "A", "scenario": "长期经销商正常采购", "event_type": "下单", "source_id": "D7PO_NORMAL", "dealer_id": normal.dealer_id},
        {"demo": "B", "scenario": "新经销商大额采购", "event_type": "下单", "source_id": "D7PO_NEW_LARGE", "dealer_id": new_large.dealer_id},
        {"demo": "C", "scenario": "正常设备保修", "event_type": "售后申请", "source_id": "D7CLM_NORMAL", "dealer_id": normal.dealer_id},
        {"demo": "D", "scenario": "高频高金额材料缺失保修", "event_type": "售后申请", "source_id": "D7CLM_RISK", "dealer_id": warranty_risk.dealer_id},
        {"demo": "E", "scenario": "跨区域串货", "event_type": "物流投诉", "source_id": "D7CRR_CROSS", "dealer_id": cross_risk.dealer_id},
        {"demo": "F", "scenario": "黑名单经销商", "event_type": "下单", "source_id": "D7PO_BLACKLIST", "dealer_id": blacklisted.dealer_id},
    ]


def _rule_score(triggered_rules) -> int:
    hits = [SimpleNamespace(risk_score=r.risk_score, risk_level=r.risk_level) for r in triggered_rules]
    score = calculate_final_score(hits)
    return max(score, settings.RISK_VETO_MIN_SCORE) if check_veto(hits) else score


async def run_demo(db_name: str) -> dict:
    if db_name == settings.DB_NAME:
        raise RuntimeError("Step 7 Demo 拒绝写入默认数据库；请使用独立 --db")
    if not load_model():
        raise RuntimeError("标准制造业 XGBoost 模型加载失败")
    model = get_model()
    if model is None or model.num_features() != 25 or model.feature_names != FEATURE_COLUMNS:
        raise RuntimeError("标准模型与25维 FEATURE_COLUMNS 不一致")

    engine = create_async_engine(settings.get_database_url_async(db_name), pool_pre_ping=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    output = {
        "database": db_name,
        "default_database_protected": db_name != settings.DB_NAME,
        "model": {"loaded": True, "feature_count": model.num_features(), "feature_names_match": model.feature_names == FEATURE_COLUMNS},
        "demos": [],
    }
    try:
        async with factory() as db:
            await _reset_demo_scope(db)
            scenarios = await _prepare_sources(db)
            for item in scenarios:
                before_alerts = int((await db.execute(text("SELECT COUNT(*) FROM risk_alert"))).scalar_one())
                response = await process_event(db, RiskCheckRequest(
                    event_type=item["event_type"], source_id=item["source_id"],
                    user_id=item["dealer_id"], event_data={"step7_demo": item["demo"]},
                ))
                after_alerts = int((await db.execute(text("SELECT COUNT(*) FROM risk_alert"))).scalar_one())
                record = {
                    **item,
                    "business_input": {"event_type": item["event_type"], "source_id": item["source_id"], "dealer_id": item["dealer_id"]},
                    "event_id": response.event_id,
                    "assessment_id": response.assessment_id,
                    "feature_count": len(response.features),
                    "key_features": {name: response.features[name] for name in KEY_FEATURES if name in response.features},
                    "triggered_rules": [rule.model_dump() for rule in response.triggered_rules],
                    "rule_score": _rule_score(response.triggered_rules),
                    "xgboost_probability": response.ml_score,
                    "ml_score": response.ml_score,
                    "final_score": response.final_score,
                    "risk_level": response.risk_level,
                    "action": response.decision,
                    "blocked_by": response.blocked_by,
                    "risk_case_generated": False,
                    "risk_case_id": None,
                    "alert_generated": after_alerts > before_alerts,
                    "alert_note": "risk_alert 是聚合监控告警，不是逐事件告警",
                }
                if response.blocked_by is None:
                    case_id = (await db.execute(
                        select(RiskCase.case_id).where(RiskCase.assessment_id == response.assessment_id)
                    )).scalar_one_or_none()
                    record["risk_case_generated"] = case_id is not None
                    record["risk_case_id"] = case_id
                    evidence = await _biz_risk_assessment_evidence(
                        db, item["dealer_id"], response.assessment_id, 1,
                    )
                    record["agent_explanation"] = evidence[0]["agent_explanation"]
                    if record["feature_count"] != 25:
                        raise RuntimeError(f"Demo {item['demo']} 没有生成25维特征")
                else:
                    record["agent_explanation"] = (
                        f"结论：经销商 {item['dealer_id']} 命中内部“{response.blocked_by}”黑名单，"
                        "process_event 第3步直接拒绝，未执行 run_risk_check，因此没有规则、25维特征或ML评分。"
                    )
                output["demos"].append(record)
    finally:
        await engine.dispose()
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="制造业 Agent/规则/ML/页面最终证据链 Demo")
    parser.add_argument("--db", required=True, help="必须是非默认的独立验收数据库")
    args = parser.parse_args()
    asyncio.run(run_demo(args.db))


if __name__ == "__main__":
    main()
