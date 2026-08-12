from __future__ import annotations

from app.database import SessionLocal
from app.risk_engine import recalculate_all_assessments


def main() -> None:
    with SessionLocal.begin() as session:
        result = recalculate_all_assessments(
            session,
            operator="system_reviewer",
            trigger="manual_script",
        )
    print(f"Recalculated {result.total_orders} assessments.")
    print(f"Changed assessments: {result.changed_assessments}")
    print(f"Generated hits: {result.generated_hits}")
    print(f"Created review cases: {result.created_review_cases}")
    print(f"Cancelled review cases: {result.cancelled_review_cases}")
    print(f"Reopened review cases: {result.reopened_review_cases}")
    print(f"Decision distribution: {result.decisions}")


if __name__ == "__main__":
    main()
