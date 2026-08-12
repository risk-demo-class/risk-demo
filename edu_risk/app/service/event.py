"""
核心业务层 — 7 步流水线 process_event
原子事务: 末尾一次 commit,任何步骤失败全部回滚。
步骤: 1 校验 → 2 建事件 → 3-4 特征+快照 → 5 规则 → 6 ML+融合 → 7 落库
"""
import logging
from datetime import datetime

from sqlalchemy import select

from app.engine import decision, feature, ml_model, rule
from app.engine.rule import build_hits, evaluate_condition, load_enabled_rules
from app.models import (
    RiskAssessment, RiskCase, RiskEvent, RiskFeature, RiskUserProfile, gen_id,
)
from app.service import validator
from app.service.action_log import record_action

logger = logging.getLogger(__name__)


async def process_event(db, payload: dict) -> dict:
    """
    7 步流水线(教育场景):
    POST /api/risk/check {"event_type":"报名","source_id":"ENR_xxx","user_id":"1001"}
    返回: RiskCheckResponse
    """
    # ---------- 步骤 1: 校验 + 构造上下文 ----------
    await validator.validate_risk_check_request(db, payload)   # 1a 6 个 ensure_*
    ctx = _build_context(payload)                              # 1b
    _enrich_receive_id(db, ctx)                                # 1c (教育场景: 报名单即 source)

    # ---------- 步骤 2: 建事件记录 ----------
    event = await _create_event_record(db, ctx)                # 2

    # ---------- 步骤 3-4: 25 维特征 + 快照 ----------
    features = await _compute_features(db, ctx)                # 3
    await _save_feature_snapshot(db, event.event_id, features)  # 4

    # ---------- 步骤 5: 规则匹配 ----------
    hits = await _evaluate_rules(db, ctx, features)            # 5

    # ---------- 步骤 6: ML + 双轨融合 ----------
    result = await _calculate_decision(db, ctx, hits, features)  # 6

    # ---------- 步骤 7: 落库(一次 commit) ----------
    case_id = await _save_assessment_and_case(db, ctx, event, result, hits)  # 7
    await _update_user_profile(db, ctx["user_id"], result)      # 7

    await db.commit()  # ★ 原子提交,任何步骤失败全部回滚

    return {
        "event_id": event.event_id,
        "user_id": ctx["user_id"],
        "event_type": ctx["event_type"],
        "features": features,
        "hit_rules": build_hits(hits, features),
        "rule_score": result["rule_score"],
        "ml_score": result["ml_score"],
        "ml_loaded": result["ml_loaded"],
        "final_score": result["final_score"],
        "risk_level": result["risk_level"],
        "decision": result["decision"],
        "case_id": case_id,
    }


# ============================================================
# 9 个内部函数
# ============================================================

def _build_context(payload: dict) -> dict:
    """1b: 构造 ctx,包含业务上下文。"""
    return {
        "event_type": payload["event_type"],
        "user_id": payload["user_id"],
        "source_id": payload["source_id"],
        "extra": payload.get("extra", {}),
    }


def _enrich_receive_id(db, ctx: dict):
    """1c: 教育场景 source_id 即业务单据号(报名单/缴费单/退费单...),无需二次补全。"""
    return ctx["source_id"]


async def _create_event_record(db, ctx: dict) -> RiskEvent:
    """2: 插入 risk_event,拿到 event_id。"""
    event = RiskEvent(
        event_id=gen_id("EVT"),
        event_type=ctx["event_type"],
        user_id=ctx["user_id"],
        source_id=ctx["source_id"],
        event_data={"extra": ctx["extra"]},
    )
    db.add(event)
    await db.flush()
    return event


async def _compute_features(db, ctx: dict) -> dict:
    """3: 25 维特征。"""
    return await feature.compute_all_features(
        db, user_id=ctx["user_id"], source_id=ctx["source_id"])


async def _save_feature_snapshot(db, event_id: str, features: dict):
    """4: 25 条 risk_feature 快照 — 训练 ML 用快照,不受业务数据变化影响。"""
    for name, value in features.items():
        db.add(RiskFeature(event_id=event_id, feature_name=name, feature_value=value))
    await db.flush()


async def _evaluate_rules(db, ctx: dict, features: dict) -> list:
    """5: 加载启用规则(按优先级)+ 匹配。"""
    rules = await load_enabled_rules(db, event_type=ctx["event_type"])
    hits = [r for r in rules if evaluate_condition(r.rule_condition, features)]
    logger.info("event_type=%s 命中规则 %d 条", ctx["event_type"], len(hits))
    return hits


async def _calculate_decision(db, ctx: dict, hits: list, features: dict) -> dict:
    """6: 双轨融合 + 一票否决。"""
    return decision.calculate_decision(build_hits(hits, features), features)


async def _save_assessment_and_case(db, ctx: dict, event: RiskEvent,
                                    result: dict, hits: list) -> str | None:
    """7a: 写 risk_assessment;决策=人工审核/拒绝时生成 risk_case。"""
    assessment = RiskAssessment(
        assessment_id=gen_id("ASM"),
        event_id=event.event_id,
        rule_score=result["rule_score"],
        ml_score=result["ml_score"],
        final_score=result["final_score"],
        risk_level=result["risk_level"],
        decision=result["decision"],
        hit_rules=[{"rule_id": h.rule_id, "risk_level": h.risk_level,
                    "risk_score": h.risk_score} for h in hits],
    )
    db.add(assessment)
    await db.flush()

    case_id = None
    if result["decision"] in ("人工审核", "拒绝"):
        case = RiskCase(
            case_id=gen_id("CASE"),
            assessment_id=assessment.assessment_id,
            user_id=ctx["user_id"],
            source_id=ctx["source_id"],
            event_type=ctx["event_type"],
            case_status="待审核",
        )
        db.add(case)
        await db.flush()
        case_id = case.case_id
        await record_action(db, "system", "case_create",
                            after={"case_id": case_id, "decision": result["decision"]})
    return case_id


async def _update_user_profile(db, user_id: str, result: dict):
    """7b: UPSERT 用户风险画像。"""
    r = await db.execute(select(RiskUserProfile).where(RiskUserProfile.user_id == user_id))
    profile = r.scalar_one_or_none()
    now = datetime.now()
    if profile is None:
        profile = RiskUserProfile(user_id=user_id, total_checks=0, total_cases=0,
                                  max_score=0, avg_score=0)
        db.add(profile)
    profile.total_checks += 1
    profile.max_score = max(profile.max_score, result["final_score"])
    # 简易移动平均
    profile.avg_score = round(
        (float(profile.avg_score) * (profile.total_checks - 1) + float(result["final_score"]))
        / profile.total_checks, 2) if profile.total_checks else result["final_score"]
    if result["final_score"] >= 80:
        profile.risk_tag = "高危"
    elif result["final_score"] >= 60:
        profile.risk_tag = "关注"
    if profile.first_check_time is None:
        profile.first_check_time = now
    profile.last_check_time = now
