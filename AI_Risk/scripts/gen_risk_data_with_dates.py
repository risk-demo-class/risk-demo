"""Generate risk assessment data with date ranges - Bank Risk version. v2 clean."""
import argparse, asyncio, os, random, sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.schemas import RiskCheckRequest
from app.service.event import process_event

RISKY_USER_PREFIX = "RISK"
BANK_EVENT_TYPES = ["转账/支付", "转账/支付", "转账/支付", "转账/支付", "转账/支付", "贷款申请"]
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
FAIL_LOG = os.path.join(LOG_DIR, "gen_risk_fail.log")
os.makedirs(LOG_DIR, exist_ok=True)


def _log_fail(error, request, target_time=None):
    entry = {
        "target_time": target_time.isoformat() if target_time else None,
        "user_id": getattr(request, "user_id", None),
        "event_type": getattr(request, "event_type", None),
        "source_id": getattr(request, "source_id", None),
        "error": str(error)[:500],
    }
    try:
        with open(FAIL_LOG, "a", encoding="utf-8") as f:
            f.write(str(entry) + "\n")
    except Exception:
        pass


async def _clean(db):
    for tbl in ["risk_assessment", "risk_feature", "risk_event", "risk_case", "risk_user_profile"]:
        try:
            await db.execute(text(f"DELETE FROM {tbl}"))
        except Exception:
            pass
    await db.commit()


async def _pick_user_data(db, balance_pos=False):
    """从 user_info JOIN transaction 取有效用户. 返回 (user_id, txn_id)."""
    if balance_pos:
        row = (await db.execute(text(
            "SELECT u.user_id, t.txn_id FROM user_info u "
            "INNER JOIN transaction t ON u.user_id = t.user_id "
            "WHERE u.user_id LIKE :pfx ORDER BY RAND() LIMIT 1"
        ), {"pfx": f"{RISKY_USER_PREFIX}%"})).first()
    else:
        row = (await db.execute(text(
            "SELECT u.user_id, t.txn_id FROM user_info u "
            "INNER JOIN transaction t ON u.user_id = t.user_id "
            "ORDER BY RAND() LIMIT 1"
        ))).first()
    return (row.user_id, row.txn_id) if row else None


async def _pick_suspicious(db, balance_pos=False):
    """从 user_info JOIN txn_suspicious_report. 返回 (user_id, report_id)."""
    if balance_pos:
        row = (await db.execute(text(
            "SELECT u.user_id, sr.report_id FROM user_info u "
            "INNER JOIN txn_suspicious_report sr ON u.user_id = sr.user_id "
            "WHERE u.user_id LIKE :pfx ORDER BY RAND() LIMIT 1"
        ), {"pfx": f"{RISKY_USER_PREFIX}%"})).first()
    else:
        row = (await db.execute(text(
            "SELECT u.user_id, sr.report_id FROM user_info u "
            "INNER JOIN txn_suspicious_report sr ON u.user_id = sr.user_id "
            "ORDER BY RAND() LIMIT 1"
        ))).first()
    return (row.user_id, str(row.report_id)) if row else None


async def _pick_fraud(db, balance_pos=False):
    """从 user_info JOIN fraud_case_record. 返回 (user_id, fraud_case_id)."""
    if balance_pos:
        row = (await db.execute(text(
            "SELECT u.user_id, fr.fraud_case_id FROM user_info u "
            "INNER JOIN fraud_case_record fr ON u.user_id = fr.user_id "
            "WHERE u.user_id LIKE :pfx ORDER BY RAND() LIMIT 1"
        ), {"pfx": f"{RISKY_USER_PREFIX}%"})).first()
    else:
        row = (await db.execute(text(
            "SELECT u.user_id, fr.fraud_case_id FROM user_info u "
            "INNER JOIN fraud_case_record fr ON u.user_id = fr.user_id "
            "ORDER BY RAND() LIMIT 1"
        ))).first()
    return (row.user_id, str(row.fraud_case_id)) if row else None


PICKERS = [
    ("txn", _pick_user_data),
    ("txn", _pick_user_data),
    ("txn", _pick_user_data),
    ("txn", _pick_user_data),
    ("txn", _pick_user_data),
    ("txn", _pick_user_data),
]


async def gen_risk_data(days=7, per_day=None, max_per_day=None, start=None, end=None,
                        balance_pos=False, clean=False):
    if start and end:
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        date_range = [(start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
                       for i in range((end_dt - start_dt).days + 1)]
    else:
        date_range = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                       for i in range(days - 1, -1, -1)]

    async with AsyncSessionLocal() as db:
        if clean:
            print("[clean] Deleting old risk data...")
            await _clean(db)

        total_req = 0
        total_ok = 0
        total_decisions = {}

        for date_str in date_range:
            if per_day:
                n = per_day
            elif max_per_day:
                n = random.randint(1, max_per_day)
            else:
                n = random.randint(1, 30)

            print(f"\n[date: {date_str}] generating {n} records...")

            for i in range(n):
                idx = i % len(PICKERS)
                ptype, picker = PICKERS[idx]
                et = BANK_EVENT_TYPES[idx]

                picked = await picker(db, balance_pos=balance_pos)
                if not picked:
                    continue

                user_id, source_id = picked
                request = RiskCheckRequest(
                    event_type=et,
                    source_id=source_id,
                    user_id=user_id,
                    order_id=source_id if "转账" in et else None,
                )

                total_req += 1
                try:
                    resp = await process_event(db, request)
                    await db.commit()
                    total_ok += 1
                    decision = resp.decision if hasattr(resp, "decision") else "通过"
                    total_decisions[decision] = total_decisions.get(decision, 0) + 1
                except Exception as e:
                    _log_fail(e, request)
                    await db.rollback()

        print(f"\n{'='*60}")
        print(f"Summary: {total_ok}/{total_req} succeeded")
        print(f"  Decisions: {total_decisions}")
        print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate risk data — Bank Risk v2.")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--per-day", type=int, default=None)
    parser.add_argument("--max-per-day", type=int, default=None)
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--balance-pos", action="store_true")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    asyncio.run(gen_risk_data(
        days=args.days, per_day=args.per_day, max_per_day=args.max_per_day,
        start=args.start, end=args.end, balance_pos=args.balance_pos, clean=args.clean,
    ))
