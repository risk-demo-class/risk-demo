"""
银行风控系统 - 规则引擎
======================
基于 JSON 条件表达式对特征字典求值, 判断规则是否命中.

【规则执行模式】
  - 模式 1 (JSON 条件): 规则的 conditions 字段是 JSON, 直接用 evaluate_condition 求值
  - 模式 2 (自定义函数): 复杂时间窗口规则通过 feature.py 预计算特征, 本模块仅做条件求值

【支持的运算符】 >, >=, <, <=, ==, !=, in, not_in, between, and, or

【规则覆盖范围 — 25 条规则 (PRD 15 条 + 行业补充 10 条)】

  PRD 原规则 (15 条):
    R001 异地大额转账      — 登录城市 != 常用城市 且 转账 > 5 万 → 极高/拒绝
    R002 凌晨密集操作      — 0-5 点 且 1 小时内 >= 3 笔 → 高/人工复核
    R003 盗号快速改绑      — 新设备+异地 且 30 分钟内改密/换绑 → 极高/拒绝/冻结登录
    R005 新设备大额        — 设备首次出现 < 7 天 且 单笔 > 3 万 → 高/人工复核
    R008 多卡归集          — 1 小时内 >= 3 张卡转入同一收款卡 → 极高/拒绝/收款卡止付
    R010 试探后大额        — 24h 内同一对手小额 >= 2 笔 且 随即 > 1 万 → 高/人工复核
    R012 信贷申请突击      — 当月已申请 >= 3 家不同机构贷款 → 高/人工复核
    R015 放款即转          — 放款后 24h 转出 >= 90% 至非本人卡 → 极高/拒绝/账户冻结
    R018 设备多人共用      — 同一 device_id 关联 >= 5 个不同 user_id → 中/标记
    R020 多头查询          — 近 1 月征信查询 >= 6 次 → 高/人工复核
    R022 养卡套现          — 同一商户月内 >= 5 笔且累计 >= 额度 80% → 中/标记/限额
    R025 IP代理/秒拨        — 登录 IP 命中代理库/Tor → 中/标记/增强验证
    R028 涉诈收款          — 收款卡命中公安涉诈名单 → 极高/拒绝/上报
    R030 黑卡拦截          — 收款卡号在黑名单 → 极高/拒绝
    R033 团伙申请          — 同一设备或IP关联 >= 3 个不同申请人 → 高/人工复核
    R035 收入与征信不符    — 申请收入 > 征信收入 30% 且无税单佐证 → 高/人工复核

  行业补充规则 (10 条, 基于银行业真实欺诈模式调研):
    R036 撞库攻击          — 同一 IP 1 小时内 >= 10 次登录失败 (不同账号) → 极高/拒绝/IP封锁
    R037 信用卡盗刷测试    — 信用卡先小额(<=10元) >= 2 笔, 随后 >= 5000 元 → 高/人工复核
    R038 资金快进快出      — 24h 内资金流入后 <= 1h 即转出 >= 80% → 高/人工复核/账户监控
    R039 IP关联多账户      — 同一 IP 关联 >= 8 个不同 user_id (登录/交易) → 中/标记
    R040 非本人设备操作    — 设备首次关联该用户 且 用户 >= 30 天历史 → 中/增强验证
    R041 频繁修改资料      — 24h 内修改密码/手机号 >= 3 次 → 高/人工复核/冻结
    R042 境外异常消费      — 信用卡 1h 内 >= 3 笔境外交易 且 累计 >= 额度 50% → 高/人工复核
    R043 规避监控金额      — 转账金额 ∈ [9000, 10000) 或 [19000, 20000) 或 [49000, 50000) → 中/标记
    R044 集中转入分散转出  — 同一卡 24h 内 >= 3 笔转入 且 >= 5 笔转出 → 高/人工复核
    R045 贷后资金回流      — 放款后资金通过 >= 2 层关联账户回流 → 极高/拒绝/冻结

【评分公式】
  final_score = max(各规则分) + BONUS × (额外命中数), 上限 100
  一票否决: 任意 risk_level=4 (极高) 的规则命中 → 强制拒绝

【行业欺诈模式调研 (2026年8月)】
  银行业常见欺诈类型:
  1. 账户接管 (ATO): 盗取凭证 → 改绑手机 → 快速转账 (对应 R003, R041)
  2. 电信诈骗资金转移: 受害者转账 → 多级拆分 → 取现/消费 (对应 R008, R044)
  3. 洗钱 (Money Laundering): 快进快出、分散转入集中转出 (对应 R038, R044)
  4. 信用卡欺诈: 盗刷测试 → 大额消费 → 套现 (对应 R037, R042, R022)
  5. 信贷欺诈: 伪造收入、多头借贷、团伙申请 (对应 R012, R020, R033, R035, R045)
  6. 撞库/批量登录: 自动化脚本 → 大量失败 → 成功后盗号 (对应 R036, R039)
  7. 养卡/套现: POS 机虚假交易 → 循环刷卡套取额度 (对应 R022)
  8. 中介代办: 同一设备/IP 关联多人 → 收取手续费代办贷款 (对应 R018, R033, R039)
"""
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RuleConfig

