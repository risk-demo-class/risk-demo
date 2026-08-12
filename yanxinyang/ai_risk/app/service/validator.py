# -*- coding: utf-8 -*-
"""校验服务 —— 对应教学宝典《第 10 章：横向越权防护》 + 2 层「validator.py · 6 校验」

## 攻击场景（宝典 10.1）
攻击者拿自己的 user_id + **别人的 order_id** 调风控，想让别人的订单被风控。

## 3 步组合校验（宝典 10.2 / 10.3）
| 步骤 | 检查                             | 错误码 |
|------|---------------------------------|--------|
| 1    | ensure_user_exists              | 404    |
| 2    | ensure_source_matches_event_type| 400    |
| 3    | ensure_order_belongs_to_user    | 403    |

## 字典驱动（宝典 10.4）
`_EVENT_SOURCE_VALIDATORS` —— 加新 event_type = 字典加一行，**不用改 if/else 链**。
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, Tuple

from app.framework import HTTPError
from app.models import EVENT_TYPES

logger = logging.getLogger("ai_risk.service.validator")

AMOUNT_TOLERANCE = 0.01


# ====================================================================== 字典驱动（宝典 10.4）
#: (event_types) -> (表名, 主键字段, 类型转换器, 中文名, 错误码)
_EVENT_SOURCE_VALIDATORS: Dict[Tuple[str, ...], Tuple[str, str, Optional[Callable[[str], Any]], str, int]] = {
    ("考试", "作业"): ("order_info", "order_id", None, "学习行为记录", 400),
    ("选课",): ("postsale", "postsale_id", None, "选课记录", 400),
    ("成绩申诉",): ("logistics_complaints_record", "record_id", int, "成绩申诉记录", 400),
}


def _resolve_source(event_type: str):
    for types, config in _EVENT_SOURCE_VALIDATORS.items():
        if event_type in types:
            return config
    return None


def source_table_of(event_type: str) -> str:
    config = _resolve_source(event_type)
    return config[0] if config else ""


# ====================================================================== 6 个 ensure_*
def ensure_event_type_valid(event_type: str) -> str:
    """① 事件类型必须合法（400）。"""
    if not event_type:
        raise HTTPError(400, "event_type 不能为空", "E_EVENT_TYPE_REQUIRED")
    if event_type not in EVENT_TYPES:
        raise HTTPError(400, f"不支持的 event_type: {event_type}（支持 {'/'.join(EVENT_TYPES)}）",
                        "E_EVENT_TYPE_INVALID")
    return event_type


def ensure_user_exists(db: Any, user_id: str) -> Dict[str, Any]:
    """② 用户必须存在（404）。"""
    if not user_id:
        raise HTTPError(400, "user_id 不能为空", "E_USER_ID_REQUIRED")
    user = db.fetch_one(
        "SELECT * FROM user_info WHERE user_id = ? AND deleted_at IS NULL", [user_id])
    if not user:
        raise HTTPError(404, f"用户不存在: {user_id}", "E_USER_NOT_FOUND")
    if user.get("user_status") == "注销":
        raise HTTPError(400, f"用户已注销: {user_id}", "E_USER_CLOSED")
    return user


def ensure_source_matches_event_type(db: Any, event_type: str, source_id: str) -> Dict[str, Any]:
    """③ source_id 必须在对应表存在（400）—— 字典驱动，不写 if/else 链。"""
    if not source_id:
        raise HTTPError(400, "source_id 不能为空", "E_SOURCE_ID_REQUIRED")
    config = _resolve_source(event_type)
    if config is None:
        raise HTTPError(400, f"event_type={event_type} 未注册 source 校验器", "E_SOURCE_VALIDATOR_MISSING")
    table, pk, caster, label, status = config
    value: Any = source_id
    if caster is not None:
        try:
            value = caster(source_id)
        except (TypeError, ValueError):
            raise HTTPError(status, f"{label} ID 类型不合法: {source_id}", "E_SOURCE_ID_TYPE") from None
    row = db.fetch_one(f'SELECT * FROM "{table}" WHERE "{pk}" = ?', [value])
    if not row:
        raise HTTPError(status, f"{label}不存在: {source_id}", "E_SOURCE_NOT_FOUND")
    return row


def ensure_order_belongs_to_user(db: Any, order_id: Optional[str], user_id: str) -> Optional[Dict[str, Any]]:
    """④ 订单的 user_id 必须 == 请求的 user_id（403）—— **横向越权的核心防线**。"""
    if not order_id:
        return None
    order = db.fetch_one(
        "SELECT * FROM order_info WHERE order_id = ? AND deleted_at IS NULL", [order_id])
    if not order:
        raise HTTPError(400, f"订单不存在: {order_id}", "E_ORDER_NOT_FOUND")
    if str(order.get("user_id")) != str(user_id):
        logger.warning("横向越权拦截: user_id=%s 试图操作 order_id=%s（实际归属 %s）",
                       user_id, order_id, order.get("user_id"))
        raise HTTPError(403, f"订单 {order_id} 不属于用户 {user_id}，拒绝访问",
                        "E_ORDER_NOT_OWNED")
    return order


def ensure_receive_id_belongs_to_user(db: Any, receive_id: Optional[str], user_id: str) -> Optional[Dict[str, Any]]:
    """⑤ 收货地址也必须属于该用户（403）—— 防止用别人地址算地址维度特征。"""
    if not receive_id:
        return None
    address = db.fetch_one(
        "SELECT * FROM user_address WHERE address_id = ? AND deleted_at IS NULL", [receive_id])
    if not address:
        raise HTTPError(400, f"收货地址不存在: {receive_id}", "E_ADDRESS_NOT_FOUND")
    if str(address.get("user_id")) != str(user_id):
        logger.warning("横向越权拦截: user_id=%s 试图使用 address_id=%s（实际归属 %s）",
                       user_id, receive_id, address.get("user_id"))
        raise HTTPError(403, f"收货地址 {receive_id} 不属于用户 {user_id}，拒绝访问",
                        "E_ADDRESS_NOT_OWNED")
    return address


def ensure_amount_consistent(order: Optional[Dict[str, Any]], amount: Any) -> None:
    """⑥ 请求携带 amount 时必须与订单金额一致（400）—— 防篡改金额绕规则。"""
    if amount is None or order is None:
        return
    try:
        claimed = float(amount)
    except (TypeError, ValueError):
        raise HTTPError(400, f"amount 不是合法数字: {amount}", "E_AMOUNT_INVALID") from None
    actual = float(order.get("total_amount") or 0)
    if abs(claimed - actual) > AMOUNT_TOLERANCE:
        raise HTTPError(400, f"amount={claimed} 与订单实际金额 {actual} 不一致，拒绝处理",
                        "E_AMOUNT_MISMATCH")


ENSURE_FUNCTIONS = (
    ("ensure_event_type_valid", "事件类型合法", 400),
    ("ensure_user_exists", "用户必须存在", 404),
    ("ensure_source_matches_event_type", "source_id 与 event_type 匹配", 400),
    ("ensure_order_belongs_to_user", "订单归属校验（防横向越权）", 403),
    ("ensure_receive_id_belongs_to_user", "地址归属校验（防横向越权）", 403),
    ("ensure_amount_consistent", "金额一致性校验（防篡改）", 400),
)


# ====================================================================== 组合入口
def validate_risk_check_request(db: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    """风控检查请求的完整校验（流水线步骤 1a）。

    返回归一化后的请求上下文，并附带校验轨迹 `_checks`（前端展示 7 步流水线用）。
    """
    checks = []

    event_type = ensure_event_type_valid(str(payload.get("event_type") or "").strip())
    checks.append({"step": "ensure_event_type_valid", "result": "通过", "detail": event_type})

    user_id = str(payload.get("user_id") or "").strip()
    user = ensure_user_exists(db, user_id)
    checks.append({"step": "ensure_user_exists", "result": "通过",
                   "detail": f"{user_id} / {user.get('user_name')}"})

    source_id = str(payload.get("source_id") or "").strip()
    source_row = ensure_source_matches_event_type(db, event_type, source_id)
    checks.append({"step": "ensure_source_matches_event_type", "result": "通过",
                   "detail": f"{source_table_of(event_type)}.{source_id}"})

    # source 表自带 user_id 的，先做一次归属核对（售后单/投诉记录）
    if "user_id" in source_row and str(source_row.get("user_id")) != user_id:
        raise HTTPError(403, f"{source_id} 不属于用户 {user_id}，拒绝访问", "E_SOURCE_NOT_OWNED")

    order_id = str(payload.get("order_id") or source_row.get("order_id") or "").strip() or None
    if event_type in ("考试", "作业"):
        order_id = source_id
    order = ensure_order_belongs_to_user(db, order_id, user_id)
    checks.append({"step": "ensure_order_belongs_to_user",
                   "result": "通过" if order else "跳过（无订单）",
                   "detail": order_id or "-"})

    receive_id = str(payload.get("receive_id") or "").strip() or None
    if not receive_id and order:
        receive_id = order.get("receive_id") or None
    address = ensure_receive_id_belongs_to_user(db, receive_id, user_id)
    checks.append({"step": "ensure_receive_id_belongs_to_user",
                   "result": "通过" if address else "跳过（无地址）",
                   "detail": receive_id or "-"})

    ensure_amount_consistent(order, payload.get("amount"))
    checks.append({"step": "ensure_amount_consistent",
                   "result": "通过" if payload.get("amount") is not None else "跳过（未传 amount）",
                   "detail": str(payload.get("amount") or "-")})

    return {
        "event_type": event_type,
        "user_id": user_id,
        "source_id": source_id,
        "order_id": order_id,
        "receive_id": receive_id,
        "user": user,
        "order": order,
        "address": address,
        "source_row": source_row,
        "client_ip": payload.get("client_ip") or "",
        "device_id": payload.get("device_id") or "",
        "remark": payload.get("remark") or "",
        "_checks": checks,
    }
