"""Create MySQL database/tables, generate CSV data, import it, and seed rules."""

from __future__ import annotations

import argparse
import asyncio
import secrets
from pathlib import Path

from app.database import engine
from scripts.create_database import create_database
from scripts.gen_paypal_business_data import CsvDatasetWriter, GeneratorConfig, PayPalLikeGenerator
from scripts.load_simulated_data import load_dataset
from scripts.seed_operational_rules import seed_rules


async def initialize(
    output: Path, config: GeneratorConfig, replace: bool
) -> None:
    try:
        await create_database()
        if not output.exists():
            generator = PayPalLikeGenerator(config)
            generator.generate(CsvDatasetWriter(output))
        counts = await load_dataset(output, replace=replace)
        rule_count = await seed_rules()
        print(f"Demo ready: imported={sum(counts.values()):,}, new_rules={rule_count}")
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("generated/paypal_dev"))
    parser.add_argument("--users", type=int, default=100)
    parser.add_argument("--transactions", type=int, default=1_000)
    parser.add_argument("--merchants", type=int)
    parser.add_argument("--interactions", type=int)
    parser.add_argument("--segments", type=int)
    parser.add_argument("--messages", type=int)
    parser.add_argument("--risk-ratio", type=float, default=0.12)
    parser.add_argument("--email-ratio", type=float, default=0.20)
    parser.add_argument("--attachment-ratio", type=float, default=0.15)
    seeds = parser.add_mutually_exclusive_group()
    seeds.add_argument("--seed", type=int, default=20260811)
    seeds.add_argument("--random-seed", action="store_true")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    if args.replace and not args.yes:
        raise SystemExit("--replace deletes existing business rows; add --yes to confirm")
    seed = secrets.randbits(63) if args.random_seed else args.seed
    config = GeneratorConfig(users=args.users, transactions=args.transactions, seed=seed, risk_ratio=args.risk_ratio, merchants=args.merchants, interactions=args.interactions, segments=args.segments, messages=args.messages, email_ratio=args.email_ratio, attachment_ratio=args.attachment_ratio)
    asyncio.run(initialize(args.output, config, args.replace))
    print(f"Seed: {seed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
