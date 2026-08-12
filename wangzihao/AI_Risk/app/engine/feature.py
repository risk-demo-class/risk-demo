"""制造业设备经销商风控的固定 25 维特征工程。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CrossRegionReport, Dealer, Device, PurchaseOrder, WarrantyClaim


HIGH_VALUE_CLAIM_AMOUNT = 100_000.0
PAYMENT_TERM_SECONDS = {
    "预付": 0.0,
    "账期30天": 30.0 * 24 * 60 * 60,
    "账期60天": 60.0 * 24 * 60 * 60,
}

USER_FEATURE_KEYS = (
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
)
ORDER_FEATURE_KEYS = (
    "order_total_amount",
    "order_item_count",
    "order_sku_count",
    "order_discount_amount",
    "order_discount_rate",
    "order_pay_interval_sec",
    "order_is_night",
    "order_category_count",
)
ADDRESS_FEATURE_KEYS = (
    "addr_total_count",
    "addr_province_count",
    "addr_is_new",
)
FEATURE_KEYS = USER_FEATURE_KEYS + ORDER_FEATURE_KEYS + ADDRESS_FEATURE_KEYS


async def _count(model, db: AsyncSession, **filters) -> float:
    """SELECT COUNT(*) with equality filters, returning a numeric zero on no rows."""
    stmt = select(func.count()).select_from(model)
    for col, value in filters.items():
        stmt = stmt.where(getattr(model, col) == value)
    return float((await db.execute(stmt)).scalar() or 0)


async def _sum(model, col_name: str, db: AsyncSession, **filters) -> float:
    """SELECT SUM(column) with equality filters, returning zero on no rows."""
    column = getattr(model, col_name)
    stmt = select(func.coalesce(func.sum(column), 0)).select_from(model)
    for col, value in filters.items():
        stmt = stmt.where(getattr(model, col) == value)
    return float((await db.execute(stmt)).scalar() or 0)


def _safe_ratio(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _json_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _region_matches(expected: str | None, actual: str | None) -> bool:
    if not expected or not actual:
        return False
    expected_value = expected.strip().lower()
    actual_value = actual.strip().lower()
    return actual_value == expected_value or actual_value.startswith(expected_value)


def _age_seconds(factory_at: date | None, event_time: datetime | None) -> float:
    if not factory_at or not event_time:
        return 0.0
    factory_time = datetime.combine(factory_at, time.min)
    return max(float((event_time - factory_time).total_seconds()), 0.0)


@dataclass(frozen=True)
class _BusinessEventContext:
    kind: str
    source_id: str
    dealer_id: str
    create_time: datetime | None = None
    amount: float = 0.0
    items: Any = None
    payment_term: str | None = None
    device_id: str | None = None
    factory_at: date | None = None
    photos: Any = None
    expected_region: str | None = None
    actual_region: str | None = None


async def _resolve_business_event(
    db: AsyncSession,
    source_id: str | None,
) -> _BusinessEventContext | None:
    """Resolve the Step 3 source ID against the three manufacturing source tables."""
    if not source_id:
        return None

    purchase = (await db.execute(
        select(
            PurchaseOrder.po_id,
            PurchaseOrder.dealer_id,
            PurchaseOrder.total_amount,
            PurchaseOrder.items,
            PurchaseOrder.payment_term,
            PurchaseOrder.ship_to,
            PurchaseOrder.create_time,
            Dealer.region,
        )
        .join(Dealer, Dealer.dealer_id == PurchaseOrder.dealer_id)
        .where(PurchaseOrder.po_id == source_id)
    )).first()
    if purchase:
        return _BusinessEventContext(
            kind="purchase_order",
            source_id=purchase.po_id,
            dealer_id=purchase.dealer_id,
            create_time=purchase.create_time,
            amount=float(purchase.total_amount or 0),
            items=purchase.items,
            payment_term=purchase.payment_term,
            expected_region=purchase.region,
            actual_region=purchase.ship_to,
        )

    claim = (await db.execute(
        select(
            WarrantyClaim.claim_id,
            WarrantyClaim.dealer_id,
            WarrantyClaim.claim_amount,
            WarrantyClaim.photos,
            WarrantyClaim.create_time,
            Device.device_id,
            Device.factory_at,
            Dealer.region,
        )
        .join(Device, Device.device_id == WarrantyClaim.device_id)
        .join(Dealer, Dealer.dealer_id == WarrantyClaim.dealer_id)
        .where(WarrantyClaim.claim_id == source_id)
    )).first()
    if claim:
        return _BusinessEventContext(
            kind="warranty_claim",
            source_id=claim.claim_id,
            dealer_id=claim.dealer_id,
            create_time=claim.create_time,
            amount=float(claim.claim_amount or 0),
            device_id=claim.device_id,
            factory_at=claim.factory_at,
            photos=claim.photos,
            expected_region=claim.region,
            actual_region=claim.region,
        )

    report = (await db.execute(
        select(
            CrossRegionReport.report_id,
            CrossRegionReport.device_id,
            CrossRegionReport.expected_region,
            CrossRegionReport.actual_region,
            CrossRegionReport.create_time,
            Device.dealer_id,
            Device.factory_at,
        )
        .join(Device, Device.device_id == CrossRegionReport.device_id)
        .where(CrossRegionReport.report_id == source_id)
    )).first()
    if report:
        return _BusinessEventContext(
            kind="cross_region_report",
            source_id=report.report_id,
            dealer_id=report.dealer_id or "",
            create_time=report.create_time,
            device_id=report.device_id,
            factory_at=report.factory_at,
            expected_region=report.expected_region,
            actual_region=report.actual_region,
        )
    return None


async def _dealer_region_history(
    db: AsyncSession,
    dealer_id: str,
) -> tuple[str | None, list[str], list[tuple[str, str]]]:
    authorized_region = (await db.execute(
        select(Dealer.region).where(Dealer.dealer_id == dealer_id)
    )).scalar_one_or_none()
    ship_regions = list((await db.execute(
        select(PurchaseOrder.ship_to).where(PurchaseOrder.dealer_id == dealer_id)
    )).scalars().all())
    report_regions = [
        (row.expected_region, row.actual_region)
        for row in (await db.execute(
            select(CrossRegionReport.expected_region, CrossRegionReport.actual_region)
            .join(Device, Device.device_id == CrossRegionReport.device_id)
            .where(Device.dealer_id == dealer_id)
        )).all()
    ]
    return authorized_region, ship_regions, report_regions


async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """Compute the 14 dealer-level slots while preserving legacy user_* keys."""
    now = datetime.now()
    purchase_stats = (await db.execute(
        select(
            func.count(PurchaseOrder.po_id),
            func.coalesce(func.sum(PurchaseOrder.total_amount), 0),
            func.coalesce(func.avg(PurchaseOrder.total_amount), 0),
            func.coalesce(func.max(PurchaseOrder.total_amount), 0),
            func.sum(case((PurchaseOrder.create_time >= now - timedelta(days=30), 1), else_=0)),
            func.sum(case((PurchaseOrder.create_time >= now - timedelta(days=7), 1), else_=0)),
        ).where(PurchaseOrder.dealer_id == user_id)
    )).one()
    total_orders = float(purchase_stats[0] or 0)

    claim_stats = (await db.execute(
        select(
            func.count(WarrantyClaim.claim_id),
            func.sum(case((WarrantyClaim.claim_amount >= HIGH_VALUE_CLAIM_AMOUNT, 1), else_=0)),
            func.coalesce(func.sum(WarrantyClaim.claim_amount), 0),
        ).where(WarrantyClaim.dealer_id == user_id)
    )).one()
    total_claims = float(claim_stats[0] or 0)
    high_value_claims = float(claim_stats[1] or 0)

    device_count = await _count(Device, db, dealer_id=user_id)
    cross_report_count = float((await db.execute(
        select(func.count(CrossRegionReport.report_id))
        .select_from(CrossRegionReport)
        .join(Device, Device.device_id == CrossRegionReport.device_id)
        .where(Device.dealer_id == user_id)
    )).scalar() or 0)

    authorized_at = (await db.execute(
        select(Dealer.authorized_at).where(Dealer.dealer_id == user_id)
    )).scalar_one_or_none()
    cooperation_days = (
        float(max((date.today() - authorized_at).days, 0)) if authorized_at else 0.0
    )

    authorized_region, ship_regions, report_regions = await _dealer_region_history(db, user_id)
    active_regions = {value for value in [authorized_region, *ship_regions] if value}
    for expected_region, actual_region in report_regions:
        if expected_region:
            active_regions.add(expected_region)
        if actual_region:
            active_regions.add(actual_region)

    return {
        "user_total_orders": total_orders,
        "user_orders_30d": float(purchase_stats[4] or 0),
        "user_orders_7d": float(purchase_stats[5] or 0),
        "user_total_amount": float(purchase_stats[1] or 0),
        "user_avg_order_amount": round(float(purchase_stats[2] or 0), 2),
        "user_max_order_amount": float(purchase_stats[3] or 0),
        "user_refund_count": high_value_claims,
        "user_postsale_count": total_claims,
        "user_refund_rate": _safe_ratio(high_value_claims, total_claims),
        "user_postsale_rate": _safe_ratio(total_claims, device_count),
        "user_refund_amount": float(claim_stats[2] or 0),
        "user_cancel_count": cooperation_days,
        "user_complaint_count": cross_report_count,
        "user_address_count": float(len(active_regions)),
    }


async def compute_order_features(
    db: AsyncSession,
    order_id: str | None,
    *,
    event_context: _BusinessEventContext | None = None,
) -> dict[str, float]:
    """Compute all eight current-event slots for purchase, warranty, or diversion."""
    context = event_context or await _resolve_business_event(db, order_id)
    features = {name: 0.0 for name in ORDER_FEATURE_KEYS}
    if context is None:
        return features

    features["order_total_amount"] = float(context.amount)
    features["order_is_night"] = (
        1.0 if context.create_time and 0 <= context.create_time.hour < 6 else 0.0
    )

    if context.kind == "purchase_order":
        items = _json_list(context.items)
        quantities = []
        models = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                quantities.append(float(item.get("quantity", 0) or 0))
            except (TypeError, ValueError):
                quantities.append(0.0)
            if item.get("model"):
                models.add(str(item["model"]))

        average_amount = float((await db.execute(
            select(func.coalesce(func.avg(PurchaseOrder.total_amount), 0))
            .where(PurchaseOrder.dealer_id == context.dealer_id)
        )).scalar() or 0)
        excess = max(context.amount - average_amount, 0.0)
        features.update({
            "order_item_count": float(len(items)),
            "order_sku_count": float(sum(quantities)),
            "order_discount_amount": excess,
            "order_discount_rate": _safe_ratio(excess, average_amount),
            "order_pay_interval_sec": PAYMENT_TERM_SECONDS.get(context.payment_term or "", 0.0),
            "order_category_count": float(len(models)),
        })

    elif context.kind == "warranty_claim":
        average_amount = float((await db.execute(
            select(func.coalesce(func.avg(WarrantyClaim.claim_amount), 0))
            .where(WarrantyClaim.dealer_id == context.dealer_id)
        )).scalar() or 0)
        excess = max(context.amount - average_amount, 0.0)
        device_claim_count = await _count(
            WarrantyClaim, db, device_id=context.device_id,
        ) if context.device_id else 0.0
        features.update({
            "order_item_count": 1.0,
            "order_sku_count": device_claim_count,
            "order_discount_amount": excess,
            "order_discount_rate": _safe_ratio(excess, average_amount),
            "order_pay_interval_sec": _age_seconds(context.factory_at, context.create_time),
            "order_category_count": float(len(_json_list(context.photos))),
        })

    elif context.kind == "cross_region_report":
        mismatch = 0.0 if _region_matches(context.expected_region, context.actual_region) else 1.0
        device_report_count = await _count(
            CrossRegionReport, db, device_id=context.device_id,
        ) if context.device_id else 0.0
        features.update({
            "order_item_count": 1.0,
            "order_sku_count": device_report_count,
            "order_discount_amount": mismatch,
            "order_discount_rate": mismatch,
            "order_pay_interval_sec": _age_seconds(context.factory_at, context.create_time),
            "order_category_count": 1.0 if mismatch == 0 else 2.0,
        })

    return {name: float(features.get(name, 0) or 0) for name in ORDER_FEATURE_KEYS}


async def compute_address_features(
    db: AsyncSession,
    user_id: str,
    receive_id: str | None = None,
    *,
    event_context: _BusinessEventContext | None = None,
) -> dict[str, float]:
    """Compute three authorized/delivery/actual-region risk slots."""
    authorized_region, ship_regions, report_regions = await _dealer_region_history(db, user_id)
    touch_count = (1 if authorized_region else 0) + len(ship_regions) + len(report_regions)

    abnormal_regions = {
        region for region in ship_regions
        if region and not _region_matches(authorized_region, region)
    }
    for expected_region, actual_region in report_regions:
        if actual_region and not _region_matches(expected_region, actual_region):
            abnormal_regions.add(actual_region)

    context = event_context
    expected_region = context.expected_region if context else authorized_region
    actual_region = context.actual_region if context else receive_id
    current_is_abnormal = (
        1.0 if actual_region and not _region_matches(expected_region, actual_region) else 0.0
    )
    return {
        "addr_total_count": float(touch_count),
        "addr_province_count": float(len(abnormal_regions)),
        "addr_is_new": current_is_abnormal,
    }


async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    order_id: str | None = None,
    receive_id: str | None = None,
) -> dict[str, float]:
    """Return the complete ordered 25-dimensional manufacturing feature vector."""
    event_context = await _resolve_business_event(db, order_id)
    values = await compute_user_features(db, user_id)
    values.update(await compute_order_features(
        db, order_id, event_context=event_context,
    ))
    values.update(await compute_address_features(
        db, user_id, receive_id, event_context=event_context,
    ))
    return {name: float(values.get(name, 0) or 0) for name in FEATURE_KEYS}
