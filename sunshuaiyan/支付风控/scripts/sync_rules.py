from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import SessionLocal, engine  # noqa: E402
from models import Base, RiskRule  # noqa: E402


def main() -> None:
    Base.metadata.tables["risk_rules"].create(engine, checkfirst=True)
    rules = json.loads((ROOT / "rules" / "pingpong_rules.json").read_text(encoding="utf-8"))
    with SessionLocal() as db:
        existing = {row.rule_id: row for row in db.scalars(select(RiskRule)).all()}
        for priority, item in enumerate(reversed(rules), 1):
            row = existing.get(item["id"])
            values = {
                "rule_name": item["name"], "stage": item["stage"], "category": item["category"],
                "fraud_scenario": item["fraud_scenario"], "rule_condition": item["condition"],
                "severity": item["severity"], "risk_score": item["score"], "action": item["action"],
                "is_veto": item["veto"], "priority": priority, "is_enabled": True, "version": 1,
                "source_refs": ["PingPong Open Platform", "FATF TBML", "FinCEN BEC", "FCA Money Mules", "OFAC"],
                "effective_from": datetime(2026, 8, 11, 8, 0, 0),
            }
            if row is None:
                db.add(RiskRule(rule_id=item["id"], **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)
        db.commit()
        count = db.query(RiskRule).count()
    print(f"risk_rules synced: {count}")


if __name__ == "__main__":
    main()
