"""决策接口: 包装 process_event 为 REST API, 并暴露规则清单.

与基线 AI_Risk 的 decision.py 对齐: 复用 validate -> enrich -> run_risk_check
调度骨架, 此处薄封装 app.service.event.process_event 纯函数.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# 确保项目根在 sys.path (兼容 python -m app / 直接 uvicorn 启动)
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import BANK_EVENT_TYPES, BLACKLIST_TYPE_KEYS  # noqa: E402
from app.service.event import process_event  # noqa: E402
from app.service.validator import DISPATCH_TABLE, dispatch_rules  # noqa: E402

router = APIRouter(prefix="/api", tags=["decision"])


# ============================================================
# 请求/响应模型
# ============================================================
class RiskEventIn(BaseModel):
    """决策请求体, 字段对齐 TxnFlow / process_event event dict."""
    txn_id: Optional[str] = None
    txn_type: str = Field(..., description="业务事件类型")
    cust_id: str = Field(default="C000000")
    amount: float = 0.0
    counterparty_id: Optional[str] = None
    device_fingerprint: Optional[str] = None
    ip_addr: Optional[str] = None
    geo_province: Optional[str] = None
    geo_city: Optional[str] = None
    txn_time: Optional[str] = None
    # 特征扩展位 (注入 feature 计算, 如 f_counterparty_cnt / credit_query_30d 等)
    f_counterparty_cnt: Optional[int] = None
    credit_query_30d: Optional[int] = None
    multi_loan_platforms: Optional[int] = None
    login_fail_5m: Optional[int] = None
    geo_ip_deviation: Optional[bool] = None
    # 黑名单: [[type, id], ...] 例如 [["account","C200001"]]
    blacklist: Optional[list[list[str]]] = None


class RuleMeta(BaseModel):
    rule: str
    event_types: list[str]


# ============================================================
# 接口
# ============================================================
@router.post("/decision")
def post_decision(event: RiskEventIn) -> dict:
    """执行一笔银行风控事件的决策流水线, 返回五级决策 + 命中规则 + 11维特征."""
    if event.txn_type not in BANK_EVENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"未知业务事件类型: {event.txn_type}, 合法值={list(BANK_EVENT_TYPES)}",
        )

    event_dict = event.model_dump(exclude_none=True)
    # blacklist: [[type,id]] -> {(type,id)}
    bl: Optional[set[tuple[str, str]]] = None
    if event.blacklist:
        bl = {(b[0], b[1]) for b in event.blacklist if len(b) == 2}

    try:
        result = process_event(event_dict, blacklist=bl)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return result


@router.get("/rules")
def get_rules() -> dict:
    """暴露全部规则与各事件类型的路由关系 (供规则命中看板同源展示)."""
    # 反向索引: rule -> 适用事件类型
    rule_to_events: dict[str, list[str]] = {}
    for txn_type, rules in DISPATCH_TABLE.items():
        for r in rules:
            rule_to_events.setdefault(r.__name__, []).append(txn_type)

    # 规则基本信息 + 决策说明
    rule_docs = {
        "rule_blacklist_hit": {
            "name": "黑名单命中", "decision": "freeze", "severity": 4,
            "message": "账户/设备/IP/证件任一命中即一票否决冻结",
        },
        "rule_transfer_amt": {
            "name": "转账金额阈值", "decision": "report/review", "severity": "2/3",
            "message": ">=20万大额报送, >=5万模型复核",
        },
        "rule_transfer_peer_cnt": {
            "name": "分散转入对手数", "decision": "review", "severity": 2,
            "message": "近1h对手数>=10疑似资金归集",
        },
        "rule_geo_ip_deviation": {
            "name": "地理/IP突变", "decision": "review", "severity": 2,
            "message": "异地登录或盗卡",
        },
        "rule_loan_multi": {
            "name": "多头借贷/过度查询", "decision": "review/reject", "severity": 2,
            "message": "征信查询>=10或平台数>=5借名骗贷",
        },
        "rule_login_fail": {
            "name": "登录失败频控", "decision": "freeze", "severity": 2,
            "message": "5分钟失败>=5疑似撞库",
        },
        "rule_transfer_disperse": {
            "name": "分散转入集中转出", "decision": "review", "severity": 2,
            "message": "对手数高+单笔中高金额疑似洗钱",
        },
        "rule_abnormal_hour": {
            "name": "异常时段交易", "decision": "review", "severity": 1,
            "message": "0~6点夜间交易高发盗卡/电诈",
        },
    }

    rules = [
        {
            "rule": rname,
            "name": rule_docs.get(rname, {}).get("name", rname),
            "decision": rule_docs.get(rname, {}).get("decision", ""),
            "severity": rule_docs.get(rname, {}).get("severity", ""),
            "message": rule_docs.get(rname, {}).get("message", ""),
            "event_types": ets,
        }
        for rname, ets in rule_to_events.items()
    ]

    return {
        "blacklist_types": list(BLACKLIST_TYPE_KEYS),
        "bank_event_types": list(BANK_EVENT_TYPES),
        "rules": rules,
        "dispatch_table": {k: [r.__name__ for r in v] for k, v in DISPATCH_TABLE.items()},
    }


@router.get("/rules/list")
def get_rule_list() -> list[RuleMeta]:
    """轻量规则清单 (仅 rule + 适用事件类型), 供前端下拉/校验使用."""
    rule_to_events: dict[str, list[str]] = {}
    for txn_type, rules in DISPATCH_TABLE.items():
        for r in rules:
            rule_to_events.setdefault(r.__name__, []).append(txn_type)
    return [RuleMeta(rule=k, event_types=v) for k, v in rule_to_events.items()]
