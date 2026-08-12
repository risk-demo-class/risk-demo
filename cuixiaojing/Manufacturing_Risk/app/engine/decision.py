
"""
风控决策引擎: 串联 7 步流水线, 事件 → 特征 → 规则 → 评分 → 决策 → 持久化.

【评分公式】final_score = min(max(各规则分) + BONUS × (额外命中数), 100)
【双轨融合】final_score = α × rule_score + β × ml_score (α+β=1, .env 可调)
【一票否决】任何 risk_level="极高" 的规则命中 → 强制拒绝, 不被 XGBoost 推翻

7 步流水线 (仿 AI_Risk 电商风控):
  1. 校验 + 准备上下文 (Context)
  2. 创建事件记录 (risk_event)
  3-4. 计算 + 保存特征快照 (26 维, risk_feature)
  5. 加载 + 匹配规则
  6. 计算评分与决策 (含一票否决 + 双轨融合)
  7. 落库 + 响应 (assessment/case/profile)
"""
import json
import logging
import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import ulid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.engine.feature import compute_all_features
from app.engine.ml_model import is_model_loaded, predict
from app.engine.rule import RuleHitResult, load_enabled_rules, match_rules
from app.models import (
    CrossRegionReport,
    OrderInfo,
    RiskAssessment,
    RiskCase,
    RiskEvent,
    RiskFeature,
    RiskUserProfile,
    WarrantyRecord,
)
from app.schemas import RiskCheckRequest, RiskCheckResponse, RuleHitInfo

logger = logging.getLogger(__name__)


# ============================================================
# 工具函数 (纯计算, 无副作用, 易测试)
# ============================================================

def _generate_id(prefix: str = "") -> str:
    """生成带前缀的有序唯一 ID. 前缀 区分 ID 用途 (evt 事件 / ast 评估 / cas 案件)"""
    return f"{prefix}{ulid.new().str.lower()}"


def _score_to_level(score: int) -> str:
    """评分 → 风险等级."""
    if score < settings.RISK_PASS_THRESHOLD:
        return "低"
    elif score < settings.RISK_MARK_THRESHOLD:
        return "中"
    elif score < settings.RISK_REVIEW_THRESHOLD:
        return "高"
    else:
        return "极高"


def _score_to_decision(score: int) -> str:
    """评分 → 决策动作. 4 档: 通过 / 标记 / 人工审核 / 拒绝."""
    if score < settings.RISK_PASS_THRESHOLD:
        return "通过"
    elif score < settings.RISK_MARK_THRESHOLD:
        return "标记"
    elif score < settings.RISK_REVIEW_THRESHOLD:
        return "人工审核"
    else:
        return "拒绝"


def calculate_final_score(hits: list[RuleHitResult]) -> int:
    """核心评分公式: max(各规则分) + BONUS × (额外命中数), 上限 100.

    例子:
        1 条命中 [70]              → 70 + 0 = 70
        3 条命中 [70, 50, 40]      → 70 + 3×2 = 76
        3 条命中 [95, 80, 70]      → 95 + 3×2 = 101 → 上限 100
        0 条命中 []                → 0
    """
    if not hits:
        return 0
    max_score = max(h.risk_score for h in hits)
    extra_count = len(hits) - 1
    bonus = settings.RISK_MULTI_RULE_BONUS * extra_count
    return min(max_score + bonus, 100)


def check_veto(hits: list[RuleHitResult]) -> bool:
    """一票否决: 任意 1 条 risk_level="极高" 就 True, 短路返回.

    当前"极高"级别规则: R001 (串货举报≥2) / R008 (90天维修≥2) / R030 (黑经销商).
    """
    return any(h.risk_level == "极高" for h in hits)


# ============================================================
# 步骤 1: 准备上下文
# ============================================================

@dataclass
class _RiskCheckContext:
    request: RiskCheckRequest
    user_id: str
    dealer_id: Optional[str] = None     # 真正被评估的经销商 (串货举报=被举报方)
    order_id: Optional[str] = None
    product_id: Optional[str] = None
    warranty_id: Optional[str] = None
    event_id: str = ""


