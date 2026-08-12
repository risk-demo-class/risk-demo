from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import SessionLocal, engine
from app.schemas import BlacklistCreate
from app.services.blacklist import upsert_blacklist
from models import BankAccount, Counterparty, Customer, Device, RiskBlacklist, VirtualAccount


def main() -> None:
    RiskBlacklist.__table__.create(bind=engine, checkfirst=True)
    with SessionLocal() as db:
        counterparties = db.scalars(
            select(Counterparty).order_by(Counterparty.risk_score.desc()).limit(5)
        ).all()
        customers = db.scalars(
            select(Customer)
            .where(Customer.kyc_status == "APPROVED")
            .order_by(Customer.risk_tier.desc(), Customer.id)
            .limit(3)
        ).all()
        virtual_accounts = db.scalars(
            select(VirtualAccount).order_by(VirtualAccount.risk_tier.desc(), VirtualAccount.id).limit(3)
        ).all()
        devices = db.scalars(select(Device).order_by(Device.risk_score.desc()).limit(3)).all()

        entries: list[BlacklistCreate] = []
        for cp in counterparties:
            entries.append(
                BlacklistCreate(
                    entity_type="COUNTERPARTY",
                    entity_value=cp.counterparty_ref,
                    display_name=cp.legal_name,
                    reason_code="MULE_OR_FRAUD_SIGNAL",
                    reason_detail="Synthetic high-risk payer for blacklist workflow testing.",
                    severity="CRITICAL",
                    source="CASE",
                    source_refs=["synthetic-case"],
                    created_by="sync-blacklist",
                )
            )
            bank = db.scalar(
                select(BankAccount).where(BankAccount.counterparty_id == cp.id).limit(1)
            )
            if bank and len([item for item in entries if item.entity_type == "BANK_ACCOUNT"]) < 3:
                entries.append(
                    BlacklistCreate(
                        entity_type="BANK_ACCOUNT",
                        entity_value=bank.account_ref,
                        display_name=bank.holder_name,
                        reason_code="HIGH_RISK_BENEFICIARY",
                        reason_detail="Synthetic beneficiary account linked to a high-risk counterparty.",
                        severity="CRITICAL",
                        source="SCREENING",
                        source_refs=["synthetic-screening"],
                        created_by="sync-blacklist",
                    )
                )
        for customer in customers:
            entries.append(
                BlacklistCreate(
                    entity_type="CUSTOMER",
                    entity_value=customer.client_id,
                    display_name=customer.legal_name,
                    reason_code="CASE_CONFIRMED_RISK",
                    reason_detail="Synthetic customer case outcome.",
                    severity="HIGH",
                    source="CASE",
                    source_refs=["synthetic-case"],
                    created_by="sync-blacklist",
                )
            )
        for va in virtual_accounts:
            entries.append(
                BlacklistCreate(
                    entity_type="VIRTUAL_ACCOUNT",
                    entity_value=va.va_id,
                    display_name=va.account_holder_name,
                    reason_code="VA_MISUSE_SIGNAL",
                    reason_detail="Synthetic virtual account misuse signal.",
                    severity="HIGH",
                    source="CASE",
                    source_refs=["synthetic-case"],
                    created_by="sync-blacklist",
                )
            )
        for device in devices:
            entries.append(
                BlacklistCreate(
                    entity_type="DEVICE",
                    entity_value=device.device_id,
                    display_name=device.device_type,
                    reason_code="DEVICE_FRAUD_CLUSTER",
                    reason_detail="Synthetic shared-device fraud cluster.",
                    severity="HIGH",
                    source="SCREENING",
                    source_refs=["synthetic-screening"],
                    created_by="sync-blacklist",
                )
            )

        for entry in entries:
            upsert_blacklist(db, entry)
        total = db.query(RiskBlacklist).count()
    print(f"risk_blacklist synced: {total}")


if __name__ == "__main__":
    main()
