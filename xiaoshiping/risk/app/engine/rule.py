"""制造业风险规则引擎。"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RuleHit:
    rule_id: str
    rule_name: str
    category: str
    action: str
    score: int
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


RULES = (
    ("MFG-R001", "供应商资质过期", "SUPPLY_CHAIN", "REJECT", 90,
     lambda f: f["supplier_qualification_days"] < 0,
     lambda f: f"供应商资质已过期 {-f['supplier_qualification_days']:.0f} 天"),
    ("MFG-R004", "未检或冻结物料领料", "QUALITY", "HOLD", 88,
     lambda f: f["inventory_hold_flag"] >= 1,
     lambda f: "领料批次处于 HOLD/FAILED 状态"),
    ("MFG-R005", "领料超 BOM 容差", "PRODUCTION", "REVIEW", 62,
     lambda f: f["issue_over_bom_ratio"] > 1.10,
     lambda f: f"领料偏离比 {f['issue_over_bom_ratio']:.2f} 超过 1.10"),
    ("MFG-R008", "关键过程参数越限", "QUALITY", "HOLD", 90,
     lambda f: f["process_parameter_deviation"] > 1.0,
     lambda f: f"过程参数偏离规格中心 {f['process_parameter_deviation']:.2f} 倍半公差"),
    ("MFG-R009", "设备维护/校准逾期或报警", "EQUIPMENT", "REVIEW", 70,
     lambda f: f["equipment_maintenance_overdue_days"] > 0 or f["equipment_calibration_overdue_days"] > 0 or f["equipment_alarm_flag"] >= 1,
     lambda f: "设备维护/校准逾期或设备处于报警、停机状态"),
    ("MFG-R010", "成品质量冻结", "QUALITY", "HOLD", 90,
     lambda f: f["quality_hold_flag"] >= 1,
     lambda f: "成品质量状态为 HOLD/FAILED"),
    ("MFG-R011", "未放行发运", "DELIVERY", "REJECT", 94,
     lambda f: f["shipment_release_gap_flag"] >= 1,
     lambda f: "发运质量未放行或缺少放行人"),
    ("MFG-R014", "供应商质量恶化", "SUPPLY_CHAIN", "ESCALATE", 75,
     lambda f: f["supplier_risk_level"] >= 0.5 and f["iqc_defect_rate"] >= 0.05,
     lambda f: f"供应商风险等级偏高，IQC 不良率 {f['iqc_defect_rate']:.1%}"),
    ("MFG-R015", "重复高额客户投诉", "CUSTOMER", "ESCALATE", 78,
     lambda f: f["customer_complaint_count_30d"] >= 2 and f["complaint_claim_amount"] >= 10000,
     lambda f: f"近 30 天投诉 {f['customer_complaint_count_30d']:.0f} 次，索赔金额 {f['complaint_claim_amount']:.0f}"),
)


def evaluate_rules(features: dict[str, float]) -> list[RuleHit]:
    """执行所有启用的行业规则并返回命中列表。"""
    hits: list[RuleHit] = []
    for rule_id, name, category, action, score, predicate, reason_builder in RULES:
        if predicate(features):
            hits.append(RuleHit(rule_id, name, category, action, score, reason_builder(features)))
    return hits


def rule_score(hits: list[RuleHit]) -> int:
    if not hits:
        return 0
    return min(100, max(hit.score for hit in hits) + max(0, len(hits) - 1) * 3)


def rule_decision(hits: list[RuleHit]) -> str | None:
    actions = {hit.action for hit in hits}
    if "REJECT" in actions:
        return "REJECT"
    if "HOLD" in actions:
        return "HOLD"
    if "ESCALATE" in actions:
        return "ESCALATE"
    if "REVIEW" in actions:
        return "REVIEW"
    if "WARN" in actions:
        return "WARN"
    return None
