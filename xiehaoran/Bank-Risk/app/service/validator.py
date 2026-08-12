"""
银行风控系统 - 业务校验服务 (必须自建)

职责:
  1. 交易校验规则链 (Rule Chain): 对一笔交易按事件类型依次执行黑名单/Hit/金额/频率/地理
     规则, 聚合为决策 (pass/review/reject/freeze/report) 与触发的风险事件.
  2. 事件分发 (Dispatch): 根据 event_type 路由到对应规则集合, 兼容基线
     RiskCheckRequest 调度模式 (可复用基线 decision.py 编排, 但规则与枚举为银行自建).

设计对齐业务说明文档边界:
  - 复用: 决策流水线 / 规则引擎 / 双轨融合 / 一票否决 框架
  - 自建: 银行 event_type 枚举 / 黑名单类型 / 监管报送 逻辑

⚠ 说明: 本模块为纯业务校验编排, 不依赖 DB 连接即可运行规则链 (依赖注入 txn/blacklist 供数).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from app.config import (
    BANK_EVENT_TYPES,
    BANK_RULE_THRESHOLDS,
    BLACKLIST_TYPE_KEYS,
    DECISION_FREEZE,
    DECISION_PASS,
    DECISION_REJECT,
    DECISION_REPORT,
    DECISION_REVIEW,
    VETO_SEVERITY,
)


# ============================================================
# 数据结构
# ============================================================
@dataclass
class TxnContext:
    """进入规则链的交易上下文 (由上游 event 调度填充)."""
    txn_id: str
    cust_id: str
    txn_type: str                 # transfer/loan_apply/card_txn/repay/login
    amount: float = 0.0
    counterparty_id: Optional[str] = None
    device_fingerprint: Optional[str] = None
    ip_addr: Optional[str] = None
    geo_province: Optional[str] = None
    geo_city: Optional[str] = None
    # 由 feature/query 注入的扩展特征
    peer_cnt_1h: int = 0
    login_fail_5m: int = 0
    geo_ip_deviation: bool = False
    credit_query_30d: int = 0
    multi_loan_platforms: int = 0
    txn_time: Optional[Any] = None     # datetime, 供 rule_abnormal_hour 判断时段
    f_ext: dict = field(default_factory=dict)


@dataclass
class RuleResult:
    rule: str
    hit: bool
    severity: int = 1
    decision: str = DECISION_PASS
    message: str = ""


@dataclass
class ValidateResult:
    txn_id: str
    decision: str
    triggered_rules: list[RuleResult] = field(default_factory=list)
    risk_events: list[dict] = field(default_factory=list)   # 待写入 risk_event_biz
    need_report: bool = False

    @property
    def is_veto(self) -> bool:
        return any(r.severity >= VETO_SEVERITY for r in self.triggered_rules)


# ============================================================
# 规则链 (纯函数, 便于单元测试)
# ============================================================
def rule_blacklist_hit(ctx: TxnContext, blacklist: set[tuple[str, str]]) -> RuleResult:
    """黑名单命中: 账户/设备/IP/证件 任一命中即一票否决冻结."""
    checks = [
        ("account", ctx.cust_id),
        ("account", ctx.counterparty_id),
        ("device", ctx.device_fingerprint),
        ("ip", ctx.ip_addr),
    ]
    for btype, bid in checks:
        if bid and (btype, bid) in blacklist:
            return RuleResult(
                rule="blacklist_hit", hit=True, severity=VETO_SEVERITY,
                decision=DECISION_FREEZE,
                message=f"命中{btype}黑名单: {bid}",
            )
    return RuleResult(rule="blacklist_hit", hit=False)


def rule_transfer_amt(ctx: TxnContext) -> RuleResult:
    """转账金额: >=20万大额报送, >=5万进模型复核."""
    th = BANK_RULE_THRESHOLDS["transfer"]
    if ctx.amount >= th["amt_report"]:
        return RuleResult(
            rule="transfer_amt_report", hit=True, severity=3,
            decision=DECISION_REPORT,
            message=f"单笔转账 {ctx.amount} >= {th['amt_report']} 大额报送",
        )
    if ctx.amount >= th["amt_suspect"]:
        return RuleResult(
            rule="transfer_amt_suspect", hit=True, severity=2,
            decision=DECISION_REVIEW,
            message=f"单笔转账 {ctx.amount} >= {th['amt_suspect']} 进入模型复核",
        )
    return RuleResult(rule="transfer_amt_suspect", hit=False)


def rule_transfer_peer_cnt(ctx: TxnContext) -> RuleResult:
    """转账分散转入/集中转出: 近1h对手数阈值."""
    th = BANK_RULE_THRESHOLDS["transfer"]
    if ctx.peer_cnt_1h >= th["peer_cnt_1h"]:
        return RuleResult(
            rule="transfer_peer_cnt", hit=True, severity=2,
            decision=DECISION_REVIEW,
            message=f"近1h交易对手 {ctx.peer_cnt_1h} >= {th['peer_cnt_1h']} 疑似资金归集",
        )
    return RuleResult(rule="transfer_peer_cnt", hit=False)


def rule_geo_ip_deviation(ctx: TxnContext) -> RuleResult:
    """地理/IP 突变: 异地登录或盗卡."""
    if ctx.geo_ip_deviation:
        return RuleResult(
            rule="geo_ip_deviation", hit=True, severity=2,
            decision=DECISION_REVIEW,
            message="交易地理/IP 与历史基线偏离",
        )
    return RuleResult(rule="geo_ip_deviation", hit=False)


def rule_loan_multi(ctx: TxnContext) -> RuleResult:
    """多头借贷 / 过度查询: 贷前审查."""
    th = BANK_RULE_THRESHOLDS["loan_apply"]
    if ctx.credit_query_30d >= th["credit_query_30d"]:
        return RuleResult(
            rule="loan_credit_query", hit=True, severity=2,
            decision=DECISION_REVIEW,
            message=f"30天征信查询 {ctx.credit_query_30d} >= {th['credit_query_30d']} 多头借贷",
        )
    if ctx.multi_loan_platforms >= th["multi_loan_platforms"]:
        return RuleResult(
            rule="loan_multi_platform", hit=True, severity=2,
            decision=DECISION_REJECT,
            message=f"借贷平台数 {ctx.multi_loan_platforms} >= {th['multi_loan_platforms']} 借名骗贷",
        )
    return RuleResult(rule="loan_multi_platform", hit=False)


def rule_login_fail(ctx: TxnContext) -> RuleResult:
    """登录失败频控: 账户盗用防护."""
    th = BANK_RULE_THRESHOLDS["login"]
    if ctx.login_fail_5m >= th["fail_5m"]:
        return RuleResult(
            rule="login_fail_5m", hit=True, severity=2,
            decision=DECISION_FREEZE,
            message=f"5分钟登录失败 {ctx.login_fail_5m} >= {th['fail_5m']} 疑似撞库",
        )
    return RuleResult(rule="login_fail_5m", hit=False)


def rule_transfer_disperse(ctx: TxnContext) -> RuleResult:
    """分散转入集中转出: 近1h对手数高 + 单笔金额中等, 疑似资金归集/过渡性洗钱.

    复用 f_counterparty_cnt / peer_cnt_1h 语义; 与 rule_transfer_peer_cnt 的区别:
      - rule_transfer_peer_cnt 关注对手数绝对阈值 (>=10) -> review
      - 本规则额外要求单笔金额处于中高区间 (>=5万 且 <20万), 体现「分散小额转入、集中中转」形态
    """
    th = BANK_RULE_THRESHOLDS["transfer"]
    if (ctx.peer_cnt_1h >= th["peer_cnt_1h"]) and (th["amt_suspect"] <= ctx.amount < th["amt_report"]):
        return RuleResult(
            rule="transfer_disperse", hit=True, severity=2,
            decision=DECISION_REVIEW,
            message=f"近1h对手 {ctx.peer_cnt_1h} 且单笔 {ctx.amount:.0f} 处于"
                    f"[{th['amt_suspect']:.0f},{th['amt_report']:.0f}) 疑似分散转入集中转出",
        )
    return RuleResult(rule="transfer_disperse", hit=False)


def rule_abnormal_hour(ctx: TxnContext) -> RuleResult:
    """异常时段交易: 0~6 点夜间交易, 与正常作息偏离, 盗卡/电诈高发.

    txn_time 由上游 event 注入 TxnContext.txn_time (datetime); 缺失则不触发.
    """
    txn_time = getattr(ctx, "txn_time", None)
    if txn_time is not None and hasattr(txn_time, "hour"):
        if 0 <= txn_time.hour <= 6:
            return RuleResult(
                rule="abnormal_hour", hit=True, severity=1,
                decision=DECISION_REVIEW,
                message=f"交易时段 {txn_time.hour:02d}:00 处于夜间 0~6 点异常窗口",
            )
    return RuleResult(rule="abnormal_hour", hit=False)


# 事件类型 -> 规则集合 路由表 (事件分发核心)
# 8 条规则: blacklist_hit / transfer_amt_report / transfer_amt_suspect / transfer_peer_cnt
#           / geo_ip_deviation / loan_multi / login_fail / transfer_disperse / abnormal_hour
DISPATCH_TABLE: dict[str, list[Callable[[TxnContext], RuleResult]]] = {
    "transfer": [rule_blacklist_hit, rule_transfer_amt, rule_transfer_peer_cnt,
                 rule_transfer_disperse, rule_geo_ip_deviation, rule_abnormal_hour],
    "card_txn": [rule_blacklist_hit, rule_geo_ip_deviation, rule_transfer_amt,
                 rule_transfer_disperse, rule_abnormal_hour],
    "loan_apply": [rule_blacklist_hit, rule_loan_multi],
    "repay": [rule_blacklist_hit],
    "login": [rule_blacklist_hit, rule_login_fail, rule_geo_ip_deviation, rule_abnormal_hour],
}


# ============================================================
# 规则链执行 + 事件分发
# ============================================================
def dispatch_rules(txn_type: str) -> list[Callable]:
    """事件分发: 按 event_type 返回规则列表 (未知类型空链)."""
    if txn_type not in BANK_EVENT_TYPES:
        raise ValueError(f"未知业务事件类型: {txn_type}, 合法值={BANK_EVENT_TYPES}")
    return DISPATCH_TABLE.get(txn_type, [rule_blacklist_hit])


def validate_txn(
    ctx: TxnContext,
    blacklist: set[tuple[str, str]] | None = None,
) -> ValidateResult:
    """执行交易校验规则链, 聚合决策并产出风险事件.

    Args:
        ctx: 交易上下文
        blacklist: {(type, id)} 黑名单集合 (默认空)
    Returns:
        ValidateResult: 含最终决策 + 触发规则 + 待写库风险事件
    """
    blacklist = blacklist or set()
    rules = dispatch_rules(ctx.txn_type)

    results: list[RuleResult] = []
    for r in rules:
        # blacklist 规则需注入 blacklist 集合
        if r is rule_blacklist_hit:
            results.append(rule_blacklist_hit(ctx, blacklist))
        else:
            results.append(r(ctx))

    # 决策聚合: veto(冻结) > reject > report > review > pass
    order = {DECISION_PASS: 0, DECISION_REVIEW: 1, DECISION_REPORT: 2,
             DECISION_REJECT: 3, DECISION_FREEZE: 4}
    triggered = [r for r in results if r.hit]
    if triggered:
        final = max(triggered, key=lambda r: order[r.decision]).decision
    else:
        final = DECISION_PASS

    # 生成风险事件 (命中且需落库)
    events: list[dict] = []
    need_report = False
    for r in triggered:
        etype = {
            DECISION_FREEZE: "anti_fraud_freeze",
            DECISION_REJECT: "veto",
            DECISION_REPORT: "aml_suspect",
            DECISION_REVIEW: "blacklist_hit" if r.rule == "blacklist_hit" else "aml_suspect",
        }.get(r.decision, "aml_suspect")
        events.append({
            "event_id": f"E{ctx.txn_id}",
            "txn_id": ctx.txn_id,
            "cust_id": ctx.cust_id,
            "event_type": etype,
            "trigger_rule": r.rule,
            "severity": r.severity,
            "decision": r.decision,
            "reported": r.decision == DECISION_REPORT,
            "detail_json": {"message": r.message},
        })
        if r.decision == DECISION_REPORT:
            need_report = True

    return ValidateResult(
        txn_id=ctx.txn_id,
        decision=final,
        triggered_rules=triggered,
        risk_events=events,
        need_report=need_report,
    )


# ============================================================
# 便捷入口 (供 event 调度调用, 兼容基线 process_event 签名风格)
# ============================================================
def validate(
    txn_id: str,
    txn_type: str,
    cust_id: str,
    amount: float = 0.0,
    counterparty_id: str | None = None,
    device_fingerprint: str | None = None,
    ip_addr: str | None = None,
    geo_province: str | None = None,
    geo_city: str | None = None,
    blacklist: set[tuple[str, str]] | None = None,
    **features,
) -> ValidateResult:
    """高层封装: 直接传字段, 内部构造 TxnContext 并跑规则链."""
    ctx = TxnContext(
        txn_id=txn_id, cust_id=cust_id, txn_type=txn_type, amount=amount,
        counterparty_id=counterparty_id, device_fingerprint=device_fingerprint,
        ip_addr=ip_addr, geo_province=geo_province, geo_city=geo_city,
        **{k: v for k, v in features.items()
           if k in TxnContext.__dataclass_fields__},
    )
    return validate_txn(ctx, blacklist=blacklist)
