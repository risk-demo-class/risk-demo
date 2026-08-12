from __future__ import annotations

from sqlalchemy import inspect, select, text

from app.database import SessionLocal, engine
from app.models import StaffUserRole


CONSTRAINT_NAME = "uq_staff_user_role_staff_user_id"


def main() -> None:
    removed = 0
    with SessionLocal() as db:
        assignments = list(
            db.scalars(
                select(StaffUserRole).order_by(
                    StaffUserRole.staff_user_id,
                    StaffUserRole.assigned_at,
                    StaffUserRole.role_id,
                )
            )
        )
        seen_users: set[int] = set()
        for assignment in assignments:
            if assignment.staff_user_id in seen_users:
                db.delete(assignment)
                removed += 1
            else:
                seen_users.add(assignment.staff_user_id)
        db.commit()

    schema = inspect(engine)
    unique_names = {
        item.get("name") for item in schema.get_unique_constraints("staff_user_role")
    }
    unique_names.update(
        item.get("name")
        for item in schema.get_indexes("staff_user_role")
        if item.get("unique")
    )
    created = CONSTRAINT_NAME not in unique_names
    if created:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE staff_user_role "
                    f"ADD CONSTRAINT {CONSTRAINT_NAME} UNIQUE (staff_user_id)"
                )
            )

    print(
        f"Single-role constraint ready; removed {removed} duplicate assignment(s); "
        f"constraint {'created' if created else 'already existed'}."
    )


if __name__ == "__main__":
    main()