logger = logging.getLogger(__name__)


class RuleHitResult:
    """单条规则命中结果. 从 RuleConfig ORM 拷贝业务字段, 后续不碰 ORM 对象."""

    def __init__(self, rule: RuleConfig):
        self.rule_id = rule.rule_id
        self.rule_name = rule.rule_name
        self.scene = rule.scene
        self.risk_level = rule.risk_level
        self.decision = rule.decision
        self.action = rule.action
        self.priority = rule.priority
        self.conditions = rule.conditions

    def risk_score(self) -> int:
        """风险等级 → 分值: 1=低→20, 2=中→45, 3=高→70, 4=极高→95"""
        mapping = {1: 20, 2: 45, 3: 70, 4: 95}
        return mapping.get(self.risk_level, 20)

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "scene": self.scene,
            "risk_level": self.risk_level,
            "risk_score": self.risk_score(),
            "decision": self.decision,
            "action": self.action,
            "description": f"规则 {self.rule_id}: {self.rule_name} (条件: {json.dumps(self.conditions, ensure_ascii=False)})",
        }


def match_rules(
    rules: list[RuleConfig],
    features: dict[str, float],
) -> list[RuleHitResult]:
    """
    对 rules 每条用 features 求值, 返回所有命中的 RuleHitResult.

    流程:
      1. 对每条规则解析 conditions JSON
      2. evaluate_condition 递归求值
      3. 命中 → 加入结果列表

    注意: features 由 feature.py 预计算, 包含时间窗口聚合指标,
    规则引擎只负责条件求值, 不再查 DB.
    """
    hits: list[RuleHitResult] = []
    for rule in rules:
        try:
            condition = rule.conditions
            if isinstance(condition, str):
                condition = json.loads(condition)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("规则 %s 条件解析失败: %s", rule.rule_id, e)
            continue

        if evaluate_condition(condition, features):
            hit = RuleHitResult(rule)
            logger.info(
                "规则命中: %s (%s), 场景=%s, 风险等级=%d, 分值=%d, 决策=%s",
                rule.rule_id, rule.rule_name, rule.scene,
                rule.risk_level, hit.risk_score(), rule.decision,
            )
            hits.append(hit)

    # 按优先级排序 (小者先, 即高优先级规则在前)
    hits.sort(key=lambda h: h.priority)
    return hits


def evaluate_condition(condition: dict, features: dict[str, float]) -> bool:
    """
    递归求值 1 个 JSON 条件表达式, 返回 bool.

    条件格式:
      {"field": "user_txn_1h_count", "op": ">=", "value": 3}     ← 单条件
      {"and": [条件1, 条件2]}                                      ← 逻辑组合
      {"or": [条件1, 条件2]}                                       ← 逻辑组合
      {"not": 条件1}                                               ← 取反

    支持的 op:
      比较: >, >=, <, <=, ==, !=
      集合: in, not_in
      区间: between
    """
    if "and" in condition:
        return all(evaluate_condition(sub, features) for sub in condition["and"])
    if "or" in condition:
        return any(evaluate_condition(sub, features) for sub in condition["or"])
    if "not" in condition:
        return not evaluate_condition(condition["not"], features)

    field = condition.get("field", "")
    op = condition.get("op", "")
    value = condition.get("value")

    actual = features.get(field)
    if actual is None:
        logger.debug("特征 '%s' 不存在, 条件跳过", field)
        return False

    try:
        return _compare(actual, op, value)
    except Exception as e:
        logger.warning("条件求值异常: field=%s, op=%s, value=%s, actual=%s, err=%s",
                       field, op, value, actual, e)
        return False


