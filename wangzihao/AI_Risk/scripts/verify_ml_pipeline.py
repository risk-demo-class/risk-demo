"""Verify real manufacturing inference and online run_risk_check persistence."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.engine.feature import compute_all_features
from app.engine.ml_model import FEATURE_COLUMNS, load_model, predict
from app.models import CrossRegionReport, Dealer, PurchaseOrder, WarrantyClaim
from app.schemas import RiskCheckRequest
from app.service.event import process_event


KEY_FEATURES = (
    "user_cancel_count",
    "user_postsale_count",
    "order_total_amount",
    "order_sku_count",
    "order_category_count",
    "addr_is_new",
)


async def _scenario_sources(db) -> list[tuple[str, str, str]]:
    async def dealer_id(mode: str) -> str:
        return (await db.execute(
            select(Dealer.dealer_id)
            .where(Dealer.name.like(f"ML-{mode}-%"))
            .order_by(Dealer.dealer_id).limit(1)
        )).scalar_one()

    normal = await dealer_id("NORMAL_LONG")
    new_large = await dealer_id("RISK_NEW_LARGE")
    warranty_risk = await dealer_id("RISK_WARRANTY")
    cross_risk = await dealer_id("RISK_CROSS_REGION")

    normal_po = (await db.execute(select(PurchaseOrder.po_id).where(
        PurchaseOrder.dealer_id == normal).order_by(PurchaseOrder.po_id).limit(1)
    )).scalar_one()
    large_po = (await db.execute(select(PurchaseOrder.po_id).where(
        PurchaseOrder.dealer_id == new_large).order_by(PurchaseOrder.po_id).limit(1)
    )).scalar_one()
    normal_claim = (await db.execute(select(WarrantyClaim.claim_id).where(
        WarrantyClaim.dealer_id == normal).order_by(WarrantyClaim.claim_id).limit(1)
    )).scalar_one()
    abnormal_claim = (await db.execute(select(WarrantyClaim.claim_id).where(
        WarrantyClaim.dealer_id == warranty_risk
    ).order_by(WarrantyClaim.claim_amount.desc()).limit(1))).scalar_one()
    normal_report = (await db.execute(text("""
        SELECT r.report_id FROM cross_region_report r
        JOIN device d ON d.device_id=r.device_id
        WHERE d.dealer_id=:dealer_id ORDER BY r.report_id LIMIT 1
    """), {"dealer_id": normal})).scalar_one()
    cross_report = (await db.execute(text("""
        SELECT r.report_id FROM cross_region_report r
        JOIN device d ON d.device_id=r.device_id
        WHERE d.dealer_id=:dealer_id ORDER BY r.report_id LIMIT 1
    """), {"dealer_id": cross_risk})).scalar_one()
    return [
        ("正常采购", normal_po, normal),
        ("新经销商大额采购", large_po, new_large),
        ("正常保修", normal_claim, normal),
        ("高频高金额保修", abnormal_claim, warranty_risk),
        ("正常区域", normal_report, normal),
        ("跨区域串货", cross_report, cross_risk),
    ]


async def verify(db_name: str, model_path: str | None = None) -> dict:
    if not load_model(model_path):
        raise RuntimeError("manufacturing XGBoost model failed to load")
    engine = create_async_engine(settings.get_database_url_async(db_name), pool_pre_ping=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    output: dict = {"inference": [], "online": [], "blacklist": {}}
    try:
        async with factory() as db:
            for name, source_id, dealer_id in await _scenario_sources(db):
                features = await compute_all_features(db, dealer_id, source_id, None)
                if list(features) != FEATURE_COLUMNS:
                    raise RuntimeError(f"{name}: FEATURE_COLUMNS order mismatch")
                result = predict(features)
                output["inference"].append({
                    "scenario": name,
                    "source_id": source_id,
                    "dealer_id": dealer_id,
                    "feature_count": len(features),
                    "key_features": {key: features[key] for key in KEY_FEATURES},
                    "predict_proba": result.score,
                    "ml_score": result.score,
                    "ml_decision": result.decision,
                })

            normal_dealer = output["inference"][0]["dealer_id"]
            risk_dealer = output["inference"][1]["dealer_id"]
            suffix = uuid.uuid4().hex[:10]
            online_rows = [
                ("正常制造业事件", f"ONLINE_NORMAL_{suffix}", normal_dealer, Decimal("160000")),
                ("高风险制造业事件", f"ONLINE_RISK_{suffix}", risk_dealer, Decimal("1350000")),
            ]
            for scenario, po_id, dealer_id, amount in online_rows:
                region = (await db.execute(select(Dealer.region).where(
                    Dealer.dealer_id == dealer_id
                ))).scalar_one()
                db.add(PurchaseOrder(
                    po_id=po_id,
                    dealer_id=dealer_id,
                    total_amount=amount,
                    items=[{"model": "MX-ONLINE", "quantity": 2}],
                    ship_to=f"{region}-在线验收仓",
                    payment_term="账期30天",
                ))
                await db.commit()
                response = await process_event(db, RiskCheckRequest(
                    event_type="下单", source_id=po_id, user_id=dealer_id,
                    event_data={"step6_online_verification": True},
                ))
                persisted = (await db.execute(text("""
                    SELECT a.ml_score, a.rule_count, a.final_score,
                           (SELECT COUNT(*) FROM risk_feature f WHERE f.event_id=e.event_id)
                    FROM risk_assessment a
                    JOIN risk_event e ON e.event_id=a.event_id
                    WHERE a.assessment_id=:assessment_id
                """), {"assessment_id": response.assessment_id})).one()
                output["online"].append({
                    "scenario": scenario,
                    "source_id": po_id,
                    "event_id": response.event_id,
                    "assessment_id": response.assessment_id,
                    "ml_score": float(persisted[0]),
                    "rule_score_evidence_rule_count": int(persisted[1]),
                    "final_score": int(persisted[2]),
                    "risk_feature_count": int(persisted[3]),
                    "decision": response.decision,
                })

            blacklisted = (await db.execute(select(Dealer.dealer_id).where(
                Dealer.name.like("ML-BLACKLISTED-%")
            ).order_by(Dealer.dealer_id).limit(1))).scalar_one()
            blacklisted_po = (await db.execute(select(PurchaseOrder.po_id).where(
                PurchaseOrder.dealer_id == blacklisted
            ).order_by(PurchaseOrder.po_id).limit(1))).scalar_one()
            before = int((await db.execute(text(
                "SELECT COUNT(*) FROM risk_event WHERE event_source_id=:source_id"
            ), {"source_id": blacklisted_po})).scalar_one())
            blocked = await process_event(db, RiskCheckRequest(
                event_type="下单", source_id=blacklisted_po, user_id=blacklisted,
                event_data={"step6_blacklist_verification": True},
            ))
            after = int((await db.execute(text(
                "SELECT COUNT(*) FROM risk_event WHERE event_source_id=:source_id"
            ), {"source_id": blacklisted_po})).scalar_one())
            output["blacklist"] = {
                "dealer_id": blacklisted,
                "source_id": blacklisted_po,
                "blocked_by": blocked.blocked_by,
                "decision": blocked.decision,
                "risk_event_count_before": before,
                "risk_event_count_after": after,
                "run_risk_check_executed": after != before,
            }
    finally:
        await engine.dispose()
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="制造业 ML 推理与在线决策集成验收")
    parser.add_argument("--db", default=settings.DB_NAME)
    parser.add_argument("--model-path")
    args = parser.parse_args()
    asyncio.run(verify(args.db, args.model_path))


if __name__ == "__main__":
    main()
