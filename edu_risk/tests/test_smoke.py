"""
冒烟测试 — 用 SQLite 内存库验证核心链路
不依赖 MySQL/XGBoost/LLM/插件,快速验证:
  1. 规则引擎 14 种 op
  2. 双轨融合 + 一票否决
  3. 7 步流水线 process_event
  4. 案件生成 + 状态机
运行: python -m pytest tests/ -v  (或 python tests/test_smoke.py)
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 测试环境: 用 SQLite 替代 MySQL(必须在 import app.* 之前设置)
os.environ["DB_DRIVER"] = "sqlite"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app import models  # noqa: E402,F401  确保所有表注册到 Base.metadata
from app.database import Base  # noqa: E402
from app.engine import decision  # noqa: E402
from app.engine.rule import evaluate_condition  # noqa: E402
from app.service.event import process_event  # noqa: E402


def _make_db():
    """创建内存 SQLite 引擎 + 建表,返回 session。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    asyncio.run(_init())
    Session = async_sessionmaker(engine, expire_on_commit=False)
    return Session, engine


# ---------- 1. 规则引擎 14 op ----------

def test_rule_ops():
    f = {"a": 10, "b": 5, "s": "报名", "list": [1, 2, 3], "r": 0.5}
    assert evaluate_condition({"field": "a", "op": ">", "value": 9}, f) is True
    assert evaluate_condition({"field": "a", "op": ">=", "value": 10}, f) is True
    assert evaluate_condition({"field": "a", "op": "<", "value": 11}, f) is True
    assert evaluate_condition({"field": "a", "op": "<=", "value": 10}, f) is True
    assert evaluate_condition({"field": "a", "op": "==", "value": 10}, f) is True
    assert evaluate_condition({"field": "a", "op": "!=", "value": 11}, f) is True
    assert evaluate_condition({"field": "s", "op": "in", "value": ["报名", "缴费"]}, f) is True
    assert evaluate_condition({"field": "s", "op": "not_in", "value": ["退费"]}, f) is True
    assert evaluate_condition({"field": "a", "op": "between", "value": [5, 15]}, f) is True
    assert evaluate_condition({"and": [{"field": "a", "op": ">", "value": 9},
                                       {"field": "b", "op": "<", "value": 6}]}, f) is True
    assert evaluate_condition({"or": [{"field": "a", "op": ">", "value": 99},
                                      {"field": "b", "op": "==", "value": 5}]}, f) is True
    # 兜底: unknown field / unknown op → False 不抛异常
    assert evaluate_condition({"field": "no_such", "op": ">=", "value": 1}, f) is False
    assert evaluate_condition({"field": "a", "op": "unknown_op", "value": 1}, f) is False
    print("[PASS] 规则引擎 14 op")


# ---------- 2. 双轨融合 + 一票否决 ----------

def test_rule_score():
    hits = [{"risk_level": "高", "risk_score": 70},
            {"risk_level": "中", "risk_score": 40}]
    assert decision.compute_rule_score(hits) == 73.0  # 70 + 3×(2-1)
    print("[PASS] rule_score = max + 3×额外命中")


def test_veto():
    hits = [{"risk_level": "极高", "risk_score": 95}]
    assert decision.apply_veto(50.0, hits) == 90.0  # 一票否决强制 ≥ 90
    assert decision.apply_veto(97.0, hits) == 97.0
    print("[PASS] 一票否决")


def test_decision_map():
    assert decision.score_to_decision(10) == "通过"
    assert decision.score_to_decision(45) == "标记"
    assert decision.score_to_decision(70) == "人工审核"
    assert decision.score_to_decision(95) == "拒绝"
    print("[PASS] 4 种决策映射")


# ---------- 3. 7 步流水线 ----------

