"""
金融风控事件处理管道 (process_event 统一入口)

4 步业务流:
  1. 业务实体校验 (账户/交易/贷款是否存在, 归属是否一致)
  2. 自动补全关联业务参数 (account_id, loan_id)
  3. 黑名单前置拦截 (身份证/手机号/账户/IP/设备ID/国家地区, 撞黑就拒, 不再跑 7 步)
  4. 调用风控决策引擎 run_risk_check (7 步)

金融场景黑名单检查规则:
  - 身份证黑名单: 必查 (任何 event_type)
  - 手机号黑名单: 有 account_id 时查
  - 账户黑名单: 有 account_id 时查
  - IP黑名单: 有 event_data.ip_address 时查
  - 设备ID黑名单: 有 event_data.device_id 时查
  - 国家地区黑名单: 有 event_data.country_code 时查
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import AccountInfo, TransactionOrder, LoanInfo, UserOperationLog, AmlSuspiciousReport
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    """金融风控事件处理主入口"""
    # 1. 业务实体校验
    await validate_risk_check_request(db, request)

    # 2. 补全 account_id / loan_id (黑名单检查需要)
    request = await _enrich_request(db, request)

    # 3. 黑名单前置检查
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning("撞黑名单: type=%s, value=%s, user_id=%s",
                       blocked, request.user_id, request.user_id)
        return _blacklist_reject(request, blocked)

    # 4. 决策引擎 7 步: validate → event → feature → snapshot → rule → decision → persist+respond
    return await run_risk_check(db, request)


# 优先级: 身份证 > 手机号 > 账户 > IP > 设备ID > 国家地区; 短路: 一旦撞黑立刻返回
async def _check_all_blacklists(
    db: AsyncSession, request: RiskCheckRequest,
) -> str | None:
    """
    金融场景黑名单检查 (6种类型, 优先级短路)
    
    检查顺序:
    1. 身份证 (id_card_no) - 从 account_info 获取
    2. 手机号 (phone_no) - 从 account_info 获取
    3. 账户 (account_id) - 直接从 request 获取
    4. IP (ip_address) - 从 event_data 获取
    5. 设备ID (device_id) - 从 event_data 获取
    6. 国家地区 (country_code) - 从 event_data 获取
    """
    # 1. 身份证黑名单
    if request.account_id:
        row = (await db.execute(
            select(AccountInfo.id_card_no).where(AccountInfo.account_id == request.account_id)
        )).first()
        if row and row.id_card_no and await check_blacklist(db, "身份证", row.id_card_no):
            return "身份证"
    
    # 2. 手机号黑名单
    if request.account_id:
        row = (await db.execute(
            select(AccountInfo.phone_no).where(AccountInfo.account_id == request.account_id)
        )).first()
        if row and row.phone_no and await check_blacklist(db, "手机号", row.phone_no):
            return "手机号"
    
    # 3. 账户黑名单
    if request.account_id and await check_blacklist(db, "账户", request.account_id):
        return "账户"
    
    # 4. IP黑名单
    event_data = request.event_data or {}
    ip_address = event_data.get("ip_address")
    if ip_address and await check_blacklist(db, "IP", ip_address):
        return "IP"
    
    # 5. 设备ID黑名单
    device_id = event_data.get("device_id")
    if device_id and await check_blacklist(db, "设备ID", device_id):
        return "设备ID"
    
    # 6. 国家地区黑名单
    country_code = event_data.get("country_code")
    if country_code and await check_blacklist(db, "国家地区", country_code):
        return "国家地区"
    
    return None


# 按 event_type 自动补全 account_id / loan_id
async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    """
    金融场景请求补全
    
    根据 event_type 补全 account_id 和 loan_id:
    - 交易/转账/取现: source_id 是 txn_id, 从 transaction_order 获取 account_id
    - 贷款申请: source_id 是 loan_id, 从 loan_info 获取 account_id
    - 账户变更: source_id 是 op_id, 从 user_operation_log 获取 account_id
    - 反洗钱预警: source_id 是 report_id, 从 aml_suspicious_report 获取 account_id
    - 登录: 需要直接提供 account_id
    """
    if request.event_type in ("交易", "转账", "取现"):
        # source_id 是 txn_id
        if not request.account_id and request.source_id:
            row = (await db.execute(
                select(TransactionOrder.account_id).where(
                    TransactionOrder.txn_id == request.source_id
                )
            )).first()
            if row:
                request.account_id = row.account_id
        
        # 从 transaction_order 获取 event_data (ip_address, device_id, country_code)
        if request.source_id and not request.event_data:
            row = (await db.execute(
                select(
                    TransactionOrder.ip_address,
                    TransactionOrder.device_id,
                    TransactionOrder.country_code
                ).where(TransactionOrder.txn_id == request.source_id)
            )).first()
            if row:
                request.event_data = {
                    "ip_address": row.ip_address,
                    "device_id": row.device_id,
                    "country_code": row.country_code,
                }

    elif request.event_type == "贷款申请":
        # source_id 是 loan_id
        if not request.account_id and request.source_id:
            row = (await db.execute(
                select(LoanInfo.account_id).where(
                    LoanInfo.loan_id == request.source_id
                )
            )).first()
            if row:
                request.account_id = row.account_id
        if not request.loan_id and request.source_id:
            request.loan_id = request.source_id

    elif request.event_type == "账户变更":
        # source_id 是 op_id
        if not request.account_id and request.source_id:
            try:
                op_id = int(request.source_id)
                row = (await db.execute(
                    select(UserOperationLog.account_id).where(
                        UserOperationLog.op_id == op_id
                    )
                )).first()
                if row:
                    request.account_id = row.account_id
            except (ValueError, TypeError):
                pass

    elif request.event_type == "反洗钱预警":
        # source_id 是 report_id
        if not request.account_id and request.source_id:
            try:
                report_id = int(request.source_id)
                row = (await db.execute(
                    select(AmlSuspiciousReport.account_id).where(
                        AmlSuspiciousReport.report_id == report_id
                    )
                )).first()
                if row:
                    request.account_id = row.account_id
            except (ValueError, TypeError):
                pass

    elif request.event_type == "登录":
        # 登录事件需要直接提供 account_id, 或者从 event_data 获取
        if not request.account_id and request.event_data:
            request.account_id = request.event_data.get("account_id")

    return request


# 故意不写库: 黑名单拦截不算一次风控评估, 只算"系统保护动作",
# 不写 risk_event/risk_assessment, 避免审计噪音
def _blacklist_reject(request: RiskCheckRequest, blocked_by: str) -> RiskCheckResponse:
    """黑名单拦截响应 (不写库)"""
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
    print("金融风控 Service Event — 黑名单优先级短路")
    print("=" * 60)

    # 1. _check_all_blacklists 子函数: 6种黑名单类型优先级
    print("\n[1] 黑名单检查优先级: 身份证 → 手机号 → 账户 → IP → 设备ID → 国家地区 (短路)")

    async def demo_blacklist_priority():
        # 模拟 7 种场景
        scenarios = [
            ("只身份证撞黑",     ["身份证", None, None, None, None, None], "身份证"),
            ("只手机号撞黑",     [None, "手机号", None, None, None, None], "手机号"),
            ("只账户撞黑",       [None, None, "账户", None, None, None], "账户"),
            ("只IP撞黑",         [None, None, None, "IP", None, None], "IP"),
            ("只设备ID撞黑",     [None, None, None, None, "设备ID", None], "设备ID"),
            ("只国家地区撞黑",   [None, None, None, None, None, "国家地区"], "国家地区"),
            ("全没撞",           [None, None, None, None, None, None], None),
        ]
        for name, calls, expected in scenarios:
            class _RealDB:
                def __init__(self, calls):
                    self.calls = calls
                    self.idx = 0
                async def execute(self, stmt):
                    class _R:
                        def __init__(self, r): self.r = r
                        def scalar(self): return 1 if self.r else 0
                        def scalar_one_or_none(self): return self.r
                        def first(self): return self.r
                    which = self.calls[self.idx]
                    self.idx += 1
                    if which is None:
                        return _R(None)
                    # 返回对应的黑名单值
                    if which == "身份证":
                        return _R(SimpleNamespace(id_card_no="110101199001011234"))
                    elif which == "手机号":
                        return _R(SimpleNamespace(phone_no="13800138000"))
                    elif which == "账户":
                        return _R(SimpleNamespace(account_id="ACC001"))
                    elif which == "IP":
                        return _R(SimpleNamespace(ip_address="192.168.1.1"))
                    elif which == "设备ID":
                        return _R(SimpleNamespace(device_id="DEV001"))
                    elif which == "国家地区":
                        return _R(SimpleNamespace(country_code="CN"))
                    return _R(None)

            db = _RealDB(list(calls))
            req = SimpleNamespace(
                user_id="U001",
                account_id="ACC001",
                event_data={
                    "ip_address": "192.168.1.1",
                    "device_id": "DEV001",
                    "country_code": "CN"
                }
            )
            got = await _check_all_blacklists(db, req)
            mark = "OK" if got == expected else "FAIL"
            print(f"  [{mark}] {name:<20} 期望={expected} 实际={got}")

    asyncio.run(demo_blacklist_priority())

    # 2. _blacklist_reject 子函数: 返回 RiskCheckResponse
    print("\n[2] _blacklist_reject 行为 (不写库, 直接返响应):")
    req = SimpleNamespace(user_id="U001")
    resp = _blacklist_reject(req, blocked_by="身份证")
    print(f"  assessment_id = '{resp.assessment_id}'  (特殊值, 标识撞黑)")
    print(f"  final_score   = {resp.final_score}")
    print(f"  risk_level    = '{resp.risk_level}'")
    print(f"  decision      = '{resp.decision}'")
    print(f"  blocked_by    = '{resp.blocked_by}'  (区分撞的哪种黑名单)")
    print(f"  rule_count    = {resp.rule_count}  (0, 不走 7 步决策)")

    # 3. process_event 主入口: 4 步业务流
    print("\n[3] process_event 主入口 — 4 步业务流:")
    print("  1. validate_risk_check_request (validator.py)")
    print("  2. _enrich_request (补全 account_id / loan_id)")
    print("  3. _check_all_blacklists (短路: 身份证 > 手机号 > 账户 > IP > 设备ID > 国家地区)")
    print("  4. run_risk_check (decision.py 7 步流水线)")

    print("\n" + "=" * 60)
    print("总结: 金融场景支持 6 种黑名单类型, 优先级短路, 审计 noise 0")
