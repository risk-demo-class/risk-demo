from __future__ import annotations

from sqlalchemy import inspect, text

from app.database import engine


TABLE_NAME = "risk_assessment"


def main() -> None:
    inspector = inspect(engine)
    existing_columns = {
        column["name"] for column in inspector.get_columns(TABLE_NAME)
    }
    column_definitions = {
        "model_probability": "DECIMAL(9,8) NULL AFTER raw_score",
        "model_score": "TINYINT UNSIGNED NULL AFTER model_probability",
        "model_version": "VARCHAR(100) NULL AFTER model_score",
    }

    added: list[str] = []
    with engine.begin() as connection:
        for name, definition in column_definitions.items():
            if name in existing_columns:
                continue
            connection.execute(
                text(f"ALTER TABLE {TABLE_NAME} ADD COLUMN {name} {definition}")
            )
            added.append(name)

    print(
        "Model scoring fields ready; "
        + (f"added: {', '.join(added)}" if added else "all fields already existed")
        + "."
    )


if __name__ == "__main__":
    main()