def _build_context(request: RiskCheckRequest) -> _RiskCheckContext:
    """步骤 1b: 请求 → Context, 补全 order_id.

    业务规则:
      - "经销商订货"事件: source_id 就是 order_id
      - "保修申请" / "售后维修"事件: source_id 是 warranty_id, order_id 后续从保修单补
      - "串货举报"事件: source_id 是 report_id, order_id 后续从举报单补
    """
    order_id = request.order_id
    if not order_id and request.event_type == "经销商订货":
        order_id = request.source_id
    return _RiskCheckContext(
        request=request,
        user_id=request.user_id,
        order_id=order_id,
    )


async def _enrich_business_ids(db: AsyncSession, ctx: _RiskCheckContext) -> None:
    """步骤 1c: 按事件类型补全 dealer_id / order_id / product_id / warranty_id.

    经销商订货: 订单 → product_id / dealer_id (校验在 validator 已完成)
    保修/维修:  保修单 → product_sn / order_id → 订单 → product_id / dealer_id
    串货举报:   举报单 → order_id → 订单 → product_id / dealer_id (被举报经销商)
    """
    if ctx.request.event_type == "经销商订货" and ctx.order_id:
        row = (await db.execute(
            select(OrderInfo.product_id, OrderInfo.dealer_id).where(
                OrderInfo.order_id == ctx.order_id
            )
        )).first()
        if row:
            ctx.product_id = row.product_id
            ctx.dealer_id = row.dealer_id

    elif ctx.request.event_type in ("保修申请", "售后维修"):
        ctx.warranty_id = ctx.request.source_id
        wrow = (await db.execute(
            select(WarrantyRecord.order_id).where(
                WarrantyRecord.warranty_id == ctx.warranty_id
            )
        )).first()
        if wrow:
            ctx.order_id = wrow.order_id
            orow = (await db.execute(
                select(OrderInfo.product_id, OrderInfo.dealer_id).where(
                    OrderInfo.order_id == ctx.order_id
                )
            )).first()
            if orow:
                ctx.product_id = orow.product_id
                ctx.dealer_id = orow.dealer_id

    elif ctx.request.event_type == "串货举报":
        rrow = (await db.execute(
            select(CrossRegionReport.order_id, CrossRegionReport.dealer_id).where(
                CrossRegionReport.report_id == ctx.request.source_id
            )
        )).first()
        if rrow:
            ctx.order_id = rrow.order_id
            ctx.dealer_id = rrow.dealer_id
            orow = (await db.execute(
                select(OrderInfo.product_id).where(OrderInfo.order_id == ctx.order_id)
            )).first()
            if orow:
                ctx.product_id = orow.product_id


# ============================================================
# 步骤 2: 创建事件记录
# ============================================================

def _create_event_record(db: AsyncSession, ctx: _RiskCheckContext) -> str:
    """记 risk_event 表, 返回 event_id (后续 3 张表 FK 引用)"""
    ctx.event_id = _generate_id("evt")
    event = RiskEvent(
        event_id=ctx.event_id,
        event_type=ctx.request.event_type,
        event_source_id=ctx.request.source_id,
        user_id=ctx.user_id,
        event_data=json.dumps(ctx.request.event_data or {}, ensure_ascii=False),
    )
    db.add(event)
    return ctx.event_id


# ============================================================
# 步骤 3-4: 计算特征 + 保存特征快照
# ============================================================

async def _compute_features(db: AsyncSession, ctx: _RiskCheckContext) -> dict:
    """步骤 3: 调 feature.py 计算 26 个风控特征 (经销商/订单/产品/保修 4 类)"""
    return await compute_all_features(
        db,
        user_id=ctx.user_id,
        dealer_id=ctx.dealer_id,
        order_id=ctx.order_id,
        product_id=ctx.product_id,
        warranty_id=ctx.warranty_id,
    )


