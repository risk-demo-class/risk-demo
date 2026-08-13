"""可复现的银行业务数据与八类风险场景生成器。

生成器只写 8 张银行业务表；风险事件、特征和评估必须由后续回放脚本调用
真实 ``process_event`` 产生。这样训练数据与线上决策共用同一条代码路径。
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EventType
from app.models_business import (
    AccountStatus,
    AccountType,
    BankAccount,
    BankCard,
    BankTransaction,
    CardStatus,
    CardType,
    CustomerInfo,
    CustomerStatus,
    DeviceFingerprint,
    IpGeoLocation,
    KycLevel,
    LoanApplication,
    LoanStatus,
    LoginLog,
    TransactionChannel,
    TransactionStatus,
    TransactionType,
)


PATTERN_LABELS: dict[str, str] = {
    "cross_city_large_transfer": "异地大额转账用户",
    "night_dense_operation": "凌晨密集操作用户",
    "new_device_large_transfer": "新设备大额转账用户",
    "multi_account_convergence": "多账户向单一收款账户归集",
    "multi_lender_loan": "多头借贷用户",
    "shared_device": "同一设备关联多人",
    "proxy_or_tor_login": "代理/Tor IP 登录用户",
    "normal_control": "正常对照用户",
}
RISK_PATTERNS = tuple(name for name in PATTERN_LABELS if name != "normal_control")


@dataclass(frozen=True, slots=True)
class GenerationConfig:
    users: int = 1000
    transactions: int = 20_000
    loans: int = 500
    logins_per_user_min: int = 5
    logins_per_user_max: int = 30
    candidate_count: int = 2000
    risk_ratio: float = 0.28
    days: int = 90
    seed: int = 20260813
    prefix: str = "BG"
    end_time: str = "2026-08-12T23:59:00"

    def validate(self) -> None:
        if self.users < 10:
            raise ValueError("users 至少为 10，才能构造多人共用设备和多账户归集")
        if self.transactions < 0 or self.loans < 0 or self.candidate_count < 1:
            raise ValueError("transactions/loans 不能为负，candidate_count 必须大于 0")
        if not 0.0 <= self.risk_ratio <= 1.0:
            raise ValueError("risk_ratio 必须在 0 到 1 之间")
        if not 1 <= self.logins_per_user_min <= self.logins_per_user_max:
            raise ValueError("登录数量范围不合法")
        if self.days < 7:
            raise ValueError("days 至少为 7，才能生成时间窗口历史")
        if not self.prefix.isalnum() or len(self.prefix) > 8:
            raise ValueError("prefix 只能由字母数字组成且最长 8 位")
        try:
            datetime.fromisoformat(self.end_time)
        except ValueError as exc:
            raise ValueError("end_time 必须是 ISO 日期时间，例如 2026-08-12T23:59:00") from exc


@dataclass(frozen=True, slots=True)
class RiskCandidate:
    event_type: str
    source_id: str
    user_id: str
    event_time: str
    pattern: str

    def request_data(self) -> dict[str, object]:
        return {
            "event_type": self.event_type,
            "source_id": self.source_id,
            "user_id": self.user_id,
            "event_data": {
                "generation_pattern": self.pattern,
                "generation_pattern_label": PATTERN_LABELS[self.pattern],
            },
        }


@dataclass(frozen=True, slots=True)
class GenerationSummary:
    customers: int
    accounts: int
    cards: int
    devices: int
    ip_records: int
    transactions: int
    logins: int
    loans: int
    candidates: int
    risk_candidates: int
    seed: int
    prefix: str


def demo_hash(value: str) -> str:
    """仅用于虚构教学数据；输入本身也不包含真实身份信息。"""

    return hashlib.sha256(f"bank-risk-batch::{value}".encode("utf-8")).hexdigest()


def save_manifest(
    path: Path,
    *,
    config: GenerationConfig,
    summary: GenerationSummary,
    candidates: list[RiskCandidate],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": datetime.now(UTC).isoformat(),
                "config": asdict(config),
                "summary": asdict(summary),
                "candidates": [asdict(item) for item in candidates],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def load_manifest(path: Path) -> list[RiskCandidate]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [RiskCandidate(**item) for item in payload["candidates"]]


def pattern_distribution(candidates: list[RiskCandidate]) -> dict[str, int]:
    result = {name: 0 for name in PATTERN_LABELS}
    for item in candidates:
        result[item.pattern] = result.get(item.pattern, 0) + 1
    return result


def _event_times(config: GenerationConfig, count: int) -> list[datetime]:
    end = datetime.fromisoformat(config.end_time)
    start = end - timedelta(days=config.days)
    span_seconds = max(int((end - start).total_seconds()), 1)
    return [start + timedelta(seconds=int(span_seconds * (index + 1) / (count + 1))) for index in range(count)]


async def _add_in_batches(db: AsyncSession, rows: list[object], batch_size: int = 1000) -> None:
    for start in range(0, len(rows), batch_size):
        db.add_all(rows[start : start + batch_size])
        await db.flush()


async def _assert_prefix_is_unused(db: AsyncSession, prefix: str) -> None:
    count = int(
        (
            await db.execute(
                select(func.count(CustomerInfo.user_id)).where(
                    CustomerInfo.user_id.like(f"{prefix}U%")
                )
            )
        ).scalar_one()
        or 0
    )
    if count:
        raise RuntimeError(
            f"前缀 {prefix!r} 的批量数据已存在（{count} 个客户）。"
            "为防误删，本脚本不会自动覆盖；请更换 --prefix，或明确重置教学数据库。"
        )


async def generate_bank_data(
    db: AsyncSession,
    config: GenerationConfig,
) -> tuple[GenerationSummary, list[RiskCandidate]]:
    """向业务表写入固定种子的批量数据，返回供真实决策回放的候选事件。"""

    config.validate()
    await _assert_prefix_is_unused(db, config.prefix)
    rng = random.Random(config.seed)
    cities = ("北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "西安", "南京")
    times = _event_times(config, config.candidate_count)
    start_time = times[0] - timedelta(days=2)

    normal_ip = f"198.51.100.{(config.seed % 200) + 1}"
    proxy_ip = f"203.0.113.{(config.seed % 200) + 1}"
    tor_ip = f"203.0.113.{(config.seed % 200) + 2}"
    ip_rows: list[object] = [
        IpGeoLocation(ip=normal_ip, country="中国", province="北京", city="北京", isp="教学网络",
                      is_proxy=False, is_tor=False, risk_score=3, updated_at=start_time),
        IpGeoLocation(ip=proxy_ip, country="中国", province="上海", city="上海", isp="教学代理网络",
                      is_proxy=True, is_tor=False, risk_score=85, updated_at=start_time),
        IpGeoLocation(ip=tor_ip, country="未知", province="未知", city="未知", isp="教学Tor网络",
                      is_proxy=False, is_tor=True, risk_score=95, updated_at=start_time),
    ]
    await _add_in_batches(db, ip_rows)

    customer_rows: list[object] = []
    user_ids: list[str] = []
    home_cities: dict[str, str] = {}
    for index in range(config.users):
        user_id = f"{config.prefix}U{index + 1:06d}"
        city = cities[index % len(cities)]
        user_ids.append(user_id)
        home_cities[user_id] = city
        customer_rows.append(
            CustomerInfo(
                user_id=user_id,
                name_hash=demo_hash(f"{user_id}:name"),
                id_card_hash=demo_hash(f"{user_id}:id-card"),
                mobile_hash=demo_hash(f"{user_id}:mobile"),
                credit_score=rng.randint(650, 820),
                kyc_level=KycLevel.L2 if index % 4 else KycLevel.L3,
                monthly_income=Decimal(str(rng.randint(8_000, 45_000))),
                home_city=city,
                register_at=start_time - timedelta(days=rng.randint(180, 2200)),
                status=CustomerStatus.NORMAL,
            )
        )
    await _add_in_batches(db, customer_rows)

    account_rows: list[object] = []
    card_rows: list[object] = []
    device_rows: list[object] = []
    first_account: dict[str, str] = {}
    first_card: dict[str, str] = {}
    old_device: dict[str, str] = {}
    for user_index, user_id in enumerate(user_ids):
        account_count = rng.randint(1, 3)
        card_count = rng.randint(1, 3)
        for item_index in range(account_count):
            account_id = f"{config.prefix}A{user_index + 1:06d}{item_index + 1}"
            first_account.setdefault(user_id, account_id)
            account_rows.append(
                BankAccount(
                    account_id=account_id, user_id=user_id,
                    account_no_hash=demo_hash(f"{account_id}:number"),
                    account_type=AccountType.SAVING if item_index == 0 else AccountType.CURRENT,
                    balance=Decimal(str(rng.randint(50_000, 800_000))),
                    available_balance=Decimal(str(rng.randint(30_000, 500_000))),
                    home_branch=f"{home_cities[user_id]}教学支行",
                    open_at=start_time - timedelta(days=rng.randint(120, 1800)),
                    status=AccountStatus.NORMAL,
                )
            )
        for item_index in range(card_count):
            card_id = f"{config.prefix}C{user_index + 1:06d}{item_index + 1}"
            first_card.setdefault(user_id, card_id)
            credit_limit = rng.randint(20_000, 120_000)
            card_rows.append(
                BankCard(
                    card_id=card_id, user_id=user_id, account_id=first_account[user_id],
                    card_no_hash=demo_hash(f"{card_id}:number"), card_type=CardType.CREDIT,
                    credit_limit=Decimal(str(credit_limit)),
                    available_limit=Decimal(str(int(credit_limit * rng.uniform(0.3, 0.95)))),
                    issue_at=start_time - timedelta(days=rng.randint(90, 1200)),
                    status=CardStatus.NORMAL,
                )
            )
        device_id = f"{config.prefix}D{user_index + 1:06d}"
        old_device[user_id] = device_id
        device_rows.append(
            DeviceFingerprint(
                device_id=device_id, user_id=user_id,
                fingerprint_hash=demo_hash(f"{device_id}:fingerprint"),
                first_seen=start_time - timedelta(days=120),
                last_seen=times[-1], os="Android", browser="银行APP",
                is_rooted=False, is_emulator=False,
            )
        )
    await _add_in_batches(db, account_rows)
    await _add_in_batches(db, card_rows)
    await _add_in_batches(db, device_rows)

    transaction_rows: list[object] = []
    login_rows: list[object] = []
    loan_rows: list[object] = []

    # 普通历史必须先于当前候选事件。它们用于形成个人均值、时间窗口和登录轨迹。
    for user_index, user_id in enumerate(user_ids):
        count = rng.randint(config.logins_per_user_min, config.logins_per_user_max)
        for item_index in range(count):
            login_at = start_time + timedelta(days=rng.random() * max(config.days - 2, 1))
            login_rows.append(
                LoginLog(
                    login_id=f"{config.prefix}HLOG{user_index + 1:06d}{item_index + 1:02d}",
                    user_id=user_id, device_id=old_device[user_id], ip=normal_ip,
                    geo=home_cities[user_id], success=True, fail_reason=None, login_at=login_at,
                )
            )

    base_transaction_count = max(config.transactions - config.candidate_count, 0)
    for index in range(base_transaction_count):
        user_id = user_ids[index % len(user_ids)]
        txn_time = start_time + timedelta(seconds=rng.randint(0, config.days * 24 * 3600 - 1))
        transaction_rows.append(
            BankTransaction(
                txn_id=f"{config.prefix}HT{index + 1:08d}", user_id=user_id,
                from_account_id=first_account[user_id], from_card_id=None,
                beneficiary_account_hash=demo_hash(f"normal-beneficiary-{index % 300}"),
                amount=Decimal(str(rng.randint(20, 5000))), currency="CNY",
                txn_type=TransactionType.TRANSFER,
                channel=rng.choice(list(TransactionChannel)), device_id=old_device[user_id],
                ip=normal_ip, geo=home_cities[user_id], txn_time=txn_time,
                status=TransactionStatus.SUCCESS,
            )
        )

    for index in range(config.loans):
        user_id = user_ids[index % len(user_ids)]
        apply_at = start_time + timedelta(seconds=rng.randint(0, config.days * 24 * 3600 - 1))
        loan_rows.append(
            LoanApplication(
                loan_id=f"{config.prefix}HLN{index + 1:07d}", user_id=user_id,
                institution_code=f"DEMO_BANK_{index % 8 + 1}", amount=Decimal(str(rng.randint(5_000, 80_000))),
                term_months=rng.choice((6, 12, 24, 36)), purpose="教学消费贷",
                monthly_income=Decimal("20000"), debt_ratio=Decimal("0.30"),
                device_id=old_device[user_id], ip=normal_ip, apply_at=apply_at,
                status=LoanStatus.APPROVED,
            )
        )

    risk_count = round(config.candidate_count * config.risk_ratio)
    patterns = [RISK_PATTERNS[index % len(RISK_PATTERNS)] for index in range(risk_count)]
    patterns.extend(["normal_control"] * (config.candidate_count - risk_count))
    rng.shuffle(patterns)
    candidates: list[RiskCandidate] = []

    for index, (event_time, pattern) in enumerate(zip(times, patterns, strict=True)):
        user_id = user_ids[index % len(user_ids)]
        source_id: str
        event_type: EventType
        suffix = f"{index + 1:07d}"

        if pattern in {
            "cross_city_large_transfer", "night_dense_operation",
            "new_device_large_transfer", "multi_account_convergence",
        }:
            event_type = EventType.TRANSFER
            source_id = f"{config.prefix}RT{suffix}"
            txn_time = event_time
            amount = Decimal("1200")
            device_id = old_device[user_id]
            geo = home_cities[user_id]
            beneficiary = demo_hash(f"candidate-beneficiary-{suffix}")
            if pattern == "cross_city_large_transfer":
                amount = Decimal("60000")
                geo = next(city for city in cities if city != home_cities[user_id])
            elif pattern == "night_dense_operation":
                txn_time = event_time.replace(hour=2, minute=30, second=0)
                for history_index, minutes in enumerate((40, 20), start=1):
                    transaction_rows.append(
                        BankTransaction(
                            txn_id=f"{config.prefix}NTH{suffix}{history_index}", user_id=user_id,
                            from_account_id=first_account[user_id], from_card_id=None,
                            beneficiary_account_hash=demo_hash(f"night-{suffix}-{history_index}"),
                            amount=Decimal("800"), currency="CNY", txn_type=TransactionType.TRANSFER,
                            channel=TransactionChannel.APP, device_id=device_id, ip=normal_ip,
                            geo=geo, txn_time=txn_time - timedelta(minutes=minutes),
                            status=TransactionStatus.SUCCESS,
                        )
                    )
            elif pattern == "new_device_large_transfer":
                amount = Decimal("40000")
                device_id = f"{config.prefix}NEW{suffix}"
                device_rows.append(
                    DeviceFingerprint(
                        device_id=device_id, user_id=user_id,
                        fingerprint_hash=demo_hash(f"{device_id}:fingerprint"),
                        first_seen=txn_time - timedelta(hours=2), last_seen=txn_time,
                        os="Android", browser="银行APP", is_rooted=False, is_emulator=False,
                    )
                )
            elif pattern == "multi_account_convergence":
                beneficiary = demo_hash(f"convergence-{suffix}")
                for feeder_index in range(4):
                    feeder_user = user_ids[(index + feeder_index + 1) % len(user_ids)]
                    transaction_rows.append(
                        BankTransaction(
                            txn_id=f"{config.prefix}CVH{suffix}{feeder_index + 1}", user_id=feeder_user,
                            from_account_id=first_account[feeder_user], from_card_id=None,
                            beneficiary_account_hash=beneficiary, amount=Decimal("1500"), currency="CNY",
                            txn_type=TransactionType.TRANSFER, channel=TransactionChannel.APP,
                            device_id=old_device[feeder_user], ip=normal_ip,
                            geo=home_cities[feeder_user],
                            txn_time=txn_time - timedelta(minutes=20 - feeder_index * 3),
                            status=TransactionStatus.SUCCESS,
                        )
                    )
            transaction_rows.append(
                BankTransaction(
                    txn_id=source_id, user_id=user_id, from_account_id=first_account[user_id],
                    from_card_id=None, beneficiary_account_hash=beneficiary, amount=amount,
                    currency="CNY", txn_type=TransactionType.TRANSFER,
                    channel=TransactionChannel.APP, device_id=device_id, ip=normal_ip,
                    geo=geo, txn_time=txn_time, status=TransactionStatus.PENDING,
                )
            )
            event_time = txn_time

        elif pattern == "multi_lender_loan":
            event_type = EventType.LOAN_APPLICATION
            source_id = f"{config.prefix}RLN{suffix}"
            for history_index in range(2):
                loan_rows.append(
                    LoanApplication(
                        loan_id=f"{config.prefix}MLH{suffix}{history_index + 1}", user_id=user_id,
                        institution_code=f"RISK_LENDER_{history_index + 1}", amount=Decimal("15000"),
                        term_months=12, purpose="教学历史申请", monthly_income=Decimal("20000"),
                        debt_ratio=Decimal("0.45"), device_id=old_device[user_id], ip=normal_ip,
                        apply_at=event_time - timedelta(days=10 - history_index * 5),
                        status=LoanStatus.REJECTED,
                    )
                )
            loan_rows.append(
                LoanApplication(
                    loan_id=source_id, user_id=user_id, institution_code="RISK_LENDER_3",
                    amount=Decimal("40000"), term_months=24, purpose="教学当前申请",
                    monthly_income=Decimal("20000"), debt_ratio=Decimal("0.55"),
                    device_id=old_device[user_id], ip=normal_ip, apply_at=event_time,
                    status=LoanStatus.SUBMITTED,
                )
            )

        elif pattern in {"shared_device", "proxy_or_tor_login"}:
            event_type = EventType.LOGIN
            source_id = f"{config.prefix}RLG{suffix}"
            device_id = old_device[user_id]
            ip = normal_ip
            geo = home_cities[user_id]
            if pattern == "shared_device":
                device_id = f"{config.prefix}SHR{suffix}"
                for shared_index in range(5):
                    shared_user = user_ids[(index + shared_index) % len(user_ids)]
                    device_rows.append(
                        DeviceFingerprint(
                            device_id=device_id, user_id=shared_user,
                            fingerprint_hash=demo_hash(f"{device_id}:fingerprint"),
                            first_seen=event_time - timedelta(days=20), last_seen=event_time,
                            os="Android", browser="银行APP", is_rooted=False, is_emulator=True,
                        )
                    )
            else:
                device_id = f"{config.prefix}PXY{suffix}"
                ip = proxy_ip if index % 2 else tor_ip
                geo = "上海" if home_cities[user_id] != "上海" else "北京"
                device_rows.append(
                    DeviceFingerprint(
                        device_id=device_id, user_id=user_id,
                        fingerprint_hash=demo_hash(f"{device_id}:fingerprint"),
                        first_seen=event_time - timedelta(hours=3), last_seen=event_time,
                        os="Android", browser="银行APP", is_rooted=False, is_emulator=False,
                    )
                )
            login_rows.append(
                LoginLog(
                    login_id=source_id, user_id=user_id, device_id=device_id, ip=ip, geo=geo,
                    success=True, fail_reason=None, login_at=event_time,
                )
            )

        else:
            # 正常对照均匀覆盖四类事件，保证每类 API/特征路径都有训练样本。
            normal_kind = index % 4
            if normal_kind in (0, 1):
                is_card = normal_kind == 1
                event_type = EventType.CARD_PAYMENT if is_card else EventType.TRANSFER
                source_id = f"{config.prefix}{'NC' if is_card else 'NT'}{suffix}"
                transaction_rows.append(
                    BankTransaction(
                        txn_id=source_id, user_id=user_id, from_account_id=first_account[user_id],
                        from_card_id=first_card[user_id] if is_card else None,
                        beneficiary_account_hash=demo_hash(f"normal-current-{suffix}"),
                        amount=Decimal("500" if is_card else "1200"), currency="CNY",
                        txn_type=TransactionType.CARD_PAYMENT if is_card else TransactionType.TRANSFER,
                        channel=TransactionChannel.POS if is_card else TransactionChannel.APP,
                        device_id=old_device[user_id], ip=normal_ip, geo=home_cities[user_id],
                        txn_time=event_time, status=TransactionStatus.PENDING,
                    )
                )
            elif normal_kind == 2:
                event_type = EventType.LOGIN
                source_id = f"{config.prefix}NL{suffix}"
                login_rows.append(
                    LoginLog(
                        login_id=source_id, user_id=user_id, device_id=old_device[user_id],
                        ip=normal_ip, geo=home_cities[user_id], success=True,
                        fail_reason=None, login_at=event_time,
                    )
                )
            else:
                event_type = EventType.LOAN_APPLICATION
                source_id = f"{config.prefix}NLN{suffix}"
                loan_rows.append(
                    LoanApplication(
                        loan_id=source_id, user_id=user_id, institution_code="DEMO_BANK_NORMAL",
                        amount=Decimal("10000"), term_months=12, purpose="教学正常申请",
                        monthly_income=Decimal("20000"), debt_ratio=Decimal("0.20"),
                        device_id=old_device[user_id], ip=normal_ip, apply_at=event_time,
                        status=LoanStatus.SUBMITTED,
                    )
                )

        candidates.append(
            RiskCandidate(
                event_type=event_type.value,
                source_id=source_id,
                user_id=user_id,
                event_time=event_time.isoformat(),
                pattern=pattern,
            )
        )

    # 候选场景可能追加新设备；必须在交易、登录和贷款之前写入。
    already_persisted_devices = config.users
    await _add_in_batches(db, device_rows[already_persisted_devices:])
    await _add_in_batches(db, transaction_rows)
    await _add_in_batches(db, login_rows)
    await _add_in_batches(db, loan_rows)

    summary = GenerationSummary(
        customers=len(customer_rows), accounts=len(account_rows), cards=len(card_rows),
        devices=len(device_rows), ip_records=len(ip_rows), transactions=len(transaction_rows),
        logins=len(login_rows), loans=len(loan_rows), candidates=len(candidates),
        risk_candidates=sum(item.pattern != "normal_control" for item in candidates),
        seed=config.seed, prefix=config.prefix,
    )
    return summary, candidates
