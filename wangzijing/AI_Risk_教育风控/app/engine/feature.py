"""教育行业 25 维风控特征工程。

特征键和顺序继续兼容原 XGBoost 接口，但含义与查询来源全部替换为
课程报名、学习进度、退费、认证和设备数据。三类事件始终返回完整 25 维。
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Course,
    DeviceBinding,
    IdentityVerification,
    LearningProgress,
    OrderInfo,
    RefundRequest,
)


FEATURE_NAMES: tuple[str, ...] = (
    "user_total_orders",
    "user_orders_30d",
    "user_orders_7d",
    "user_total_amount",
    "user_avg_order_amount",
    "user_max_order_amount",
    "user_refund_count",
    "user_postsale_count",
    "user_refund_rate",
    "user_postsale_rate",
    "user_refund_amount",
    "user_cancel_count",
    "user_complaint_count",
    "user_address_count",
    "order_total_amount",
    "order_item_count",
    "order_sku_count",
    "order_discount_amount",
    "order_discount_rate",
    "order_pay_interval_sec",
    "order_is_night",
    "order_category_count",
    "addr_total_count",
    "addr_province_count",
    "addr_is_new",
)

assert len(FEATURE_NAMES) == 25

VALID_ORDER_STATUSES = ("已支付", "已退费")
SUCCESS_REFUND_STATUSES = ("已通过",)


@dataclass(frozen=True)
class EducationEventContext:
    """特征、黑名单和快照落库共享的教育业务上下文。"""

    event_type: str
    source_id: str
    user_id: str
    order_id: Optional[str]
    course_id: Optional[str]
    device_id_hash: Optional[str]
    operation_time: datetime


async def resolve_event_context(
    db: AsyncSession,
    *,
    event_type: str,
    source_id: str,
    user_id: str,
) -> EducationEventContext:
    """把三类事件统一解析为订单、设备和操作时间上下文。"""
    order_id: Optional[str] = None
    course_id: Optional[str] = None
    device_id_hash: Optional[str] = None
    operation_time: Optional[datetime] = None

    if event_type == "课程报名":
        order_id = source_id
        row = (
            await db.execute(
                select(
                    OrderInfo.course_id,
                    OrderInfo.device_id_hash,
                    OrderInfo.create_time,
                ).where(OrderInfo.order_id == order_id)
            )
        ).first()
        if row:
            course_id = row.course_id
            device_id_hash = row.device_id_hash
            operation_time = row.create_time

    elif event_type == "退费申请":
        refund = (
            await db.execute(
                select(RefundRequest.order_id, RefundRequest.apply_time).where(
                    RefundRequest.refund_id == source_id
                )
            )
        ).first()
        if refund:
            order_id = refund.order_id
            operation_time = refund.apply_time
            order = (
                await db.execute(
                    select(OrderInfo.course_id, OrderInfo.device_id_hash).where(
                        OrderInfo.order_id == order_id
                    )
                )
            ).first()
            if order:
                course_id = order.course_id
                device_id_hash = order.device_id_hash

    elif event_type == "学历认证":
        operation_time = (
            await db.execute(
                select(IdentityVerification.submit_time).where(
                    IdentityVerification.verify_id == source_id
                )
            )
        ).scalar_one_or_none()

    if not device_id_hash:
        device_id_hash = (
            await db.execute(
                select(DeviceBinding.device_id_hash)
                .where(
                    DeviceBinding.user_id == user_id,
                    DeviceBinding.is_current.is_(True),
                )
                .order_by(DeviceBinding.last_seen.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    return EducationEventContext(
        event_type=event_type,
        source_id=source_id,
        user_id=user_id,
        order_id=order_id,
        course_id=course_id,
        device_id_hash=device_id_hash,
        operation_time=operation_time or datetime.now(),
    )


async def _scalar(db: AsyncSession, statement) -> float:
    value = (await db.execute(statement)).scalar()
    return float(value or 0)


def _clamp_rate(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(max(0.0, min(numerator / denominator, 1.0)), 4)


async def compute_user_features(
    db: AsyncSession,
    user_id: str,
    *,
    as_of: datetime | None = None,
) -> dict[str, float]:
    """计算 14 个用户特征；历史口径截止到事件发生时间，避免未来数据泄漏。"""
    as_of = as_of or datetime.now()
    valid_order_filter = (
        OrderInfo.user_id == user_id,
        OrderInfo.order_status.in_(VALID_ORDER_STATUSES),
        OrderInfo.create_time <= as_of,
    )

    total_orders = await _scalar(
        db, select(func.count()).select_from(OrderInfo).where(*valid_order_filter)
    )
    orders_30d = await _scalar(
        db,
        select(func.count()).select_from(OrderInfo).where(
            *valid_order_filter,
            OrderInfo.create_time >= as_of - timedelta(days=30),
        ),
    )
    orders_7d = await _scalar(
        db,
        select(func.count()).select_from(OrderInfo).where(
            *valid_order_filter,
            OrderInfo.create_time >= as_of - timedelta(days=7),
        ),
    )
    total_amount = await _scalar(
        db,
        select(func.coalesce(func.sum(OrderInfo.final_amount), 0))
        .select_from(OrderInfo)
        .where(*valid_order_filter),
    )
    max_amount = await _scalar(
        db,
        select(func.coalesce(func.max(OrderInfo.final_amount), 0))
        .select_from(OrderInfo)
        .where(*valid_order_filter),
    )

    refund_base = (
        RefundRequest.user_id == user_id,
        RefundRequest.apply_time <= as_of,
    )
    refund_count = await _scalar(
        db,
        select(func.count()).select_from(RefundRequest).where(
            *refund_base,
            RefundRequest.refund_status.in_(SUCCESS_REFUND_STATUSES),
        ),
    )
    refund_apply_count = await _scalar(
        db, select(func.count()).select_from(RefundRequest).where(*refund_base)
    )
    refund_amount = await _scalar(
        db,
        select(func.coalesce(func.sum(RefundRequest.refund_amount), 0))
        .select_from(RefundRequest)
        .where(
            *refund_base,
            RefundRequest.refund_status.in_(SUCCESS_REFUND_STATUSES),
        ),
    )
    cancel_count = await _scalar(
        db,
        select(func.count()).select_from(OrderInfo).where(
            OrderInfo.user_id == user_id,
            OrderInfo.order_status == "已取消",
            OrderInfo.create_time <= as_of,
        ),
    )
    verification_failures = await _scalar(
        db,
        select(func.count()).select_from(IdentityVerification).where(
            IdentityVerification.user_id == user_id,
            IdentityVerification.verify_result == "失败",
            IdentityVerification.submit_time <= as_of,
        ),
    )
    linked_devices = await _scalar(
        db,
        select(func.count(func.distinct(DeviceBinding.device_id_hash)))
        .select_from(DeviceBinding)
        .where(
            DeviceBinding.user_id == user_id,
            DeviceBinding.first_seen <= as_of,
        ),
    )

    return {
        "user_total_orders": total_orders,
        "user_orders_30d": orders_30d,
        "user_orders_7d": orders_7d,
        "user_total_amount": total_amount,
        "user_avg_order_amount": round(total_amount / total_orders, 2) if total_orders else 0.0,
        "user_max_order_amount": max_amount,
        "user_refund_count": refund_count,
        "user_postsale_count": refund_apply_count,
        "user_refund_rate": _clamp_rate(refund_count, total_orders),
        "user_postsale_rate": _clamp_rate(refund_apply_count, total_orders),
        "user_refund_amount": refund_amount,
        "user_cancel_count": cancel_count,
        "user_complaint_count": verification_failures,
        "user_address_count": linked_devices,
    }


async def compute_order_features(
    db: AsyncSession,
    context: EducationEventContext,
) -> dict[str, float]:
    """计算 8 个当前订单/事件特征；认证事件没有订单时金额维度为 0。"""
    total_amount = 0.0
    original_amount = 0.0
    discount_amount = 0.0
    item_count = 0.0
    sku_count = 0.0
    learning_minutes = 0.0

    if context.order_id:
        order = (
            await db.execute(
                select(
                    OrderInfo.total_amount,
                    OrderInfo.discount_amount,
                    OrderInfo.final_amount,
                ).where(OrderInfo.order_id == context.order_id)
            )
        ).first()
        if order:
            original_amount = float(order.total_amount or 0)
            discount_amount = float(order.discount_amount or 0)
            total_amount = float(order.final_amount or 0)
            item_count = 1.0
            sku_count = 1.0
        learning_minutes = await _scalar(
            db,
            select(func.coalesce(func.sum(LearningProgress.total_minutes), 0))
            .select_from(LearningProgress)
            .where(LearningProgress.order_id == context.order_id),
        )

    category_count = await _scalar(
        db,
        select(func.count(func.distinct(Course.category)))
        .select_from(OrderInfo)
        .join(Course, OrderInfo.course_id == Course.course_id)
        .where(
            OrderInfo.user_id == context.user_id,
            OrderInfo.order_status.in_(VALID_ORDER_STATUSES),
            OrderInfo.create_time <= context.operation_time,
        ),
    )
    hour = context.operation_time.hour

    return {
        "order_total_amount": total_amount,
        "order_item_count": item_count,
        "order_sku_count": sku_count,
        "order_discount_amount": discount_amount,
        "order_discount_rate": round(discount_amount / original_amount, 4) if original_amount else 0.0,
        # 旧键保留兼容；教育语义为发起退费前累计学习分钟数。
        "order_pay_interval_sec": learning_minutes,
        "order_is_night": 1.0 if 1 <= hour < 5 else 0.0,
        "order_category_count": category_count,
    }


async def compute_device_features(
    db: AsyncSession,
    context: EducationEventContext,
) -> dict[str, float]:
    """计算 3 个设备特征，继续沿用历史 ``addr_*`` 键名。"""
    active_devices = await _scalar(
        db,
        select(func.count(func.distinct(DeviceBinding.device_id_hash)))
        .select_from(DeviceBinding)
        .where(
            DeviceBinding.user_id == context.user_id,
            DeviceBinding.is_current.is_(True),
            DeviceBinding.first_seen <= context.operation_time,
        ),
    )
    device_user_count = 0.0
    is_new = 0.0
    if context.device_id_hash:
        device_user_count = await _scalar(
            db,
            select(func.count(func.distinct(DeviceBinding.user_id)))
            .select_from(DeviceBinding)
            .where(
                DeviceBinding.device_id_hash == context.device_id_hash,
                DeviceBinding.is_current.is_(True),
                DeviceBinding.first_seen <= context.operation_time,
            ),
        )
        first_seen = (
            await db.execute(
                select(func.min(DeviceBinding.first_seen)).where(
                    DeviceBinding.device_id_hash == context.device_id_hash,
                    DeviceBinding.first_seen <= context.operation_time,
                )
            )
        ).scalar_one_or_none()
        if first_seen is not None:
            age = context.operation_time - first_seen
            is_new = 1.0 if timedelta(0) <= age < timedelta(days=7) else 0.0

    return {
        "addr_total_count": active_devices,
        "addr_province_count": device_user_count,
        "addr_is_new": is_new,
    }


async def compute_all_features(
    db: AsyncSession,
    *,
    user_id: str,
    event_type: str,
    source_id: str,
    event_context: EducationEventContext | None = None,
) -> dict[str, float]:
    """计算并按固定顺序返回完整 25 维教育风控特征。"""
    context = event_context or await resolve_event_context(
        db,
        event_type=event_type,
        source_id=source_id,
        user_id=user_id,
    )
    features: dict[str, float] = {}
    features.update(await compute_user_features(db, user_id, as_of=context.operation_time))
    features.update(await compute_order_features(db, context))
    features.update(await compute_device_features(db, context))
    return {name: float(features.get(name, 0.0)) for name in FEATURE_NAMES}


if __name__ == "__main__":
    descriptions = {
        "user_complaint_count": "身份认证失败次数",
        "user_address_count": "用户关联设备数",
        "order_pay_interval_sec": "退费前学习分钟数（兼容旧键）",
        "addr_province_count": "当前设备关联用户数（兼容旧键）",
        "addr_is_new": "当前设备是否首次出现不足7天（兼容旧键）",
    }
    print("教育行业 25 维特征（顺序与训练/推理完全一致）：")
    for index, feature_name in enumerate(FEATURE_NAMES, start=1):
        print(f"{index:>2}. {feature_name:<28} {descriptions.get(feature_name, '')}")