def _classify_feature_entity(feature_name: str) -> tuple[str, str]:
    """特征名前缀 → 实体类型. dealer_* → 经销商, order_* → 订单, product_* → 产品, 其他 → 保修"""
    if feature_name.startswith("dealer_"):
        return "经销商", feature_name
    if feature_name.startswith("order_"):
        return "订单", feature_name
    if feature_name.startswith("product_"):
        return "产品", feature_name
    return "保修", feature_name


def _save_feature_snapshot(
    db: AsyncSession,
    ctx: _RiskCheckContext,
    features: dict,
) -> None:
    """步骤 4: 把 26 个特征落库到 risk_feature (审计回溯).

    entity_id 填充规则 (按 entity_type):
      - 经销商特征 → ctx.dealer_id (缺失用 user_id)
      - 订单特征   → ctx.order_id (缺失用 source_id)
      - 产品特征   → ctx.product_id
      - 保修特征   → ctx.warranty_id (缺失用 source_id)
    """
    for fname, fval in features.items():
        entity_type, _ = _classify_feature_entity(fname)
        if entity_type == "经销商":
            entity_id = ctx.dealer_id or ctx.user_id
        elif entity_type == "订单":
            entity_id = ctx.order_id or ctx.request.source_id
        elif entity_type == "产品":
            entity_id = ctx.product_id or ""
        else:  # 保修
            entity_id = ctx.warranty_id or ctx.request.source_id
        db.add(RiskFeature(
            event_id=ctx.event_id,
            entity_type=entity_type,
            entity_id=entity_id,
            feature_name=fname,
            feature_value=fval,
        ))


# ============================================================
# 步骤 5: 加载并匹配规则
# ============================================================

async def _evaluate_rules(
    db: AsyncSession,
    ctx: _RiskCheckContext,
    features: dict,
) -> list[RuleHitResult]:
    """步骤 5: 加载 + 匹配规则. "通用" 规则对所有 event_type 生效"""
    rules = await load_enabled_rules(db, event_type=ctx.request.event_type)
    return match_rules(rules, features)


# ============================================================
# 步骤 6: 计算评分与决策
# ============================================================

def _ml_prob_to_risk_score(prob: float, k: float = 3.0) -> int:
    """ML P(拒绝) → 0-100 风险分 (sigmoid 风格校准).

    校准公式: risk_score = 100 * (1 - exp(-k * prob)), k=3
    物理意义: 指数饱和函数, 低概率压低 (避免误报), 高概率推高 (强化高风险信号).
    校准点: 0.1→26, 0.3→59, 0.5→78, 0.7→90, 0.9→97
    """
    if prob <= 0:
        return 0
    if prob >= 1:
        return 100
    return int(round(100 * (1 - math.exp(-k * prob))))


def _calculate_decision(
    rules: list[RuleHitResult],
    features: dict,
) -> tuple[int, str, str, float, str]:
    """步骤 6: 算评分 + 一票否决 + 双轨融合 + 映射.

    双轨融合: final_score = α × rule_score + β × ml_score (默认 0.5/0.5)
    兜底: XGBoost 未加载 → 只用 rule_score.
    一票否决双保险: 融合前抬分 + 融合后强制拒绝, 不被 ML 推翻.
    """
    # 基础评分
    rule_score = calculate_final_score(rules)

    has_veto = check_veto(rules)
    if has_veto:
        rule_score = max(rule_score, settings.RISK_VETO_MIN_SCORE)

    # XGBoost 推理 (未加载返回 None → 纯规则)
    ml_result = predict(features) if is_model_loaded() else None
    ml_score_100 = _ml_prob_to_risk_score(ml_result.score) if ml_result else 0
    ml_decision = ml_result.decision if ml_result else "通过"

    # 双轨融合 (加权平均, 截到 [0, 100])
    if ml_result and ml_result.is_loaded:
        final_score = int(round(
            settings.ML_WEIGHT_RULE * rule_score
            + settings.ML_WEIGHT_XGB * ml_score_100
        ))
        final_score = max(0, min(100, final_score))
    else:
        final_score = rule_score

    risk_level = _score_to_level(final_score)
    decision = _score_to_decision(final_score)

    # 硬性一票否决: 不被 XGBoost 推翻
    if has_veto:
        decision = "拒绝"
        risk_level = "极高"
        final_score = max(final_score, settings.RISK_VETO_MIN_SCORE)

    return final_score, risk_level, decision, ml_result.score if ml_result else 0.0, ml_decision


