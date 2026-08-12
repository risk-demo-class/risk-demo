"""
银行业务实体校验器: 集中处理"借款人/贷款申请/合同/还款/转账/登录"等业务实体的
存在性、一致性校验.

所有校验失败都抛 HTTPException, 由 FastAPI 统一返回 4xx 响应.

业务事件类型 (Task 2, 与 app/config.py 的 BUSINESS_EVENT_TYPES 对齐):
  - 贷款申请  -> loan_application.application_id
  - 放款      -> loan_contract.contract_id
  - 还款      -> repayment_record.record_id
  - 转账      -> transaction.txn_id
  - 登录      -> login_log.login_id
"""
import asyncio
import logging
from typing import Any, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import BUSINESS_EVENT_TYPES
from app.models import (
    LoanApplication,
    LoanContract,
    LoginLog,
    RepaymentRecord,
    Transaction,
    UserInfo,
)
from app.schemas import RiskCheckRequest

logger = logging.getLogger(__name__)


async def ensure_exists(
    db: AsyncSession,
    model: type,
    field_name: str,
    value: Any,
    *,
    entity_label: str,
    field_label: Optional[str] = None,
    cast_value: Optional[Callable[[Any], Any]] = None,
    status_code: int = 404,
) -> None:
    """泛型存在性校验: 检查 model.field_name == value 的记录是否存在."""
    field_label = field_label or f"{entity_label}ID"
    if not value:
        # 空值属于"调用方没传对", 不是"实体不存在", 抛 400
        raise HTTPException(status_code=400, detail=f"{field_label}不能为空")

    compare_value = cast_value(value) if cast_value else value
    stmt = (
        select(func.count())
        .select_from(model)
        .where(getattr(model, field_name) == compare_value)
        .limit(1)
    )
    if not (await db.execute(stmt)).scalar():
        logger.warning("校验失败: %s不存在 %s=%s", entity_label, field_label, value)
        raise HTTPException(
            status_code=status_code,
            detail=f"{field_label}不存在: {value}",
        )


async def ensure_user_exists(db: AsyncSession, user_id: str) -> None:
    await ensure_exists(db, UserInfo, "user_id", user_id, entity_label="借款人")


# 防"水平越权": 拿真申请/合同 + 假用户绕过风控
# 攻击场景: 攻击者拿自己的 user_id + 别人的真实 application_id 调风控
# 后果: 别人的贷款申请/合同被风控/被拒, 业务投诉
async def ensure_entity_belongs_to_user(
    db: AsyncSession,
    model: type,
    entity_id_field: str,
    user_id_field: str,
    entity_id: str,
    user_id: str,
    entity_label: str,
) -> None:
    owner = (await db.execute(
        select(getattr(model, user_id_field))
        .where(getattr(model, entity_id_field) == entity_id)
        .limit(1)
    )).scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail=f"{entity_label}ID不存在: {entity_id}")
    if owner != user_id:
        logger.warning(
            "安全告警: %s归属不一致 %s=%s, owner=%s, request_user=%s",
            entity_label, entity_id_field, entity_id, owner, user_id,
        )
        raise HTTPException(
            status_code=403,
            detail=f"{entity_label} {entity_id} 属于用户 {owner}, 与请求用户 {user_id} 不一致",
        )


async def ensure_loan_belongs_to_user(
    db: AsyncSession,
    application_id: str,
    user_id: str,
) -> None:
    """贷款申请归属校验 (防越权)"""
    await ensure_entity_belongs_to_user(
        db, LoanApplication, "application_id", "user_id",
        application_id, user_id, "贷款申请",
    )


async def ensure_contract_belongs_to_user(
    db: AsyncSession,
    contract_id: str,
    user_id: str,
) -> None:
    """贷款合同归属校验 (防越权)"""
    await ensure_entity_belongs_to_user(
        db, LoanContract, "contract_id", "user_id",
        contract_id, user_id, "贷款合同",
    )


# source_id 与 event_type 匹配的校验规则 (字典派发, 加新 event_type 只加 1 行)
# 格式: event_type -> (model, source_id 字段, cast 函数, 实体名, 错误码)
_EVENT_SOURCE_VALIDATORS = {
    ("贷款申请",): (LoanApplication, "application_id", None, "贷款申请", 400),
    ("放款",): (LoanContract, "contract_id", None, "贷款合同", 400),
    ("还款",): (RepaymentRecord, "record_id", None, "还款记录", 400),
    ("转账",): (Transaction, "txn_id", None, "交易记录", 400),
    ("登录",): (LoginLog, "login_id", None, "登录日志", 400),
}

# 一致性约束: 派发表的事件类型必须与 config.BUSINESS_EVENT_TYPES 完全一致,
# 加新事件类型时两边必须同步 (防止改一处漏一处)
assert {et for types in _EVENT_SOURCE_VALIDATORS for et in types} == set(BUSINESS_EVENT_TYPES), (
    "validator 派发表与 config.BUSINESS_EVENT_TYPES 不一致"
)


