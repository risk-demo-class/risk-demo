"""
事件处理管道 (process_event 统一入口) — 银行信贷版 (Task 3)

4 步业务流:
  1. 业务实体校验 (借款人/申请/合同/还款/转账/登录 是否存在, 归属是否一致)
  2. 自动补全关联业务参数 (事件源实体 = source_id; 设备/IP 按事件类型解析)
  3. 黑名单前置拦截 (用户/身份证号/手机号/设备指纹/IP 5 种类型, 撞黑就拒)
  4. 调用风控决策引擎 run_risk_check (7 步)

黑名单类型对齐 app/config.py BUSINESS_BLACKLIST_TYPES:
  - 用户: 必查 (任何 event_type)
  - 身份证号 / 手机号: 查 user_info (PII 脱敏后存哈希, 撞哈希)
  - 设备指纹: 查事件设备 (贷款申请/转账/登录)
  - IP: 查事件 IP (代理/Tor/境外 秒拨池)
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import (
    BankAccount,
    DeviceFingerprint,
    EnterpriseInfo,
    LoanApplication,
    LoginLog,
    Transaction,
    UserInfo,
)
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. 业务实体校验
    await validate_risk_check_request(db, request)

    # 2. 补全事件关联参数 (黑名单检查需要设备/IP)
    request = await _enrich_request(db, request)

    # 3. 黑名单前置检查
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning("撞黑名单: type=%s, user_id=%s", blocked, request.user_id)
        return _blacklist_reject(request, blocked)

    # 4. 决策引擎 7 步: validate → event → feature → snapshot → rule → decision → persist+respond
    return await run_risk_check(db, request)


# 按 event_type 解析事件设备 / IP (黑名单检查 + 决策特征共用同一套逻辑)
async def _resolve_event_device_ip(
    db: AsyncSession, request: RiskCheckRequest,
) -> tuple[str | None, str | None, str | None, str | None]:
    """返回 (device_id, ip, from_account_id, to_account_id)"""
    if request.event_type == "贷款申请":
        row = (await db.execute(
            select(LoanApplication.device_id, LoanApplication.ip)
            .where(LoanApplication.application_id == request.source_id).limit(1)
        )).first()
        return (row.device_id, row.ip, None, None) if row else (None, None, None, None)
    if request.event_type == "转账":
        row = (await db.execute(
            select(Transaction.device_id, Transaction.ip,
                   Transaction.from_account_id, Transaction.to_account_id)
            .where(Transaction.txn_id == request.source_id).limit(1)
        )).first()
        return (row.device_id, row.ip, row.from_account_id, row.to_account_id) if row else (None, None, None, None)
    if request.event_type == "登录":
        row = (await db.execute(
            select(LoginLog.device_id, LoginLog.ip)
            .where(LoginLog.login_id == request.source_id).limit(1)
        )).first()
        return (row.device_id, row.ip, None, None) if row else (None, None, None, None)
    # 放款 / 还款 事件无设备/IP
    return None, None, None, None


# 按 event_type 自动补全关联业务参数
async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    # 银行版: source_id 本身就是事件源实体 ID (申请/合同/还款/交易/登录),
    # 无需像电商版那样 join 补 order_id; 设备/IP 由黑名单检查与特征计算各自解析
    return request


# 优先级: 用户 > 身份证号 > 手机号 > 设备指纹 > IP; 短路: 一旦撞黑立刻返回
async def _check_all_blacklists(
    db: AsyncSession, request: RiskCheckRequest,
) -> str | None:
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"

    user = (await db.execute(
        select(UserInfo.id_card_hash, UserInfo.mobile)
        .where(UserInfo.user_id == request.user_id).limit(1)
    )).first()
    if user:
        if user.id_card_hash and await check_blacklist(db, "身份证号", user.id_card_hash):
            return "身份证号"
        if user.mobile and await check_blacklist(db, "手机号", user.mobile):
            return "手机号"

    # 贷款申请: 法定代表人企业信用代码撞黑 (空壳公司拦截)
    if request.event_type == "贷款申请":
        code = (await db.execute(
            select(EnterpriseInfo.credit_code)
            .where(EnterpriseInfo.user_id == request.user_id).limit(1)
        )).scalar_one_or_none()
        if code and await check_blacklist(db, "统一社会信用代码", code):
            return "统一社会信用代码"

    device_id, ip, from_acc, to_acc = await _resolve_event_device_ip(db, request)
    if device_id:
        fp = (await db.execute(
            select(DeviceFingerprint.fingerprint_hash)
            .where(DeviceFingerprint.device_id == device_id).limit(1)
        )).scalar_one_or_none()
        if fp and await check_blacklist(db, "设备指纹", fp):
            return "设备指纹"
    if ip and await check_blacklist(db, "IP", ip):
        return "IP"
    # 转账事件: 转出/转入银行卡号撞黑 (黑卡拦截)
    for acc_id in (from_acc, to_acc):
        if not acc_id:
            continue
        acc_hash = (await db.execute(
            select(BankAccount.account_no_hash)
            .where(BankAccount.account_id == acc_id).limit(1)
        )).scalar_one_or_none()
        if acc_hash and await check_blacklist(db, "银行卡号", acc_hash):
            return "银行卡号"
    return None


# 故意不写库: 黑名单拦截不算一次风控评估, 只算"系统保护动作",
# 不写 risk_event/risk_assessment, 避免审计噪音
def _blacklist_reject(request: RiskCheckRequest, blocked_by: str) -> RiskCheckResponse:
    return RiskCheckResponse(
        assessment_id="blacklist_reject",
        event_id="blacklist_reject",
        user_id=request.user_id,
        final_score=100,
        risk_level="极高",
        decision="拒绝",
        rule_count=0,
        triggered_rules=[],
        features={},
        create_time=datetime.now(),
        blocked_by=blocked_by,
    )


# ============================================================
# Demo: _check_all_blacklists 黑名单优先级短路 + _enrich_request — mock DB
# 跑法: python app/service/event.py
# ============================================================
if __name__ == "__main__":
    from types import SimpleNamespace

    print("=" * 60)
    print("Service Event — 银行版黑名单优先级短路 (用户>身份证>手机号>设备>IP)")
    print("=" * 60)

    print("\n[1] 黑名单检查优先级: 用户 → 身份证号 → 手机号 → 设备指纹 → IP (短路)")

    async def demo_blacklist_priority():
        # 用固定调用序列模拟 (跟 _check_all_blacklists 内部顺序一致)
        scenarios = [
            ("只用户撞黑",    ["用户", None, None, None, None, None, None], "用户"),
            ("只身份证撞黑",  [None, "身份证号", None, None, None, None, None], "身份证号"),
            ("用户+身份证都撞", ["用户", "身份证号", None, None, None, None, None], "用户"),
            ("只设备撞黑",    [None, None, None, "设备指纹", None, None, None], "设备指纹"),
            ("只IP撞黑",      [None, None, None, None, "IP", None, None], "IP"),
            ("全没撞",        [None, None, None, None, None, None, None], None),
        ]
        for name, calls, expected in scenarios:
            class _RealDB:
                def __init__(self, calls):
                    self.calls = calls
                    self.idx = 0
                async def execute(self, stmt):
                    s = str(stmt)
                    class _R:
                        def __init__(self, r):
                            self.r = r
                        def scalar(self):
                            return 1 if self.r else 0
                        def scalar_one_or_none(self):
                            return self.r
                        def first(self):
                            return self.r
                    which = self.calls[self.idx]
                    self.idx += 1
                    if which == "身份证号":
                        return _R(SimpleNamespace(id_card_hash="HASH_ID", mobile="13800001111"))
                    if which == "设备指纹":
                        return _R(SimpleNamespace(device_id="DEV1", ip="1.1.1.1"))
                    if which == "IP":
                        return _R(SimpleNamespace(fingerprint_hash="HASH_FP"))
                    if which is None:
                        return _R(None)
                    # 撞黑: 返回非空 ORM 对象 (deleted_at=None = 未软删, 与 check_blacklist 防御检查对齐)
                    return _R(SimpleNamespace(blacklist_id=1, expire_time=None, deleted_at=None))

            db = _RealDB(list(calls))
            req = SimpleNamespace(user_id="U0001", source_id="LA0001", event_type="贷款申请")
            got = await _check_all_blacklists(db, req)
            mark = "OK" if got == expected else "FAIL"
            print(f"  [{mark}] {name:<24} 期望={expected} 实际={got}")

    asyncio.run(demo_blacklist_priority())

    print("\n[2] _blacklist_reject 行为 (不写库, 直接返响应):")
    req = SimpleNamespace(user_id="U0001")
    resp = _blacklist_reject(req, blocked_by="设备指纹")
    print(f"  assessment_id = '{resp.assessment_id}'  (特殊值, 标识撞黑)")
    print(f"  final_score   = {resp.final_score}")
    print(f"  decision      = '{resp.decision}'")
    print(f"  blocked_by    = '{resp.blocked_by}'  (区分撞的哪种黑名单)")
    print(f"  rule_count    = {resp.rule_count}  (0, 不走 7 步决策)")

    print("\n[3] process_event 主入口 — 4 步业务流:")
    print("  1. validate_risk_check_request (validator.py, 银行 5 类事件)")
    print("  2. _enrich_request (source_id 即事件实体, 设备/IP 按需解析)")
    print("  3. _check_all_blacklists (短路: 用户>身份证>手机号>设备>IP)")
    print("  4. run_risk_check (decision.py 7 步流水线)")