# ============================================================
# 步骤 7: 落库 + 响应
# ============================================================

async def _save_assessment(
    db: AsyncSession,
    ctx: _RiskCheckContext,
    rules: list[RuleHitResult],
    final_score: int,
    risk_level: str,
    decision: str,
    ml_score: float = 0.0,
    ml_decision: str = "通过",
) -> str:
    """步骤 7a: 写 risk_assessment, 返回 assessment_id."""
    assessment_id = _generate_id("ast")
    rule_results_json = json.dumps(
        [h.to_dict() for h in rules], ensure_ascii=False,
    )
    db.add(RiskAssessment(
        assessment_id=assessment_id,
        event_id=ctx.event_id,
        user_id=ctx.user_id,
        rule_results=rule_results_json,
        rule_count=len(rules),
        final_score=final_score,
        risk_level=risk_level,
        decision=decision,
        ml_score=ml_score,
        ml_decision=ml_decision,
    ))
    return assessment_id


# 条件建案: 决策是"人工审核"或"拒绝"时才建 (通过/标记不留底)
async def _maybe_create_case(
    db: AsyncSession,
    assessment_id: str,
    ctx: _RiskCheckContext,
    rules: list[RuleHitResult],
    final_score: int,
    decision: str,
) -> None:
    """步骤 7b: 条件建案 (决策是"人工审核"或"拒绝"时才建)."""
    if decision not in ("人工审核", "拒绝"):
        return

    # 去重: 同一 (source_id, event_type) + 未结案 → skip
    open_statuses = ("待审核", "审核中")
    existing = (await db.execute(
        select(RiskCase.case_id).where(
            RiskCase.source_id == ctx.request.source_id,
            RiskCase.event_type == ctx.request.event_type,
            RiskCase.case_status.in_(open_statuses),
        ).limit(1)
    )).scalar_one_or_none()
    if existing:
        logger.info(
            "跳过建案: 已有未结案 case=%s (source_id=%s, event_type=%s)",
            existing, ctx.request.source_id, ctx.request.event_type,
        )
        return

    case_id = _generate_id("cas")
    if rules:
        top_category = Counter(r.rule_category for r in rules).most_common(1)[0][0]
    else:
        top_category = "未知"

    # 自动拒绝的案件直接关案; 人工审核的才走待审核
    is_auto_reject = decision == "拒绝"
    initial_status = "已拒绝" if is_auto_reject else "待审核"

    case_kwargs = dict(
        case_id=case_id,
        assessment_id=assessment_id,
        user_id=ctx.user_id,
        case_status=initial_status,
        case_category=top_category,
        risk_detail=json.dumps([h.to_dict() for h in rules], ensure_ascii=False),
        # 冗余: 让"重做检查"不用 join 多张表
        source_id=ctx.request.source_id,
        event_type=ctx.request.event_type,
    )
    if is_auto_reject:
        case_kwargs.update(
            reviewer="system",
            review_time=datetime.now(),
            review_comment=f"系统自动拒绝 (final_score={final_score}, {len(rules)} 条规则命中)",
        )

    db.add(RiskCase(**case_kwargs))
    logger.info(
        "创建案件: %s, source_id=%s, event_type=%s, 决策=%s, 分值=%d, 状态=%s",
        case_id, ctx.request.source_id, ctx.request.event_type, decision, final_score, initial_status,
    )

    # 自动拒绝记一条审计 (action_log)
    if is_auto_reject:
        from app.service.action_log import record_action
        await record_action(
            db, operator="system", action_type="AUTO_REJECT_CASE",
            target_type="case", target_id=case_id,
            before_value=None,
            after_value={"case_status": "已拒绝", "final_score": final_score,
                         "decision": decision, "rule_count": len(rules)},
            remark=f"系统自动拒绝, source_id={ctx.request.source_id}",
        )


