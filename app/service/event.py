"""
事件处理管道 (process_event 统一入口) — 医疗版

4 步业务流 (流程结构不变, 业务对象换医疗):
  1. 业务实体校验 (参保人/结算/处方/挂号/药品订单是否存在, 归属是否一致)
  2. 自动补全关联业务参数 (order_id=业务单ID, receive_id=医院ID, event_data.doctor_id)
  3. 黑名单前置拦截 (医保卡/身份证/执业证/医院编码/用户, 撞黑就拒, 不再跑 7 步)
  4. 调用风控决策引擎 run_risk_check (7 步)
"""
import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import (
    Appointment,
    Doctor,
    DrugOrder,
    InsuranceClaim,
    Prescription,
    UserInfo,
)
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


# event_type → (业务表, 业务单ID字段, 医院字段, 医生字段)
# DrugOrder 无医院字段, 经处方 (rx_id) 关联 Prescription 拿医院
_EVENT_BUSINESS_TABLE = {
    "医保结算": (InsuranceClaim, "claim_id", "hospital_id", None),
    "处方审核": (Prescription, "rx_id", "hospital_id", "doctor_id"),
    "挂号": (Appointment, "appt_id", "hospital_id", "doctor_id"),
    "药品代购": (DrugOrder, "drug_order_id", None, None),
}


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. 业务实体校验
    await validate_risk_check_request(db, request)

    # 2. 补全 order_id / receive_id / doctor_id (黑名单检查需要)
    request = await _enrich_request(db, request)

    # 3. 黑名单前置检查
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning("撞黑名单: type=%s, value=%s, user_id=%s",
                       blocked, request.user_id, request.user_id)
        return _blacklist_reject(request, blocked)

    # 4. 决策引擎 7 步: validate → event → feature → snapshot → rule → decision → persist+respond
    return await run_risk_check(db, request)


# 按 event_type 自动补全业务参数
async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    cfg = _EVENT_BUSINESS_TABLE.get(request.event_type)
    if not cfg:
        return request
    model, id_field, hospital_field, doctor_field = cfg

    if not request.order_id:
        request.order_id = request.source_id

    row = (await db.execute(
        select(model).where(getattr(model, id_field) == request.source_id)
    )).first()
    if row is None:
        return request

    # receive_id 承载"医院ID" (黑名单"医院编码"检查用)
    if hospital_field and not request.receive_id:
        request.receive_id = getattr(row, hospital_field, None)
    if request.event_type == "药品代购" and not request.receive_id:
        # 药品代购: 经处方关联 Prescription 拿医院
        rx = (await db.execute(
            select(Prescription.hospital_id).where(Prescription.rx_id == row.rx_id)
        )).first()
        if rx and rx[0]:
            request.receive_id = rx[0]

    # doctor_id 放进 event_data (执业证黑名单检查用)
    if doctor_field:
        did = getattr(row, doctor_field, None)
        if did:
            request.event_data = dict(request.event_data or {})
            request.event_data["doctor_id"] = did

    return request


# 黑名单优先级: 用户 > 医保卡 > 身份证 > 医院编码 > 执业证; 短路: 一旦撞黑立刻返回
async def _check_all_blacklists(
    db: AsyncSession, request: RiskCheckRequest,
) -> str | None:
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"

    u = (await db.execute(
        select(UserInfo.medical_card_no, UserInfo.id_card_hash)
        .where(UserInfo.user_id == request.user_id)
    )).first()
    if u:
        if u[0] and await check_blacklist(db, "医保卡", u[0]):
            return "医保卡"
        if u[1] and await check_blacklist(db, "身份证", u[1]):
            return "身份证"

    if request.receive_id and await check_blacklist(db, "医院编码", request.receive_id):
        return "医院编码"

    doctor_id = (request.event_data or {}).get("doctor_id")
    if doctor_id:
        lic = (await db.execute(
            select(Doctor.license_no).where(Doctor.doctor_id == doctor_id)
        )).first()
        if lic and lic[0] and await check_blacklist(db, "执业证", lic[0]):
            return "执业证"
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
        ml_score=None,
        ml_decision=None,
        blocked_by=blocked_by,
        message=f"撞黑名单: {blocked_by}",
    )


# ============================================================
# Demo: 演示 4 步流程 + 黑名单类型 — 无需 DB (只读常量)
# 跑法: python app/service/event.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("事件处理管道 — 4 步流程 (医疗版)")
    print("=" * 60)
    print("\n[1] 事件 → 业务表映射:")
    for evt, (model, id_f, h_f, d_f) in _EVENT_BUSINESS_TABLE.items():
        print(f"  {evt:<10} → {model.__name__:<16} id={id_f:<16} hospital={h_f} doctor={d_f}")

    print("\n[2] 黑名单检查类型 (医疗版):")
    for t in ["用户", "医保卡", "身份证", "医院编码", "执业证"]:
        print(f"  - {t}")

    print("\n" + "=" * 60)
    print("总结: 流程结构不变, 业务对象换成 医保结算/处方审核/挂号/药品代购")