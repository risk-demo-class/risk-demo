"""Load generated 40-table CSV data into the configured PP_Risk database."""

from __future__ import annotations

import argparse
import asyncio
import csv
from collections.abc import Iterator, Sequence
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import Boolean, DateTime, Numeric, delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, create_schema
from app.models_business import BUSINESS_MODELS


def _convert(column: Any, value: str) -> Any:
    if value == "":
        return None
    if isinstance(column.type, Boolean):
        return value.lower() in {"1", "true", "yes"}
    if isinstance(column.type, Numeric):
        return Decimal(value)
    if isinstance(column.type, DateTime):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def read_rows(path: Path, table: Any) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            yield {column.name: _convert(column, raw.get(column.name, "")) for column in table.columns}


async def _insert_batches(
    db: AsyncSession, table: Any, rows: Iterator[dict[str, Any]], batch_size: int
) -> int:
    batch: list[dict[str, Any]] = []
    total = 0
    for row in rows:
        batch.append(row)
        if len(batch) >= batch_size:
            await db.execute(insert(table), batch)
            total += len(batch)
            batch.clear()
    if batch:
        await db.execute(insert(table), batch)
        total += len(batch)
    return total


async def load_dataset(
    source: Path,
    *,
    replace: bool = False,
    batch_size: int = 1_000,
) -> dict[str, int]:
    source = source.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"dataset directory does not exist: {source}")
    missing = [name for name in BUSINESS_MODELS if not (source / f"{name}.csv").is_file()]
    if missing:
        raise ValueError(f"dataset is missing {len(missing)} table files: {', '.join(missing[:5])}")

    await create_schema()
    counts: dict[str, int] = {}
    async with AsyncSessionLocal() as db:
        if replace:
            for model in reversed(tuple(BUSINESS_MODELS.values())):
                await db.execute(delete(model))
            await db.commit()

        for table_name, model in BUSINESS_MODELS.items():
            existing = await db.scalar(select(func.count()).select_from(model)) or 0
            if existing:
                counts[table_name] = 0
                continue
            table = model.__table__
            count = await _insert_batches(
                db,
                table,
                read_rows(source / f"{table_name}.csv", table),
                batch_size,
            )
            await db.commit()
            counts[table_name] = count
            print(f"[{table_name:<32}] {count:>10,} rows")
    return counts


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("generated/paypal_dev"))
    parser.add_argument("--batch-size", type=int, default=1_000)
    parser.add_argument("--replace", action="store_true", help="delete existing business rows before import")
    parser.add_argument("--yes", action="store_true", help="confirm destructive --replace operation")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.replace and not args.yes:
        raise SystemExit("--replace deletes all 40 business tables; add --yes to confirm")
    counts = asyncio.run(
        load_dataset(args.source, replace=args.replace, batch_size=args.batch_size)
    )
    print(f"Imported {sum(counts.values()):,} rows across {len(counts)} tables")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