async def _update_user_profile(
    db: AsyncSession,
    ctx: _RiskCheckContext,
    features: dict,
    final_score: int,
    risk_level: str,
) -> None:
    """步骤 7c: 更新经销商风险画像 (upsert 模式: 有则更新, 无则插入).

    字段从 features 取 (复用刚才算好的 26 特征, 不再查 DB).
    """
    profile = (await db.execute(
        select(RiskUserProfile).where(RiskUserProfile.user_id == ctx.user_id)
    )).scalar_one_or_none()

    if not profile:
        profile = RiskUserProfile(user_id=ctx.user_id)
        db.add(profile)

    profile.risk_score = final_score
    profile.risk_level = risk_level
    profile.total_orders = int(features.get("dealer_total_orders", 0))
    profile.total_amount = features.get("dealer_total_amount", 0)
    profile.avg_order_amount = features.get("dealer_avg_order_amount", 0)
    profile.warranty_count = int(features.get("dealer_warranty_count", 0))
    profile.repair_count = int(features.get("dealer_repair_count", 0))
    profile.contract_expired = int(features.get("dealer_contract_expired", 0))
    # 累计评估次数 +1
    profile.assessment_count = (profile.assessment_count or 0) + 1
    profile.last_assessment_time = datetime.now()


def _build_response(
    ctx: _RiskCheckContext,
    features: dict,
    rules: list[RuleHitResult],
    final_score: int,
    risk_level: str,
    decision: str,
    event_id: str,
    assessment_id: str,
    ml_score: float = 0.0,
    ml_decision: str = "通过",
) -> RiskCheckResponse:
    """步骤 7d: 包装成 API 响应 (Pydantic 模型)."""
    triggered_rules = [
        RuleHitInfo(
            rule_id=h.rule_id,
            rule_name=h.rule_name,
            rule_category=h.rule_category,
            risk_level=h.risk_level,
            risk_score=h.risk_score,
            action=h.action,
            description=h.description,
        )
        for h in rules
    ]

    features_out = features if settings.RISK_FEATURES_FULL_RETURN else {}

    return RiskCheckResponse(
        assessment_id=assessment_id,
        event_id=event_id,
        user_id=ctx.user_id,
        final_score=final_score,
        risk_level=risk_level,
        decision=decision,
        rule_count=len(rules),
        triggered_rules=triggered_rules,
        features=features_out,
        create_time=datetime.now(),
        ml_score=ml_score,
        ml_decision=ml_decision,
    )


# ============================================================
# 主函数: 7 步流水线串联
# ============================================================

