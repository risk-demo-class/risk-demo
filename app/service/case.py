"""Service 层步骤三：黑名单预拦截。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DeviceBinding, RiskBlacklist, RiskCase, Student
from app.schemas import BlacklistCreate, RiskCheckRequest


_ALLOWED_CASE_TRANSITIONS: dict[str, set[str]] = {
    "待审核": {"审核中", "已通过", "已拒绝", "已关闭"},
    "审核中": {"已通过", "已拒绝", "已关闭"},
    "已通过": set(),
    "已拒绝": set(),
    "已关闭": set(),
}


def _is_blacklisted(session: Session, blacklist_type: str, value: str | None) -> bool:
    if not value:
        return False
    return session.scalar(
        select(RiskBlacklist.blacklist_id).where(
            RiskBlacklist.blacklist_type == blacklist_type,
            RiskBlacklist.blacklist_value == value,
        )
    ) is not None


def check_blacklists(session: Session, request: RiskCheckRequest) -> str | None:
    """依次检查用户、证件哈希和设备哈希，命中即停止后续规则计算。"""
    if _is_blacklisted(session, "用户", request.user_id):
        return "用户黑名单"

    student = session.get(Student, request.user_id)
    if student and _is_blacklisted(session, "证件哈希", student.student_id_hash):
        return "证件黑名单"

    device_hash = session.scalar(
        select(DeviceBinding.device_fingerprint_hash)
        .where(DeviceBinding.user_id == request.user_id)
        .order_by(DeviceBinding.last_seen_at.desc())
        .limit(1)
    )
    if _is_blacklisted(session, "设备哈希", device_hash):
        return "设备黑名单"
    return None


def list_blacklists(
    session: Session, page: int, page_size: int, blacklist_type: str | None
) -> tuple[int, list[RiskBlacklist]]:
    filters = []
    if blacklist_type:
        filters.append(RiskBlacklist.blacklist_type == blacklist_type)
    total = session.scalar(select(func.count()).select_from(RiskBlacklist).where(*filters)) or 0
    items = session.scalars(
        select(RiskBlacklist)
        .where(*filters)
        .order_by(RiskBlacklist.blacklist_id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return total, items


def add_blacklist(session: Session, data: BlacklistCreate) -> RiskBlacklist:
    item = RiskBlacklist(**data.model_dump())
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def remove_blacklist(session: Session, blacklist_id: int) -> bool:
    item = session.get(RiskBlacklist, blacklist_id)
    if item is None:
        return False
    session.delete(item)
    session.commit()
    return True


def review_case(session: Session, case_id: str, decision: str) -> RiskCase | None:
    """更新案件工作状态；评估、特征和规则快照均保持只读。"""
    item = session.get(RiskCase, case_id)
    if item is None:
        return None
    if decision not in _ALLOWED_CASE_TRANSITIONS.get(item.case_status, set()):
        raise ValueError(f"案件不能从“{item.case_status}”流转到“{decision}”")
    item.case_status = decision
    session.commit()
    session.refresh(item)
    return item
