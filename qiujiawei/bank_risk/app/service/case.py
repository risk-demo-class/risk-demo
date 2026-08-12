"""
案件管理模块: 案件创建 / 状态流转 / 超时关闭, 黑名单检查.

黑名单类型 (5 种): user / card / device / ip / id_card
案件状态机: 待审核 → 审核中/已通过/已拒绝/已关闭; 审核中 → 已通过/已拒绝/已关闭; 其余终态

Commit 策略:
  create_case / check_blacklists:  不 commit, 留给调用方合并事务
  update_case_status / auto_close:  内部 self-commit
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

import ulid
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bank_risk.app.config import settings
from bank_risk.app.models import RiskBlacklist, RiskCase
from bank_risk.app.service.action_log import record_action

logger = logging.getLogger(__name__)


# ============================================================
# 案件状态流转白名单
# ============================================================

_ALLOWED_CASE_TRANSITIONS: dict[str, set[str]] = {
    "待审核": {"审核中", "已通过", "已拒绝", "已关闭"},
    "审核中": {"已通过", "已拒绝", "已关闭"},
    "已通过": set(),
    "已拒绝": set(),
    "已关闭": set(),
}


# ============================================================
# 黑名单检查
# ============================================================

async def _check_one_blacklist(
    db: AsyncSession, blacklist_type: str, value: str,
) -> bool:
    """检查单个黑名单类型是否命中 (过期 / 软删 不算命中)."""
    if not value:
        return False
    bl = (await db.execute(
        select(RiskBlacklist).where(
            RiskBlacklist.blacklist_type == blacklist_type,
            RiskBlacklist.blacklist_value == value,
            RiskBlacklist.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not bl:
        return False
    # 过期黑名单不算命中
    if bl.expire_time and bl.expire_time < datetime.now():
        return False
    return True


async def check_blacklists(
    db: AsyncSession,
    user_id: str,
    card_id: Optional[str] = None,
    device_id: Optional[str] = None,
    ip: Optional[str] = None,
    id_card_hash: Optional[str] = None,
    to_card: Optional[str] = None,
) -> Optional[str]:
    """黑名单检查: 用户 > 银行卡号 > 收款卡号 > 设备指纹 > IP > 身份证号.

    短路逻辑: 一旦命中立刻返回, 不继续检查后续类型.

    Returns:
        命中的 blacklist_type 字符串 ("user"/"card"/"device"/"ip"/"id_card"), 或 None
    """
    # 优先级: 用户 > 银行卡号 > 收款卡号 > 设备指纹 > IP > 身份证号
    checks = [
        ("user", user_id),
        ("card", card_id),
        ("card", to_card),
        ("device", device_id),
        ("ip", ip),
        ("id_card", id_card_hash),
    ]
    for bl_type, value in checks:
        if await _check_one_blacklist(db, bl_type, value):
            logger.warning("撞黑名单: type=%s, value=%s", bl_type, value)
            return bl_type
    return None


# ============================================================
# 案件管理
# ============================================================

def _generate_case_id() -> str:
    """生成案件 ID (cas 前缀 + ulid)"""
    return f"cas{ulid.new().str.lower()}"


async def create_case(
    db: AsyncSession,
    assessment_id: str,
    user_id: str,
    decision: str,
) -> str:
    """建案: decision=人工审核→待审核, decision=拒绝→已拒绝.

    不 commit, 留给调用方合并到 1 个事务.

    Returns:
        新建的 case_id
    """
    # decision → case_status 映射
    if decision == "人工审核":
        case_status = "待审核"
    elif decision == "拒绝":
        case_status = "已拒绝"
    else:
        # 通过/标记 不建案, 调用方不应走到这里
        logger.warning("create_case 收到非预期 decision=%s, 跳过建案", decision)
        return ""

    case_id = _generate_case_id()
    case = RiskCase(
        case_id=case_id,
        assessment_id=assessment_id,
        user_id=user_id,
        case_status=case_status,
    )
    db.add(case)
    logger.info("建案: case_id=%s, assessment_id=%s, status=%s", case_id, assessment_id, case_status)
    return case_id


async def update_case_status(
    db: AsyncSession,
    case_id: str,
    new_status: str,
    operator: str = "admin",
) -> Optional[RiskCase]:
    """更新案件状态 (校验白名单 + 审计日志).

    1. 加载案件 (不存在返回 None, 由调用方抛 404)
    2. 校验状态流转是否合法 (_ALLOWED_CASE_TRANSITIONS)
    3. 更新状态 + reviewer + review_time
    4. 写审计日志
    5. commit + 返回 ORM 对象
    """
    case = (await db.execute(
        select(RiskCase).where(RiskCase.case_id == case_id)
    )).scalar_one_or_none()
    if not case:
        return None

    # 状态机校验
    current_status = case.case_status
    allowed_targets = _ALLOWED_CASE_TRANSITIONS.get(current_status, set())
    if new_status not in allowed_targets:
        raise HTTPException(
            status_code=400,
            detail=f"案件状态不能从 '{current_status}' 流转到 '{new_status}', "
                   f"合法的目标状态: {sorted(allowed_targets) or '(终态, 不可再改)'}",
        )

    # 更新
    case.case_status = new_status
    case.reviewer = operator
    case.review_time = datetime.now()

    # 审计日志
    await record_action(
        db, operator=operator, action_type="REVIEW_CASE",
        target_type="case", target_id=case.case_id,
        before_value={"case_status": current_status},
        after_value={"case_status": new_status},
        remark=f"审核 {new_status}",
    )

    await db.commit()
    logger.info("案件状态更新: case_id=%s, %s → %s, operator=%s", case_id, current_status, new_status, operator)
    return case


# ============================================================
# 案件超时自动关闭 (配合 scheduler 定时调用)
# ============================================================

async def auto_close_timeout_cases(db: AsyncSession, hours: Optional[int] = None) -> int:
    """把超过 N 小时的"待审核"案件自动改为"已关闭", 写 audit.

    场景: 案件一直没人审会积压, 自动关案避免越积越多.
    由 scheduler.py 每 15 分钟调一次, 也可手动 await.

    Args:
        hours: 超时阈值 (小时), None=用 settings.CASE_AUTO_CLOSE_HOURS (默认 24).
               设 0 关闭此功能.

    Returns:
        关闭的案件数.
    """
    if hours is None:
        hours = settings.CASE_AUTO_CLOSE_HOURS
    if hours <= 0:
        return 0

    threshold = datetime.now() - timedelta(hours=hours)
    cases = (await db.execute(
        select(RiskCase).where(
            RiskCase.case_status == "待审核",
            RiskCase.create_time < threshold,
        )
    )).scalars().all()

    for c in cases:
        c.case_status = "已关闭"
        c.reviewer = "system"
        c.review_time = datetime.now()
        c.review_comment = f"系统自动关闭: 待审核超过 {hours} 小时未处理"
        await record_action(
            db, operator="system", action_type="AUTO_CLOSE_CASE",
            target_type="case", target_id=c.case_id,
            before_value={"case_status": "待审核"},
            after_value={"case_status": "已关闭", "auto_close_hours": hours},
            remark=f"超时自动关闭, create_time={c.create_time.isoformat()}",
        )

    if cases:
        await db.commit()
        logger.info("auto_close_timeout_cases: 关闭 %d 个超时案件 (阈值 %dh)", len(cases), hours)
    return len(cases)