async def run_risk_check(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> RiskCheckResponse:
    """串流程, 不写业务. 失败任意一步 → 整个事务回滚, 不留脏数据.
    入口校验在 process_event 第 1 步已完成, run_risk_check 不再重复.
    """
    # 1. 准备上下文 (校验已在 process_event 完成, 不重复)
    ctx = _build_context(request)
    await _enrich_business_ids(db, ctx)

    # 2. 创建事件记录
    event_id = _create_event_record(db, ctx)

    # 3-4. 计算 + 保存特征快照
    features = await _compute_features(db, ctx)
    _save_feature_snapshot(db, ctx, features)

    # 5. 加载 + 匹配规则
    rules = await _evaluate_rules(db, ctx, features)

    # 6. 算决策 (含一票否决 + 双轨融合)
    final_score, risk_level, decision, ml_score, ml_decision = _calculate_decision(rules, features)

    # 7. 落库 + 响应
    # flush 发 SQL 但不 commit, 让 event_id 落库可被 FK 引用
    await db.flush()
    assessment_id = await _save_assessment(
        db, ctx, rules, final_score, risk_level, decision, ml_score, ml_decision,
    )
    await _maybe_create_case(db, assessment_id, ctx, rules, final_score, decision)
    await _update_user_profile(db, ctx, features, final_score, risk_level)

    # 提交事务 (一次性写 4-5 张表, 原子性)
    await db.commit()

    return _build_response(
        ctx, features, rules, final_score, risk_level, decision, event_id, assessment_id,
        ml_score, ml_decision,
    )


# ============================================================
# Demo: 演练核心评分公式 + 一票否决 + 等级/决策映射 — 无需 DB
# 跑法: python -m app.engine.decision
# ============================================================
if __name__ == "__main__":
    from types import SimpleNamespace
    from app.engine.rule import RuleHitResult

    def _mock_hit(rid, score, level, action="拒绝"):
        return RuleHitResult(SimpleNamespace(
            rule_id=rid, rule_name=f"规则 {rid}", rule_category="测试",
            risk_score=score, risk_level=level, action=action, description="",
        ))

    print("=" * 60)
    print("决策引擎 — 4 大核心能力 (纯计算, 无 DB 依赖)")
    print("=" * 60)

    # 1. 映射
    print("\n[1] 评分 → 风险等级 / 决策 映射 (4 档)")
    print(f"  {'score':<6} {'level':<6} {'decision':<8}")
    for s in [10, 30, 50, 60, 70, 80, 95, 100]:
        print(f"  {s:<6} {_score_to_level(s):<6} {_score_to_decision(s):<8}")

    # 2. 评分公式
    print("\n[2] 评分公式: max(规则分) + 3 × (额外命中数), 上限 100")
    cases = [
        ("1 条命中 [70]",                       [_mock_hit("R1", 70, "高")]),
        ("2 条命中 [70, 40]",                   [_mock_hit("R1", 70, "高"), _mock_hit("R2", 40, "中")]),
        ("3 条命中 [70, 40, 20]",               [_mock_hit("R1", 70, "高"), _mock_hit("R2", 40, "中"), _mock_hit("R3", 20, "低")]),
        ("3 条命中 [95, 80, 70]",               [_mock_hit("R1", 95, "极高"), _mock_hit("R2", 80, "高"), _mock_hit("R3", 70, "高")]),
        ("0 条命中 []",                         []),
    ]
    for desc, hits in cases:
        s = calculate_final_score(hits)
        print(f"  {desc:<32} → {s}")

    # 3. 一票否决
    print("\n[3] 一票否决: 任意 1 条 risk_level='极高' 触发")
    cases2 = [
        ("无极高",     [_mock_hit("R1", 70, "高"),  _mock_hit("R2", 80, "高")],  False),
        ("含 1 条极高",[_mock_hit("R1", 95, "极高"), _mock_hit("R2", 80, "高")], True),
    ]
    for desc, hits, expected in cases2:
        got = check_veto(hits)
        mark = "✓" if got == expected else "✗"
        print(f"  {mark} {desc:<20} 期望={expected} 实际={got}")

    # 4. 双轨融合 + 一票否决双保险
    print("\n[4] 决策: 双轨融合 + 一票否决双保险")
    print(f"  {'场景':<35} {'rule_s':<7} {'ml_s':<5} {'final':<6} {'level':<6} {'decision':<8}")
    cases3 = [
        ("R005 大额囤货 (无 veto)",  [_mock_hit("R005", 70, "高")],     0.20, None),
        ("R001 串货 (有 veto)",      [_mock_hit("R001", 95, "极高")],   0.05, None),
    ]
    for desc, hits, ml_score, _ in cases3:
        ml_loaded = ml_score is not None
        ml_res = SimpleNamespace(score=ml_score or 0, decision="通过", is_loaded=ml_loaded) if ml_loaded else None
        from app.engine import ml_model
        orig = ml_model.predict
        ml_model.predict = lambda f: ml_res if ml_res else orig(f)
        orig_loaded = ml_model.is_model_loaded
        ml_model.is_model_loaded = lambda: ml_loaded
        try:
            fs, lv, dc, _, _ = _calculate_decision(hits, {})
        finally:
            ml_model.predict = orig
            ml_model.is_model_loaded = orig_loaded
        print(f"  {desc:<30} {calculate_final_score(hits):<7} {(ml_score or 0):<5} {fs:<6} {lv:<6} {dc:<8}")

    print("\n" + "=" * 60)
    print("结论: 双保险 (veto 强制拒绝 + 抬分到 90) 即使 ML 给出低分也无法放行")
