"""
物流风控评估数据生成 (异步)

从 logistics_waybill / complaint / claim / cod 里随机挑业务单据,
调用 process_event 走完整风控流水线, 生成 risk_event / risk_feature /
risk_assessment / risk_case / risk_user_profile.

用法:
  python scripts/gen_logistics_risk_data.py --count 200
  python scripts/gen_logistics_risk_data.py --count 200 --clean-ml
"""
import argparse
import asyncio
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.database import AsyncSessionLocal, async_engine
from app.schemas import RiskCheckRequest
from app.service.event import process_event

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


async def _pick_waybill(db) -> tuple | None:
    row = (await db.execute(text(
        "SELECT waybill_no, sender_id FROM logistics_waybill ORDER BY RAND() LIMIT 1"
    ))).first()
    return (row.waybill_no, row.sender_id) if row else None


async def _pick_risk_waybill(db) -> tuple | None:
    """优先挑高风险运单: 未实名/危险品/COD拒收/跨境, 提高正例比例."""
    row = (await db.execute(text("""
        SELECT w.waybill_no, w.sender_id
        FROM logistics_waybill w
        LEFT JOIN logistics_sender s ON s.sender_id = w.sender_id
        LEFT JOIN logistics_cod_settlement c
               ON c.waybill_no = w.waybill_no AND c.collect_status = '拒收'
        WHERE s.is_real_name_verified = 0
           OR s.verify_fail_count >= 3
           OR w.item_category IN ('电池', '化学品')
           OR w.is_cross_border = 1
           OR c.cod_id IS NOT NULL
        ORDER BY RAND() LIMIT 1
    """))).first()
    return (row.waybill_no, row.sender_id) if row else None


async def _pick_cross_waybill(db) -> tuple | None:
    row = (await db.execute(text(
        "SELECT w.waybill_no, w.sender_id FROM logistics_waybill w "
        "JOIN logistics_customs_info c ON c.waybill_no = w.waybill_no "
        "ORDER BY RAND() LIMIT 1"
    ))).first()
    return (row.waybill_no, row.sender_id) if row else None


async def _pick_complaint(db) -> tuple | None:
    row = (await db.execute(text(
        "SELECT c.complaint_id, w.sender_id FROM logistics_complaint_record c "
        "JOIN logistics_waybill w ON w.waybill_no = c.waybill_no "
        "ORDER BY RAND() LIMIT 1"
    ))).first()
    return (row.complaint_id, row.sender_id) if row else None


async def _pick_claim(db) -> tuple | None:
    row = (await db.execute(text(
        "SELECT c.claim_id, w.sender_id FROM logistics_claim c "
        "JOIN logistics_waybill w ON w.waybill_no = c.waybill_no "
        "ORDER BY RAND() LIMIT 1"
    ))).first()
    return (row.claim_id, row.sender_id) if row else None


async def _pick_cod(db) -> tuple | None:
    row = (await db.execute(text(
        "SELECT c.cod_id, w.sender_id FROM logistics_cod_settlement c "
        "JOIN logistics_waybill w ON w.waybill_no = c.waybill_no "
        "ORDER BY RAND() LIMIT 1"
    ))).first()
    return (row.cod_id, row.sender_id) if row else None


async def gen_logistics_risk_data(
    count: int = 200,
    clean_ml: bool = False,
    balance_pos: bool = False,
) -> None:
    print("=" * 60)
    print(f"开始生成物流风控评估数据 (目标 {count} 条, balance_pos={balance_pos})")
    print("=" * 60)

    success = 0
    pos = 0
    failed = 0
    async with AsyncSessionLocal() as db:
        for i in range(1, count + 1):
            event_type = random.choices(
                ["寄件下单", "揽收", "签收", "投诉", "理赔申请", "COD结算", "报关清关"],
                weights=[40, 15, 15, 8, 8, 8, 6],
            )[0]
            try:
                if event_type in ("寄件下单", "揽收", "签收"):
                    use_risk = balance_pos and random.random() < 0.8
                    picked = await (_pick_risk_waybill(db) if use_risk else _pick_waybill(db))
                    if not picked:
                        continue
                    source_id, sender_id = picked
                elif event_type == "报关清关":
                    picked = await _pick_cross_waybill(db)
                    if not picked:
                        continue
                    source_id, sender_id = picked
                elif event_type == "投诉":
                    picked = await _pick_complaint(db)
                    if not picked:
                        continue
                    source_id, sender_id = picked
                elif event_type == "理赔申请":
                    picked = await _pick_claim(db)
                    if not picked:
                        continue
                    source_id, sender_id = picked
                else:  # COD结算
                    picked = await _pick_cod(db)
                    if not picked:
                        continue
                    source_id, sender_id = picked

                result = await process_event(db, RiskCheckRequest(
                    event_type=event_type,
                    source_id=source_id,
                    user_id=sender_id,
                ))
                success += 1
                if result.decision in ("人工审核", "拒绝"):
                    pos += 1
                if i % 50 == 0:
                    print(f"  进度 {i}/{count}: 成功 {success}, 正例 {pos}")
            except Exception as e:
                failed += 1
                if failed <= 5:
                    print(f"  [失败] {event_type} source={source_id}: {e}")

        if clean_ml:
            await db.execute(text(
                "UPDATE risk_assessment SET ml_score = NULL, ml_decision = NULL"
            ))
            await db.commit()

    print("=" * 60)
    print(f"物流风控评估生成完成: 成功 {success}, 正例 {pos} "
          f"({100 * pos / max(success, 1):.1f}%), 失败 {failed}")
    print(f"clean_ml={clean_ml} (训练数据无 ml 痕迹)")
    print("下一步: python scripts/train_xgb_model.py")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="物流风控评估数据生成")
    parser.add_argument("--count", type=int, default=200, help="评估条数")
    parser.add_argument("--clean-ml", action="store_true", help="生成后清空 ml_score (训练用)")
    parser.add_argument("--balance-pos", action="store_true",
                        help="80% 概率挑高风险运单, 提高正例比例")
    args = parser.parse_args()

    async def _runner() -> None:
        try:
            await gen_logistics_risk_data(
                count=args.count, clean_ml=args.clean_ml, balance_pos=args.balance_pos,
            )
        finally:
            await async_engine.dispose()

    asyncio.run(_runner())


if __name__ == "__main__":
    main()