async def ensure_source_matches_event_type(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    for event_types, (model, field, caster, label, status_code) in _EVENT_SOURCE_VALIDATORS.items():
        if request.event_type not in event_types:
            continue
        await ensure_exists(
            db, model, field, request.source_id,
            entity_label=label,
            cast_value=caster,
            status_code=status_code,
        )
        return

    # 兜底: event_type 不在字典里 (Pydantic schema 层 Literal 限定, 实际不会发生,
    # 这里兜底, 防未来加新 event_type 时漏配)
    logger.warning(
        "未配置 source_id 校验规则: event_type=%s source_id=%s",
        request.event_type, request.source_id,
    )


# 组合校验: 一次跑完所有跟 request 相关的校验
async def validate_risk_check_request(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    # 1. 借款人存在
    await ensure_user_exists(db, request.user_id)

    # 2. source_id 与事件类型匹配
    await ensure_source_matches_event_type(db, request)

    # 3. 贷款申请/放款场景: 校验归属 (防越权)
    if request.event_type == "贷款申请":
        await ensure_loan_belongs_to_user(db, request.source_id, request.user_id)
    elif request.event_type == "放款":
        await ensure_contract_belongs_to_user(db, request.source_id, request.user_id)


# ============================================================
# Demo: 展示 ensure_* 函数 + _EVENT_SOURCE_VALIDATORS 字典派发表 — 用 mock DB
# 跑法: python app/service/validator.py
# ============================================================
if __name__ == "__main__":
    from types import SimpleNamespace

    print("=" * 60)
    print("Service Validator — 银行业务 5 类事件 + 字典派发表 + 完整校验链")
    print("=" * 60)

    # 1. _EVENT_SOURCE_VALIDATORS 字典派发演示
    print("\n[1] 字典派发表 _EVENT_SOURCE_VALIDATORS:")
    print(f"  {'event_type':<10} {'model':<20} {'field':<16} {'label':<6} {'status'}")
    for evt_types, (model, field, _, label, status) in _EVENT_SOURCE_VALIDATORS.items():
        evt_str = " | ".join(evt_types)
        print(f"  {evt_str:<10} {model.__name__:<20} {field:<16} {label:<6} {status}")

    # 2. ensure_exists: 用户存在/不存在 的两种行为
    print("\n[2] ensure_exists 行为 (mock DB):")

    class _FakeDB:
        """Mock DB: 模拟 SELECT COUNT(*) -> scalar() 返回 1 或 0"""
        def __init__(self, found):
            self.found = found
        async def execute(self, stmt):
            class _R:
                def __init__(self, n):
                    self.n = n
                def scalar(self):
                    return self.n
            return _R(self.found)

    async def demo_ensure_exists():
        try:
            await ensure_exists(_FakeDB(found=1), UserInfo, "user_id", "U0001", entity_label="借款人")
            print("  [OK]   user_id='U0001' 存在 → 不抛异常")
        except HTTPException as e:
            print(f"  [FAIL] {e.detail}")

        try:
            await ensure_exists(_FakeDB(found=0), UserInfo, "user_id", "U9999", entity_label="借款人")
            print("  [FAIL] 不该到这里")
        except HTTPException as e:
            print(f"  [404]  user_id='U9999' 不存在 → {e.detail}  (status={e.status_code})")

    asyncio.run(demo_ensure_exists())

    # 3. ensure_source_matches_event_type: event_type 不匹配 → 400
    print("\n[3] ensure_source_matches_event_type 行为:")
    print("  event_type='贷款申请' 但用 contract_id 当 source_id → 报错 (派发错模型)")

    async def demo_event_dispatch():
        class _FlexDB:
            def __init__(self, count_n, row):
                self.count_n = count_n
                self.row = row
            async def execute(self, stmt):
                class _R:
                    def __init__(self, n, r):
                        self.n = n
                        self.r = r
                    def scalar(self):
                        return self.n
                    def scalar_one_or_none(self):
                        return self.r
                return _R(self.count_n, self.row)

        req_ok = RiskCheckRequest(event_type="贷款申请", source_id="LA0001", user_id="U0001")
        try:
            await ensure_source_matches_event_type(_FlexDB(1, SimpleNamespace(application_id="LA0001")), req_ok)
            print("  [OK]   event_type=贷款申请 + source_id=LA0001 → LoanApplication 存在, 通过")
        except HTTPException as e:
            print(f"  [FAIL] {e.detail}")

        req_bad = RiskCheckRequest(event_type="贷款申请", source_id="LC0001", user_id="U0001")
        try:
            await ensure_source_matches_event_type(_FlexDB(0, None), req_bad)
            print("  [FAIL] 不该到这里")
        except HTTPException as e:
            print(f"  [400]  source_id='LC0001' 在 LoanApplication 找不到 → {e.detail[:60]}...  (status={e.status_code})")

    asyncio.run(demo_event_dispatch())

    # 4. ensure_entity_belongs_to_user: 防越权
    print("\n[4] ensure_loan_belongs_to_user 防越权:")
    print("  user_id='U0001' 试图操作 application_id='LA9999' (属于 U0002) → 403")

    async def demo_ownership():
        class _AppOwnerU002:
            async def execute(self, stmt):
                class _R:
                    def scalar(self):
                        return 1
                    def scalar_one_or_none(self):
                        return "U0002"   # 申请属于别人
                return _R()
        try:
            await ensure_loan_belongs_to_user(_AppOwnerU002(), "LA9999", "U0001")
            print("  [FAIL] 不该到这里")
        except HTTPException as e:
            print(f"  [403]  {e.detail[:70]}...  (status={e.status_code})")

        class _AppOwnerU001:
            async def execute(self, stmt):
                class _R:
                    def scalar(self):
                        return 1
                    def scalar_one_or_none(self):
                        return "U0001"   # 申请属于本人
                return _R()
        try:
            await ensure_loan_belongs_to_user(_AppOwnerU001(), "LA0001", "U0001")
            print("  [OK]   application_id='LA0001' 属于 U0001 → 通过")
        except HTTPException as e:
            print(f"  [FAIL] {e.detail}")

    asyncio.run(demo_ownership())

    print("\n" + "=" * 60)
    print("总结: ensure_* 覆盖 '实体存在 + 事件类型匹配 + 归属' 3 维度校验, 全用 FastAPI HTTPException 兜底")
