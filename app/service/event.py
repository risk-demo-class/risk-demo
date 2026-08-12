"""
事件处理管道 (process_event 统一入口) (医疗版)

4 步业务流 (跟电商版一致, 不许改流程):
  1. 业务实体校验 (患者/诊疗单据是否存在, 归属是否一致)
  2. 自动补全关联业务参数 (hospital_id)
  3. 黑名单前置拦截 (用户/医保卡号/身份证号/医生执业证/医院编码 5 种类型, 撞黑就拒, 不再跑 7 步)
  4. 调用风控决策引擎 run_risk_check (7 步)

黑名单查询规则:
  - 用户黑名单: 必查 (任何 event_type, 值=user_id)
  - 医保卡号/身份证号黑名单: 查患者的 medical_card_no / id_card_hash
  - 医生执业证黑名单: 挂号/处方开具 场景查单据上的医生 license_no
  - 医院编码黑名单: 有 hospital_id 时查 (值=hospital_id)
所以 _enrich_request 提到撞黑检查之前, 保证 hospital_id 已知.
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import (
    Appointment, Doctor, DrugOrder, InsuranceClaim, Prescription, UserInfo,
)
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    # 1. 业务实体校验
    await validate_risk_check_request(db, request)

    # 2. 补全 hospital_id (医院编码黑名单检查需要)
    request = await _enrich_request(db, request)

    # 3. 黑名单前置检查
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning("撞黑名单: type=%s, user_id=%s", blocked, request.user_id)
        return _blacklist_reject(request, blocked)

    # 4. 决策引擎 7 步: validate → event → feature → snapshot → rule → decision → persist+respond
    return await run_risk_check(db, request)


# 优先级: 用户 > 医保卡号 > 身份证号 > 医生执业证 > 医院编码; 短路: 一旦撞黑立刻返回
async def _check_all_blacklists(
    db: AsyncSession, request: RiskCheckRequest,
) -> str | None:
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"

    # 患者的医保卡号 / 身份证号 (一次查询拿 2 个值)
    row = (await db.execute(
        select(UserInfo.medical_card_no, UserInfo.id_card_hash)
        .where(UserInfo.user_id == request.user_id).limit(1)
    )).first()
    if row:
        if row.medical_card_no and await check_blacklist(db, "医保卡号", row.medical_card_no):
            return "医保卡号"
        if row.id_card_hash and await check_blacklist(db, "身份证号", row.id_card_hash):
            return "身份证号"

    # 医生执业证: 单据上的开方/挂号医生 (查 Doctor.license_no)
    doctor_id = await _lookup_doctor_id(db, request)
    if doctor_id:
        license_no = (await db.execute(
            select(Doctor.license_no).where(Doctor.doctor_id == doctor_id).limit(1)
        )).scalar_one_or_none()
        if license_no and await check_blacklist(db, "医生执业证", license_no):
            return "医生执业证"

    # 医院编码
    if request.hospital_id and await check_blacklist(db, "医院编码", request.hospital_id):
        return "医院编码"
    return None


# 按 source_id 查单据上的医生 ID (只有 挂号/处方 单据有医生)
async def _lookup_doctor_id(db: AsyncSession, request: RiskCheckRequest) -> str | None:
    if request.event_type == "挂号":
        return (await db.execute(
            select(Appointment.doctor_id).where(Appointment.appt_id == request.source_id)
        )).scalar_one_or_none()
    if request.event_type == "处方开具":
        return (await db.execute(
            select(Prescription.doctor_id).where(Prescription.rx_id == request.source_id)
        )).scalar_one_or_none()
    return None


# 自动补全 hospital_id: 依次查 挂号→处方→结算; 药品订单走关联处方间接查
async def _enrich_request(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckRequest:
    if request.hospital_id:
        return request
    for model, pk_col in (
        (Appointment, Appointment.appt_id),
        (Prescription, Prescription.rx_id),
        (InsuranceClaim, InsuranceClaim.claim_id),
    ):
        hid = (await db.execute(
            select(model.hospital_id).where(pk_col == request.source_id)
        )).scalar_one_or_none()
        if hid:
            request.hospital_id = hid
            return request
    # 药品订单: drug_order → prescription → hospital_id
    hid = (await db.execute(
        select(Prescription.hospital_id)
        .select_from(DrugOrder)
        .join(Prescription, DrugOrder.rx_id == Prescription.rx_id)
        .where(DrugOrder.drug_order_id == request.source_id)
    )).scalar_one_or_none()
    if hid:
        request.hospital_id = hid
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
# Demo: _check_all_blacklists 黑名单优先级短路 — mock DB
# 跑法: python app/service/event.py
# ============================================================
if __name__ == "__main__":
    from types import SimpleNamespace

    print("=" * 60)
    print("Service Event (医疗版) — 黑名单优先级短路")
    print("=" * 60)

    # 1. _check_all_blacklists: 用户 > 医保卡号 > 身份证号 > 医生执业证 > 医院编码
    print("\n[1] 黑名单检查优先级 (短路):")

    async def demo_blacklist_priority():
        # 模拟 check_blacklist 对不同 (type, value) 的命中情况
        scenarios = [
            ("只用户撞黑",     {"用户"},                                "用户"),
            ("只医保卡撞黑",   {"医保卡号"},                            "医保卡号"),
            ("用户+医保卡都撞", {"用户", "医保卡号"},                    "用户"),
            ("只身份证号撞黑", {"身份证号"},                            "身份证号"),
            ("只医院编码撞黑", {"医院编码"},                            "医院编码"),
            ("全没撞",         set(),                                   None),
        ]
        for name, hit_types, expected in scenarios:
            class _RealDB:
                def __init__(self, hits):
                    self.hits = hits
                async def execute(self, stmt):
                    s = str(stmt)
                    class _R:
                        def __init__(self, r): self.r = r
                        def first(self): return self.r
                        def scalar_one_or_none(self): return self.r
                    # UserInfo 查询 → 返医保卡号+身份证号
                    if "user_info" in s:
                        return _R(SimpleNamespace(medical_card_no="MC001", id_card_hash="IDH001"))
                    # Doctor 查询 → 返执业证号
                    if "doctor" in s:
                        return _R("LIC001")
                    return _R(None)

            async def fake_check(db, btype, value):
                return btype in hit_types

            # monkeypatch check_blacklist
            global check_blacklist
            orig = check_blacklist
            check_blacklist = fake_check
            try:
                db = _RealDB(hit_types)
                req = SimpleNamespace(
                    user_id="P001", source_id="APPT001", event_type="挂号", hospital_id="H001",
                )
                got = await _check_all_blacklists(db, req)
            finally:
                check_blacklist = orig
            mark = "OK" if got == expected else "FAIL"
            print(f"  [{mark}] {name:<16} 期望={expected} 实际={got}")

    asyncio.run(demo_blacklist_priority())

    # 2. _blacklist_reject: 返回 RiskCheckResponse
    print("\n[2] _blacklist_reject 行为 (不写库, 直接返响应):")
    req = SimpleNamespace(user_id="P001")
    resp = _blacklist_reject(req, blocked_by="医保卡号")
    print(f"  assessment_id = '{resp.assessment_id}'  (特殊值, 标识撞黑)")
    print(f"  final_score   = {resp.final_score}")
    print(f"  risk_level    = '{resp.risk_level}'")
    print(f"  decision      = '{resp.decision}'")
    print(f"  blocked_by    = '{resp.blocked_by}'  (区分撞的哪种黑名单)")
    print(f"  rule_count    = {resp.rule_count}  (0, 不走 7 步决策)")

    # 3. process_event 主入口: 4 步业务流
    print("\n[3] process_event 主入口 — 4 步业务流:")
    print("  1. validate_risk_check_request (validator.py)")
    print("  2. _enrich_request (补全 hospital_id)")
    print("  3. _check_all_blacklists (短路: 用户 > 医保卡号 > 身份证号 > 医生执业证 > 医院编码)")
    print("  4. run_risk_check (decision.py 7 步流水线)")

    print("\n" + "=" * 60)
    print("总结: 黑名单拦截独立 1 步, 审计 noise 0 (不写 risk_event/case)")