def _compare(actual: float, op: str, value: Any) -> bool:
    """执行 1 次具体比较运算. 未知 op 兜底 False."""
    if op == ">":
        return actual > float(value)
    elif op == ">=":
        return actual >= float(value)
    elif op == "<":
        return actual < float(value)
    elif op == "<=":
        return actual <= float(value)
    elif op == "==":
        return actual == float(value)
    elif op == "!=":
        return actual != float(value)
    elif op == "in":
        return actual in [float(v) for v in value]
    elif op == "not_in":
        return actual not in [float(v) for v in value]
    elif op == "between":
        low, high = float(value[0]), float(value[1])
        return low <= actual <= high
    else:
        logger.warning("不支持的运算符: %s", op)
        return False


async def load_enabled_rules(
    db: AsyncSession,
    scene: str | None = None,
) -> list[RuleConfig]:
    """
    从 DB 加载"启用"的规则, 按 priority 升序 (小者优先执行).

    scene: 限定场景, 传了就只查这个场景的规则; 不传查全部.
    """
    stmt = select(RuleConfig).where(RuleConfig.status == 1)
    if scene:
        stmt = stmt.where(RuleConfig.scene == scene)
    stmt = stmt.order_by(RuleConfig.priority.asc())
    return list((await db.execute(stmt)).scalars().all())


