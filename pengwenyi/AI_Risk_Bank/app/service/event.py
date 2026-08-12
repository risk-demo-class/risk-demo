"""
事件处理管道 (process_event 统一入口)

4 步业务流 (结构保持, 内容银行化):
  1. 业务实体校验 (用户/交易/登录/贷款/信用卡 是否存在, 归属是否一致)
  2. 自动补全关联业务参数 (转账→from_card/to_card/device_id/ip, 登录→device_id/ip,
     贷款申请→device_id/ip, 信用卡→card_id)
  3. 黑名单前置拦截 (用户必查 + IP 命中 blacklist_extra 时拦截, 撞黑就拒, 不再跑 7 步)
  4. 调用风控决策引擎 run_risk_check (7 步)

银行专属黑名单 (黑卡/设备指纹/身份证) 不走第 3 步, 通过"特征 + 规则"拦截
(如 R030 黑卡拦截: txn_to_card_black 特征 + 规则条件, 不碰 risk_blacklist 结构).
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import BankCard, LoanApplication, LoginLog, Transaction
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. 业务实体校验
    await validate_risk_check_request(db, request)

    # 2. 补全 from_card/to_card/device_id/ip (黑名单检查需要 ip)
    request = await _enrich_request(db, request)

    # 3. 黑名单前置检查 (用户 > IP, 短路)
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning("撞黑名单: type=%s, value=%s, user_id=%s",
                       blocked, request.user_id, request.user_id)
        return _blacklist_reject(request, blocked)

    # 4. 决策引擎 7 步: validate → event → feature → snapshot → rule → decision → persist+respond
    return await run_risk_check(db, request)


# 优先级: 用户 > IP; 短路: 一旦撞黑立刻返回
async def _check_all_blacklists(
    db: AsyncSession, request: RiskCheckRequest,
) -> str | None:
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"
    # 银行版无"地址"黑名单; IP 命中 blacklist_extra (type=IP) 时拦截
    if request.ip:
        from app.models import BlacklistExtra
        from sqlalchemy import func as _func
        hit = (await db.execute(
            select(_func.count()).select_from(BlacklistExtra).where(
                BlacklistExtra.type == "IP",
                BlacklistExtra.value == request.ip,
            )
        )).scalar()
        if hit:
            return "IP"
    return None


# 按 event_type 自动补全关联业务参数
# if/elif 不用字典派发: SQL 差异大, if/elif 更易读
async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    if request.event_type == "转账":
        # 转账: source_id=txn_id, 从交易记录补全 from_card/to_card/device_id/ip/geo
        row = (await db.execute(
            select(
                Transaction.from_card, Transaction.to_card,
                Transaction.device_id, Transaction.ip,
            ).where(Transaction.txn_id == request.source_id)
        )).first()
        if row:
            request.from_card = request.from_card or row.from_card
            request.to_card = request.to_card or row.to_card
            request.device_id = request.device_id or row.device_id
            request.ip = request.ip or row.ip

    elif request.event_type == "登录":
        # 登录: source_id=login_id, 从登录日志补全 device_id/ip
        row = (await db.execute(
            select(LoginLog.device_id, LoginLog.ip).where(
                LoginLog.login_id == request.source_id
            )
        )).first()
        if row:
            request.device_id = request.device_id or row.device_id
            request.ip = request.ip or row.ip

    elif request.event_type == "贷款申请":
        # 贷款: source_id=loan_id, 补金额/负债率/月收入等到 event_data (设备/IP 前端传或留空)
        row = (await db.execute(
            select(
                LoanApplication.amount, LoanApplication.term_months,
                LoanApplication.debt_ratio, LoanApplication.monthly_income,
            ).where(LoanApplication.loan_id == request.source_id)
        )).first()
        if row:
            ed = dict(request.event_data or {})
            ed.setdefault("amount", float(row.amount or 0))
            ed.setdefault("term_months", float(row.term_months or 0))
            ed.setdefault("debt_ratio", float(row.debt_ratio or 0))
            ed.setdefault("monthly_income", float(row.monthly_income or 0))
            request.event_data = ed

    elif request.event_type == "信用卡":
        # 信用卡: source_id=card_id, 校验卡存在 (validator 已做), 补 device/ip 留空待前端传
        row = (await db.execute(
            select(BankCard.card_id).where(BankCard.card_id == request.source_id)
        )).first()
        if row and not request.event_data:
            request.event_data = {}

    return request


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
    print("Service Event — 黑名单优先级短路 (银行版: 用户 > IP)")
    print("=" * 60)

    # 1. _check_all_blacklists 子函数: 用户 > IP
    print("\n[1] 黑名单检查优先级: 用户 → IP (短路)")

    async def demo_blacklist_priority():
        # 模拟 4 种场景
        # _check_all_blacklists 内部调用顺序: 用户黑名单 → IP 黑名单 (blacklist_extra)
        # calls[0]=用户查询结果 (ORM 或 None), calls[1]=IP 查询结果 (count 或 None)
        scenarios = [
            ("只用户撞黑",     ["user", None],        "用户"),
            ("只 IP 撞黑",     [None,    "ip"],        "IP"),
            ("用户+IP 都撞",   ["user", "ip"],        "用户"),
            ("全没撞",         [None,    None],        None),
        ]
        for name, calls, expected in scenarios:
            class _RealDB:
                def __init__(self, calls):
                    self.calls = calls
                    self.idx = 0
                async def execute(self, stmt):
                    class _R:
                        def __init__(self, r): self.r = r
                        def scalar(self):
                            return 1 if self.r is not None else 0
                        def scalar_one_or_none(self): return self.r
                        def first(self): return self.r
                    which = self.calls[self.idx]
                    self.idx += 1
                    if which is None:
                        return _R(None)
                    if which == "user":
                        # 用户黑名单命中: 返 ORM 对象
                        return _R(SimpleNamespace(blacklist_id=1, expire_time=None))
                    # "ip": blacklist_extra 计数查询 → scalar() 返 1
                    return _R(SimpleNamespace(x=1))

            db = _RealDB(list(calls))
            req = SimpleNamespace(user_id="U001", ip="1.2.3.4")
            got = await _check_all_blacklists(db, req)
            mark = "OK" if got == expected else "FAIL"
            print(f"  [{mark}] {name:<22} 调用序列={calls}  期望={expected} 实际={got}")

    asyncio.run(demo_blacklist_priority())

    # 2. _blacklist_reject 子函数: 返回 RiskCheckResponse
    print("\n[2] _blacklist_reject 行为 (不写库, 直接返响应):")
    req = SimpleNamespace(user_id="U001")
    resp = _blacklist_reject(req, blocked_by="用户")
    print(f"  assessment_id = '{resp.assessment_id}'  (特殊值, 标识撞黑)")
    print(f"  final_score   = {resp.final_score}")
    print(f"  risk_level    = '{resp.risk_level}'")
    print(f"  decision      = '{resp.decision}'")
    print(f"  blocked_by    = '{resp.blocked_by}'  (区分撞的哪种: 用户/IP)")
    print(f"  rule_count    = {resp.rule_count}  (0, 不走 7 步决策)")

    # 3. process_event 主入口: 4 步业务流
    print("\n[3] process_event 主入口 — 4 步业务流 (结构保持):")
    print("  1. validate_risk_check_request (validator.py, 银行实体/归属校验)")
    print("  2. _enrich_request (补全 from_card/to_card/device_id/ip / event_data)")
    print("  3. _check_all_blacklists (短路: 用户 > IP)")
    print("  4. run_risk_check (decision.py 7 步流水线)")
    print("  注: 黑卡/设备指纹/身份证黑名单走特征+规则 (R030 等), 不碰第 3 步")

    print("\n" + "=" * 60)
    print("总结: 黑名单拦截独立 1 步, 审计 noise 0 (不写 risk_event/case); 银行专属黑名单走特征+规则")
