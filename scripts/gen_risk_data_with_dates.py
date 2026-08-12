"""
物流风控系统 - 带日期范围的模拟风控评估数据生成 (异步)
支持指定"近 N 天"或"起止日期"造数据, 让仪表盘趋势图有跨天数据.
完全改写为物流业务表 (shipment/customs_declaration/complaint_record).

每天数据量规则 (优先级从高到低):
    1. --per-day 固定值       → 每天生成固定条数
    2. --max-per-day 仅指定   → 每天随机 1 ~ max-per-day 条
    3. 都不指定              → 每天随机 1 ~ 30 条 (默认)
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import text

from app.database import AsyncSessionLocal, async_engine
from app.schemas import RiskCheckRequest
from app.service.event import process_event

RISKY_USER_PREFIX = "RISK"


async def _pick_forced_complaint_record(db, balance_pos=True):
    """【force-pos alias】高风险: 投诉申诉 (对应原电商售后场景)."""
    return await _pick_complaint(db, balance_pos=balance_pos)


async def _pick_forced_logistics_complaint(db, balance_pos=True):
    """【force-pos alias】物流投诉 → 对应物流: 投诉申诉."""
    return await _pick_complaint(db, balance_pos=balance_pos)


async def _pick_forced_order_for_high_amount(db, balance_pos=True):
    """【force-pos alias】高额订单 → 对应物流: 大额运单寄件下单."""
    return await _pick_shipment(db, balance_pos=balance_pos)


async def _pick_order_for_balance(db):
    """【balance-pos alias】平衡正例: 订单 → 对应物流: 运单 (寄件下单)."""
    return await _pick_shipment(db, balance_pos=True)


async def _pick_complaint_for_balance(db):
    """【balance-pos alias】平衡正例: 投诉申诉 (对应原电商售后)."""
    return await _pick_complaint(db, balance_pos=True)


async def clean_risk_tables(db):
    for tbl in ("risk_case", "risk_assessment", "risk_feature", "risk_event", "risk_user_profile"):
        try:
            await db.execute(text(f"DELETE FROM {tbl}"))
        except Exception as e:
            print(f"  清空 {tbl} 失败 (可能表不存在): {e}")
    await db.commit()


async def _pick_shipment(db, balance_pos, prefer_cod=False):
    where_extra = ""
    params = {}
    if balance_pos and random.random() < 0.8:
        where_extra = " AND s.sender_user_id LIKE :prefix"
        params["prefix"] = f"{RISKY_USER_PREFIX}%"
    if prefer_cod:
        where_extra += " AND s.payment_method = '到付'"
    sql = f"""
        SELECT s.shipment_id, s.sender_user_id, s.receiver_address_id
        FROM shipment s WHERE 1=1 {where_extra}
        ORDER BY RAND() LIMIT 1
    """
    row = (await db.execute(text(sql), params)).first()
    return (row.shipment_id, row.sender_user_id, str(row.receiver_address_id)) if row else None


async def _pick_declaration(db, balance_pos):
    where_extra = ""
    params = {}
    if balance_pos and random.random() < 0.8:
        where_extra = " AND s.sender_user_id LIKE :prefix"
        params["prefix"] = f"{RISKY_USER_PREFIX}%"
    sql = f"""
        SELECT d.declaration_id, s.sender_user_id
        FROM customs_declaration d
        JOIN shipment s ON d.shipment_id = s.shipment_id
        WHERE 1=1 {where_extra}
        ORDER BY RAND() LIMIT 1
    """
    row = (await db.execute(text(sql), params)).first()
    return (row.declaration_id, row.sender_user_id) if row else None


async def _pick_complaint(db, balance_pos):
    where_extra = ""
    params = {}
    if balance_pos and random.random() < 0.8:
        where_extra = " AND cr.user_id LIKE :prefix"
        params["prefix"] = f"{RISKY_USER_PREFIX}%"
    sql = f"""
        SELECT cr.record_id, cr.user_id FROM complaint_record cr
        WHERE 1=1 {where_extra}
        ORDER BY RAND() LIMIT 1
    """
    row = (await db.execute(text(sql), params)).first()
    return (str(row.record_id), row.user_id) if row else None


async def backdate_record(db, table, time_col, id_val, target_time, id_col=None):
    id_col = id_col or (
        'event_id' if 'event' in table
        else 'assessment_id' if 'assess' in table
        else 'case_id' if 'case' in table
        else 'user_id'
    )
    await db.execute(
        text(f"UPDATE {table} SET {time_col} = :t WHERE {id_col} = :eid"),
        {"t": target_time, "eid": id_val},
    )


def _log_failure(target_time, request, e):
    print(f"  [FAIL][{target_time}] {request.event_type} user={request.user_id} "
          f"src={request.source_id}: {type(e).__name__}: {e}")


async def generate_risk_data_with_dates(
    days=7, per_day=None, max_per_day=30,
    start_date=None, end_date=None,
    clean=False, balance_pos=False, target_pos_ratio=None,
    live=False, force_pos_ratio=None,
):
    async with AsyncSessionLocal() as db:
        if clean:
            await clean_risk_tables(db)

        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        else:
            end_dt = datetime.now()
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
        else:
            start_dt = (end_dt - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0)

        daily_rule = f"每天固定 {per_day} 条" if per_day is not None else f"每天随机 1~{max_per_day} 条"
        if target_pos_ratio is not None and not balance_pos:
            print(f"⚠️  --target-pos-ratio 必须配合 --balance-pos, 自动启用 --balance-pos")
            balance_pos = True
        if balance_pos:
            print(f"⚠️  --balance-pos 模式: 80% 概率挑 RISK 高风险用户")
        if target_pos_ratio is not None:
            print(f"🎯 目标正例比例: {target_pos_ratio*100:.0f}%, 循环造数据直到达标 (最多 10 轮)")
        if live:
            print(f"📌 --live 模式: 不回写 create_time, 数据 create_time=now, 仪表盘'今日'能看到")
        if force_pos_ratio is not None:
            print(f"[FORCE-POS] --force-pos-ratio: 强制 {force_pos_ratio*100:.0f}% 走高风险事件路径")
        print(f"日期范围: {start_dt.date()} ~ {end_dt.date()}")
        print(f"每天数据量: {daily_rule}")

        total_days = (end_dt.date() - start_dt.date()).days + 1
        max_rounds = 10
        for round_idx in range(max_rounds):
            print(f"\n[第 {round_idx+1}/{max_rounds} 轮]")
            grand_success = 0
            grand_positive = 0
            for day_offset in range(total_days):
                current_date = start_dt.date() + timedelta(days=day_offset)
                day_count = per_day if per_day is not None else random.randint(1, max_per_day)
                print(f"[{current_date}] 生成 {day_count} 条评估...")
                day_success = 0
                day_positive = 0
                for i in range(day_count):
                    target_time = datetime.combine(current_date, datetime.min.time()).replace(
                        hour=random.randint(0, 23), minute=random.randint(0, 59),
                        second=random.randint(0, 59),
                    )
                    use_force_pos = force_pos_ratio is not None and random.random() < force_pos_ratio
                    max_tries = 3 if use_force_pos else 1
                    for try_idx in range(max_tries):
                        r = random.random()
                        if use_force_pos:
                            if try_idx == 0:
                                picked = await _pick_shipment(db, balance_pos=True)
                                if picked:
                                    sid, uid, rid = picked
                                    req = RiskCheckRequest(event_type="寄件下单", source_id=sid, user_id=uid,
                                                           order_id=sid, receive_id=rid)
                            elif try_idx == 1:
                                picked = await _pick_declaration(db, balance_pos=True)
                                if picked:
                                    did, uid = picked
                                    req = RiskCheckRequest(event_type="跨境申报", source_id=did, user_id=uid)
                            else:
                                picked = await _pick_complaint(db, balance_pos=True)
                                if picked:
                                    rid, uid = picked
                                    req = RiskCheckRequest(event_type="投诉申诉", source_id=rid, user_id=uid)
                            if not picked:
                                continue
                        elif r < 0.60:
                            picked = await _pick_shipment(db, balance_pos)
                            if not picked: continue
                            sid, uid, rid = picked
                            req = RiskCheckRequest(event_type="寄件下单", source_id=sid, user_id=uid,
                                                   order_id=sid, receive_id=rid)
                        elif r < 0.80:
                            picked = await _pick_shipment(db, balance_pos, prefer_cod=True)
                            if not picked:
                                picked = await _pick_shipment(db, balance_pos)
                            if not picked: continue
                            sid, uid, rid = picked
                            req = RiskCheckRequest(event_type="到付签收", source_id=sid, user_id=uid,
                                                   order_id=sid, receive_id=rid)
                        elif r < 0.92:
                            picked = await _pick_declaration(db, balance_pos)
                            if not picked: continue
                            did, uid = picked
                            req = RiskCheckRequest(event_type="跨境申报", source_id=did, user_id=uid)
                        else:
                            picked = await _pick_complaint(db, balance_pos)
                            if not picked: continue
                            rid, uid = picked
                            req = RiskCheckRequest(event_type="投诉申诉", source_id=rid, user_id=uid)

                        try:
                            result = await process_event(db, req)
                            backdate_target = None if live else target_time
                            new_event = (await db.execute(text(
                                "SELECT event_id FROM risk_event WHERE user_id=:uid ORDER BY create_time DESC LIMIT 1"
                            ), {"uid": req.user_id})).first()
                            new_assess = (await db.execute(text(
                                "SELECT assessment_id, decision FROM risk_assessment WHERE user_id=:uid ORDER BY create_time DESC LIMIT 1"
                            ), {"uid": req.user_id})).first()
                            if new_event and backdate_target is not None:
                                await backdate_record(db, "risk_event", "create_time", new_event.event_id, backdate_target)
                                await db.execute(text(
                                    "UPDATE risk_feature SET compute_time = :t WHERE event_id = :eid"
                                ), {"t": backdate_target, "eid": new_event.event_id})
                            if new_assess:
                                if backdate_target is not None:
                                    await backdate_record(db, "risk_assessment", "create_time", new_assess.assessment_id, backdate_target)
                                    await db.execute(text(
                                        "UPDATE risk_case SET create_time = :t WHERE assessment_id = :aid"
                                    ), {"t": backdate_target, "aid": new_assess.assessment_id})
                                if new_assess.decision in ("拒绝", "人工审核"):
                                    day_positive += 1
                                    grand_positive += 1
                            await db.execute(text(
                                "UPDATE risk_user_profile SET last_assessment_time=:t, update_time=:t WHERE user_id=:uid"
                            ), {"t": backdate_target or datetime.now(), "uid": req.user_id})
                            await db.commit()
                            day_success += 1
                            grand_success += 1
                            break
                        except Exception as e:
                            await db.rollback()
                            _log_failure(target_time, req, e)
                            break

                ratio = day_positive / max(day_success, 1) * 100
                print(f"  -> 成功 {day_success}, 正例 {day_positive} ({ratio:.1f}%)")

            overall_ratio = grand_positive / max(grand_success, 1)
            print(f"[第 {round_idx+1} 轮汇总] 成功 {grand_success} 条, 正例 {grand_positive} 条 ({overall_ratio*100:.1f}%)")
            no_target_set = (target_pos_ratio is None)
            if no_target_set:
                break
            if overall_ratio >= target_pos_ratio:
                print(f"✅ 正例比例 {overall_ratio*100:.1f}% >= 目标 {target_pos_ratio*100:.0f}%, 达标!")
                break
            elif round_idx < max_rounds - 1:
                print(f"⚠️  未达标, 继续下一轮...")
                continue
            else:
                print(f"❌ 跑完 {max_rounds} 轮仍未达标, 最后 {overall_ratio*100:.1f}%")

    print(f"\n完成! 最后一轮: 成功 {grand_success} 条, 正例 {grand_positive} 条")


async def _runner():
    try:
        await generate_risk_data_with_dates(
            days=args.days, per_day=args.per_day, max_per_day=args.max_per_day,
            start_date=args.start, end_date=args.end,
            clean=args.clean, balance_pos=args.balance_pos,
            target_pos_ratio=args.target_pos_ratio, live=args.live,
            force_pos_ratio=args.force_pos_ratio,
        )
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="物流风控带日期的评估数据生成")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--per-day", type=int, default=None)
    parser.add_argument("--max-per-day", type=int, default=30)
    parser.add_argument("--start", type=str, default=None)
    parser.add_argument("--end", type=str, default=None)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--balance-pos", action="store_true")
    parser.add_argument("--target-pos-ratio", type=float, default=None)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--force-pos-ratio", type=float, default=None)
    args = parser.parse_args()
    asyncio.run(_runner())