def test_process_event():
    Session, engine = _make_db()

    async def run():
        async with Session() as db:
            now = datetime.now()
            # 业务数据: 一个"高危画像"学员
            db.add(models.UserInfo(user_id="U001", user_name="小明",
                                   phone="13800000001",
                                   register_time=now - timedelta(days=100)))
            # 5 次报名
            for i in range(5):
                db.add(models.Enrollment(
                    enrollment_id=f"ENR00{i}", user_id="U001", school_id="SCH001",
                    status="已缴费", total_amount=5000, discount_amount=0, coupon_amount=0,
                    create_time=now - timedelta(days=10 - i)))
            # 4 次退费 → 退费率 0.8
            for i in range(4):
                db.add(models.RefundRecord(
                    refund_id=f"RFD00{i}", enrollment_id=f"ENR00{i}", user_id="U001",
                    amount=5000, status="已退费",
                    apply_time=now - timedelta(days=5 - i)))
            # 2 个账号
            db.add(models.AccountInfo(account_id="ACC001", user_id="U001", account_name="主号",
                                      reg_time=now - timedelta(days=100)))
            db.add(models.AccountInfo(account_id="ACC002", user_id="U001", account_name="小号",
                                      reg_time=now - timedelta(days=50)))
            # 预置 2 条规则
            db.add(models.RiskRule(
                rule_id="R100", rule_name="退费率极高", rule_category="退费",
                event_type="退费", rule_condition={
                    "and": [
                        {"field": "user_refund_rate", "op": ">=", "value": 0.8},
                        {"field": "user_total_enrollments", "op": ">=", "value": 5},
                    ]},
                risk_level="极高", risk_score=90, action="拒绝", priority=90))
            db.add(models.RiskRule(
                rule_id="R101", rule_name="多账号", rule_category="账号",
                event_type="通用", rule_condition={
                    "field": "acct_total_count", "op": ">=", "value": 3},
                risk_level="中", risk_score=50, action="标记", priority=50))
            # 一笔待检查的退费
            db.add(models.Enrollment(
                enrollment_id="ENR_CHECK", user_id="U001", school_id="SCH001",
                status="已缴费", total_amount=5000, discount_amount=0, coupon_amount=0,
                create_time=now - timedelta(days=1),
                pay_time=now - timedelta(days=1) + timedelta(minutes=5)))
            db.add(models.PaymentRecord(payment_id="PAY001", enrollment_id="ENR_CHECK",
                                        user_id="U001", amount=5000, status="成功",
                                        pay_time=now - timedelta(days=1) + timedelta(minutes=5)))
            db.add(models.RefundRecord(refund_id="RFD_CHECK", enrollment_id="ENR_CHECK",
                                       user_id="U001", amount=5000, status="申请中",
                                       apply_time=now))
            await db.commit()

            # 触发退费风控检查
            result = await process_event(db, {
                "event_type": "退费", "source_id": "RFD_CHECK", "user_id": "U001",
            })

            assert result["event_id"].startswith("EVT_")
            assert result["risk_level"] == "极高"      # R100 一票否决
            assert result["decision"] == "拒绝"
            assert result["final_score"] >= 90
            assert result["case_id"] is not None        # 拒绝 → 生成案件
            assert result["features"]["user_refund_rate"] >= 0.8
            assert result["features"]["acct_total_count"] == 2
            assert len(result["features"]) == 25        # 25 维特征
            print(f"[PASS] 7 步流水线: final={result['final_score']} "
                  f"decision={result['decision']} case={result['case_id']}")

    asyncio.run(run())
    asyncio.run(engine.dispose())


# ---------- 4. 案件状态机 ----------

def test_case_state_machine():
    from app.service import case as case_service
    Session, engine = _make_db()

    async def run():
        async with Session() as db:
            db.add(models.RiskCase(case_id="CASE001", assessment_id="ASM001", user_id="U001",
                                   source_id="ENR001", event_type="退费", case_status="待审核"))
            await db.commit()
            # 待审核 → 审核中 → 已通过
            await case_service.claim_case(db, "CASE001", "operator1")
            await case_service.review_case(db, "CASE001", "approve", "operator1", "无误报")
            # 终态不可再转
            try:
                await case_service.claim_case(db, "CASE001", "operator2")
                raise AssertionError("终态不应可流转")
            except Exception:
                pass
            # 超时自动关闭
            from datetime import datetime as dt
            db.add(models.RiskCase(case_id="CASE002", assessment_id="ASM002", user_id="U002",
                                   source_id="ENR002", event_type="报名", case_status="待审核",
                                   create_time=dt.now() - timedelta(hours=48)))
            await db.commit()
            closed = await case_service.auto_close_timeout_cases(db, hours=24)
            assert closed == 1
            print("[PASS] 案件状态机 + 超时自动关闭")

    asyncio.run(run())
    asyncio.run(engine.dispose())


if __name__ == "__main__":
    test_rule_ops()
    test_rule_score()
    test_veto()
    test_decision_map()
    test_process_event()
    test_case_state_machine()
    print("\n全部冒烟测试通过")
