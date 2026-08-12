from __future__ import annotations

import os
import re

from sqlalchemy import create_engine, text

from app import models  # noqa: F401 - imports models into Base.metadata
from app.database import Base, build_database_url, engine


SAFE_DATABASE_NAME = re.compile(r"^[A-Za-z0-9_]+$")


def ensure_database() -> str:
    database_name = os.getenv("MYSQL_DATABASE", "risk_proj")
    if not SAFE_DATABASE_NAME.fullmatch(database_name):
        raise ValueError("MYSQL_DATABASE may contain only letters, numbers, and underscores")

    server_engine = create_engine(build_database_url(include_database=False))
    with server_engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS `{database_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            )
        )
    server_engine.dispose()
    return database_name


def main() -> None:
    database_name = ensure_database()
    Base.metadata.create_all(bind=engine)
    print(f"Initialized {database_name} with {len(Base.metadata.tables)} tables.")


if __name__ == "__main__":
    main()

