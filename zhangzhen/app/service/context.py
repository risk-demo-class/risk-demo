"""单次风险检查在 Service/Engine 之间传递的内存工作资料包。"""

from dataclasses import dataclass
from datetime import datetime

from app.models_business import (
    BankAccount,
    BankCard,
    BankTransaction,
    CustomerInfo,
    DeviceFingerprint,
    IpGeoLocation,
    LoanApplication,
    LoginLog,
)
from app.schemas import RiskCheckRequest


@dataclass(slots=True)
class RiskContext:
    request: RiskCheckRequest
    customer: CustomerInfo
    event_time: datetime
    login: LoginLog | None = None
    transaction: BankTransaction | None = None
    loan: LoanApplication | None = None
    account: BankAccount | None = None
    card: BankCard | None = None
    device: DeviceFingerprint | None = None
    ip_info: IpGeoLocation | None = None
    device_id: str | None = None
    ip: str | None = None
    geo: str | None = None
    beneficiary_account_hash: str | None = None

    def safe_event_snapshot(self) -> dict[str, object]:
        """生成可审计但不包含姓名、证件号、卡号明文的事件快照。"""

        snapshot: dict[str, object] = {
            "event_type": self.request.event_type.value,
            "source_id": self.request.source_id,
            "user_id": self.request.user_id,
            "event_time": self.event_time.isoformat(),
            "device_id": self.device_id,
            "ip": self.ip,
            "geo": self.geo,
            "request_data": self.request.event_data,
        }
        if self.transaction is not None:
            snapshot.update(
                {
                    "amount": float(self.transaction.amount),
                    "currency": self.transaction.currency,
                    "txn_type": self.transaction.txn_type.value,
                    "channel": self.transaction.channel.value,
                    "from_account_id": self.transaction.from_account_id,
                    "from_card_id": self.transaction.from_card_id,
                    "beneficiary_account_hash": self.transaction.beneficiary_account_hash,
                }
            )
        if self.loan is not None:
            snapshot.update(
                {
                    "amount": float(self.loan.amount),
                    "term_months": self.loan.term_months,
                    "institution_code": self.loan.institution_code,
                    "debt_ratio": float(self.loan.debt_ratio),
                }
            )
        if self.login is not None:
            snapshot.update({"success": self.login.success, "fail_reason": self.login.fail_reason})
        return snapshot

