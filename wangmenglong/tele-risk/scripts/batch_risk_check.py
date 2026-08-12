"""
批量风控检查脚本: 对全部号卡 (299 张: 60 风险 + 239 正常) 跑风控评估.

直接调用 process_event (不走 HTTP), 高性能批量处理.
source_id 从业务表中查询有效 ID, 通过 ensure_source_matches_event_type 校验.
自动在多种事件类型间回退, 确保每张卡都有可用的 source_id.

用法: python scripts/batch_risk_check.py [--risk-only] [--limit N]
默认: 全部 299 张, 加 --limit 可缩减
"""
import asyncio
import json
import random
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import (
    TelecomCard, TelecomCdr, TelecomServiceOrder, TelecomSms, TelecomIotCard,
)
from app.schemas import RiskCheckRequest
from app.service.event import process_event

EVENT_TYPES = ["开户", "通话", "国际来电", "短信发送", "物联网激活"]


def _msisdn_idx(msisdn: str) -> int:
    try:
        return int(msisdn[3:])
    except (ValueError, TypeError):
        return 0


def _preferred_event_types(msisdn: str) -> list[str]:
    """按号卡画像返回推荐的事件类型列表 (优先级从高到低)."""
    idx = _msisdn_idx(msisdn)
    if 1 <= idx <= 8:
        return ["通话", "国际来电", "开户", "短信发送"]
    if 9 <= idx <= 18:
        return ["通话", "开户", "短信发送"]
    if 19 <= idx <= 28:
        return ["通话", "开户", "短信发送"]
    if 29 <= idx <= 35:
        return ["国际来电", "通话", "开户", "短信发送"]
    if 36 <= idx <= 50:
        return ["物联网激活", "通话", "开户", "短信发送"]
    if 290 <= idx <= 294:
        return ["通话", "开户", "短信发送"]
    if 295 <= idx <= 299:
        return ["通话", "开户", "短信发送"]
    return ["通话", "开户", "短信发送"]


async def _find_source_id(db, event_type: str, msisdn: str) -> str:
    """从业务表查询对应 event_type 的有效 source_id."""
    if event_type in ("通话", "国际来电"):
        row = (await db.execute(
            select(TelecomCdr.cdr_id).where(TelecomCdr.calling_no == msisdn).limit(1)
        )).first()
        if row:
            return str(row[0])
        row = (await db.execute(
            select(TelecomCdr.cdr_id).where(TelecomCdr.called_no == msisdn).limit(1)
        )).first()
        if row:
            return str(row[0])
    elif event_type == "开户":
        row = (await db.execute(
            select(TelecomServiceOrder.order_id).where(TelecomServiceOrder.msisdn == msisdn).limit(1)
        )).first()
        if row:
            return str(row[0])
    elif event_type == "短信发送":
        row = (await db.execute(
            select(TelecomSms.sms_id).where(TelecomSms.sending_no == msisdn).limit(1)
        )).first()
        if row:
            return str(row[0])
    elif event_type == "物联网激活":
        row = (await db.execute(
            select(TelecomIotCard.msisdn).where(TelecomIotCard.msisdn == msisdn).limit(1)
        )).first()
        if row:
            return str(row[0])
    return ""


async def _find_best_event_and_source(db, msisdn: str) -> tuple[str, str]:
    """遍历推荐事件类型, 返回第一个有有效 source_id 的 (event_type, source_id)."""
    for evt in _preferred_event_types(msisdn):
        sid = await _find_source_id(db, evt, msisdn)
        if sid:
            return evt, sid
    return "开户", ""


async def main():
    db = AsyncSessionLocal()

    cards = (await db.execute(
        select(TelecomCard.msisdn, TelecomCard.card_status)
    )).all()
    print(f"共 {len(cards)} 张号卡")

    risk_cards = []
    normal_cards = []
    for msisdn, status in cards:
        idx = _msisdn_idx(msisdn)
        if (1 <= idx <= 50) or (290 <= idx <= 299):
            risk_cards.append(msisdn)
        else:
            normal_cards.append(msisdn)

    print(f"  风险号卡: {len(risk_cards)}")
    print(f"  正常号卡: {len(normal_cards)}")

    args = sys.argv[1:]
    risk_only = "--risk-only" in args
    limit = None
    for i, a in enumerate(args):
        if a == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])

    if risk_only:
        targets = risk_cards
    else:
        targets = risk_cards + normal_cards

    if limit:
        targets = targets[:limit]

    print(f"\n将对 {len(targets)} 张号卡跑风控检查")
    print("=" * 60)

    stats = {"通过": 0, "标记": 0, "人工审核": 0, "关停号码": 0, "error": 0}

    for i, msisdn in enumerate(targets):
        event_type, source_id = await _find_best_event_and_source(db, msisdn)

        req = RiskCheckRequest(
            event_type=event_type,
            source_id=source_id,
            msisdn=msisdn,
            event_data={"triggered_by": "batch_script", "seq": i + 1},
        )

        try:
            resp = await process_event(db, req)
            decision = resp.decision
            stats[decision] = stats.get(decision, 0) + 1

            if resp.rule_count > 0:
                hit_ids = [r.rule_id for r in resp.triggered_rules]
                print(f"  [{i+1:3d}] {msisdn} | {event_type:<8} | score={resp.final_score:3d} | "
                      f"{decision:<8} | hit={hit_ids}")
            else:
                print(f"  [{i+1:3d}] {msisdn} | {event_type:<8} | score={resp.final_score:3d} | "
                      f"{decision:<8} | no_hit")

        except Exception as e:
            stats["error"] += 1
            print(f"  [{i+1:3d}] {msisdn} | {event_type:<8} | ERROR: {e}")

        if (i + 1) % 20 == 0:
            await db.commit()

    await db.commit()
    await db.close()

    print("\n" + "=" * 60)
    print("[完成] 风控检查统计:")
    for k, v in stats.items():
        if v > 0:
            print(f"  {k}: {v}")
    total = sum(v for k, v in stats.items() if k != "error")
    print(f"  总计: {total} 次评估, {stats['error']} 次错误")


if __name__ == "__main__":
    asyncio.run(main())