# ============================================================
# Demo: 演练核心规则 + JSON 条件求值
# 跑法: python app/engine/rule.py
# ============================================================
if __name__ == "__main__":
    from types import SimpleNamespace

    print("=" * 60)
    print("银行风控系统 — 规则引擎 (25 条规则)")
    print("=" * 60)

    # 1. 条件求值测试
    print("\n[1] JSON 条件表达式求值:")
    test_cases = [
        ("基础 >=",
         {"field": "txn_amount", "op": ">=", "value": 50000},
         {"txn_amount": 80000}, True),
        ("AND 组合 (R001 异地大额)",
         {"and": [
             {"field": "user_geo_mismatch", "op": "==", "value": 1},
             {"field": "txn_amount", "op": ">=", "value": 50000},
         ]},
         {"user_geo_mismatch": 1, "txn_amount": 80000}, True),
        ("AND 组合 — 1 条件不满足",
         {"and": [
             {"field": "user_geo_mismatch", "op": "==", "value": 1},
             {"field": "txn_amount", "op": ">=", "value": 50000},
         ]},
         {"user_geo_mismatch": 0, "txn_amount": 80000}, False),
        ("OR 组合 (R003 盗号)",
         {"or": [
             {"field": "user_recent_changepwd", "op": "==", "value": 1},
             {"field": "user_recent_changephone", "op": "==", "value": 1},
         ]},
         {"user_recent_changepwd": 0, "user_recent_changephone": 1}, True),
        ("between (R043 规避监控)",
         {"field": "txn_amount", "op": "between", "value": [9000, 10000]},
         {"txn_amount": 9999}, True),
        ("in (设备黑名单)",
         {"field": "device_status", "op": "in", "value": [2, 3]},
         {"device_status": 3}, True),
    ]
    for desc, cond, feats, expected in test_cases:
        got = evaluate_condition(cond, feats)
        mark = "OK" if got == expected else "FAIL"
        print(f"  [{mark}] {desc:<40} 期望={expected} 实际={got}")

    # 2. match_rules 完整流程
    print("\n[2] match_rules 端到端 — 模拟 3 条规则:")
    rules = [
        SimpleNamespace(
            rule_id="R001", rule_name="异地大额转账", scene="转账",
            conditions={"and": [
                {"field": "user_geo_mismatch", "op": "==", "value": 1},
                {"field": "txn_amount", "op": ">=", "value": 50000},
            ]},
            risk_level=4, decision="REJECT", action="STOP_PAYMENT", priority=1,
        ),
        SimpleNamespace(
            rule_id="R005", rule_name="新设备大额", scene="转账",
            conditions={"and": [
                {"field": "device_age_days", "op": "<", "value": 7},
                {"field": "txn_amount", "op": ">=", "value": 30000},
            ]},
            risk_level=3, decision="MANUAL", action="TAG", priority=5,
        ),
        SimpleNamespace(
            rule_id="R025", rule_name="IP代理/秒拨", scene="登录",
            conditions={"or": [
                {"field": "ip_is_proxy", "op": "==", "value": 1},
                {"field": "ip_is_tor", "op": "==", "value": 1},
            ]},
            risk_level=2, decision="CHALLENGE", action="TAG", priority=15,
        ),
    ]
    # 高风险转账特征
    feats = {
        "user_geo_mismatch": 1,
        "txn_amount": 80000,
        "device_age_days": 2,
        "ip_is_proxy": 0,
        "ip_is_tor": 0,
    }
    hits = match_rules(rules, feats)
    print(f"  输入特征: {feats}")
    print(f"  命中 {len(hits)} 条:")
    for h in hits:
        print(f"    {h.rule_id:<6} | 等级={h.risk_level} | 分值={h.risk_score()} | 决策={h.decision} | {h.rule_name}")

    # 3. 25 条规则总览
    print("\n[3] 25 条规则总览 (PRD 15 + 行业补充 10):")
    print(f"  {'编号':<6} {'场景':<8} {'规则名':<20} {'等级':<4} {'决策':<12} {'处置'}")
    all_rules = [
        ("R001", "转账", "异地大额转账", 4, "REJECT", "STOP_PAYMENT"),
        ("R002", "转账", "凌晨密集操作", 3, "MANUAL", "TAG"),
        ("R003", "登录", "盗号快速改绑", 4, "REJECT", "FREEZE"),
        ("R005", "转账", "新设备大额", 3, "MANUAL", "TAG"),
        ("R008", "转账", "多卡归集", 4, "REJECT", "STOP_PAYMENT"),
        ("R010", "转账", "试探后大额", 3, "MANUAL", "TAG"),
        ("R012", "贷款", "信贷申请突击", 3, "MANUAL", "TAG"),
        ("R015", "贷款", "放款即转", 4, "REJECT", "FREEZE"),
        ("R018", "登录", "设备多人共用", 2, "PASS", "TAG"),
        ("R020", "贷款", "多头查询", 3, "MANUAL", "TAG"),
        ("R022", "信用卡", "养卡套现", 2, "PASS", "LIMIT"),
        ("R025", "登录", "IP代理/秒拨", 2, "CHALLENGE", "TAG"),
        ("R028", "转账", "涉诈收款", 4, "REJECT", "REPORT"),
        ("R030", "转账", "黑卡拦截", 4, "REJECT", "STOP_PAYMENT"),
        ("R033", "贷款", "团伙申请", 3, "MANUAL", "TAG"),
        ("R035", "贷款", "收入与征信不符", 3, "MANUAL", "TAG"),
        ("R036", "登录", "撞库攻击(补)", 4, "REJECT", "FREEZE"),
        ("R037", "信用卡", "盗刷测试(补)", 3, "MANUAL", "TAG"),
        ("R038", "转账", "快进快出(补)", 3, "MANUAL", "FREEZE"),
        ("R039", "登录", "IP多账户(补)", 2, "PASS", "TAG"),
        ("R040", "登录", "非本人设备(补)", 2, "CHALLENGE", "TAG"),
        ("R041", "转账", "频繁改资料(补)", 3, "MANUAL", "FREEZE"),
        ("R042", "信用卡", "境外异常(补)", 3, "MANUAL", "TAG"),
        ("R043", "转账", "规避监控金额(补)", 2, "PASS", "TAG"),
        ("R044", "转账", "集中入分散出(补)", 3, "MANUAL", "TAG"),
        ("R045", "贷款", "贷后回流(补)", 4, "REJECT", "FREEZE"),
    ]
    for rid, scene, name, level, decision, action in all_rules:
        level_name = {1: "低", 2: "中", 3: "高", 4: "极高"}[level]
        print(f"  {rid:<6} {scene:<8} {name:<20} {level_name:<4} {decision:<12} {action}")

    print(f"\n  共 {len(all_rules)} 条 (PRD 15 条 + 行业补充 10 条)")
    print("\n" + "=" * 60)
    print("结论: 25 条规则覆盖登录/转账/贷款/信用卡四大场景, 8 类欺诈模式")
