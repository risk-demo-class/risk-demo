"""批量银行数据、八类模式和真实跨日期回放测试。"""

from argparse import Namespace
from datetime import datetime

from sqlalchemy import func, select

from app.config import settings
from app.data_generation import (
    GenerationConfig,
    PATTERN_LABELS,
    generate_bank_data,
    pattern_distribution,
    save_manifest,
)
from app.engine.feature import FEATURE_COLUMNS
from app.engine.ml_model import ml_model
from app.models_risk import RiskAssessment, RiskFeature
from app.schemas import RiskCheckRequest
from app.service.event import process_event
from scripts.seed_rules import seed_rules


async def test_generator_covers_eight_patterns_and_real_pipeline(session_factory):
    config = GenerationConfig(
        users=20, transactions=48, loans=4,
        logins_per_user_min=1, logins_per_user_max=2,
        candidate_count=16, risk_ratio=0.875, days=45,
        seed=20260813, prefix="TST",
    )
    async with session_factory() as db:
        async with db.begin():
            await seed_rules(db)
            summary, candidates = await generate_bank_data(db, config)

        assert summary.customers == 20
        assert summary.candidates == 16
        distribution = pattern_distribution(candidates)
        assert set(distribution) == set(PATTERN_LABELS)
        assert all(distribution[name] > 0 for name in PATTERN_LABELS)

        # 每类取一条，按事件时间调用真实 Service/Engine，不直接伪造风控表。
        selected = {}
        for candidate in sorted(candidates, key=lambda item: item.event_time):
            selected.setdefault(candidate.pattern, candidate)
        old_enabled = settings.XGB_ENABLED
        settings.XGB_ENABLED = False
        ml_model.reset()
        try:
            for candidate in sorted(selected.values(), key=lambda item: item.event_time):
                result = await process_event(
                    db,
                    RiskCheckRequest.model_validate(candidate.request_data()),
                    decision_time=datetime.fromisoformat(candidate.event_time),
                )
                assert result.assessment_id is not None
                assert tuple(result.features) == FEATURE_COLUMNS
                assert len(result.features) == 25
                assert result.create_time == datetime.fromisoformat(candidate.event_time)
        finally:
            settings.XGB_ENABLED = old_enabled
            ml_model.reset()

        assessment_count = int(
            (await db.execute(select(func.count(RiskAssessment.assessment_id)))).scalar_one()
        )
        feature_count = int(
            (await db.execute(select(func.count(RiskFeature.feature_id)))).scalar_one()
        )
        assert assessment_count == 8
        assert feature_count == 8 * 25


async def test_generator_rejects_reusing_same_prefix(session_factory):
    config = GenerationConfig(
        users=10, transactions=10, loans=0,
        logins_per_user_min=1, logins_per_user_max=1,
        candidate_count=8, risk_ratio=0.875, days=30,
        seed=7, prefix="DUP",
    )
    async with session_factory() as db:
        async with db.begin():
            await generate_bank_data(db, config)
        try:
            async with db.begin():
                await generate_bank_data(db, config)
        except RuntimeError as exc:
            assert "不会自动覆盖" in str(exc)
        else:
            raise AssertionError("相同前缀应被拒绝，防止静默覆盖或误删")


async def test_replay_script_closes_read_transaction_before_process_event(
    session_factory, monkeypatch, tmp_path
):
    """回归：存在性 SELECT 自动开事务后，process_event 仍应能开始原子写事务。"""

    from scripts import gen_risk_data_with_dates as replay

    config = GenerationConfig(
        users=10, transactions=10, loans=0,
        logins_per_user_min=1, logins_per_user_max=1,
        candidate_count=8, risk_ratio=0.875, days=30,
        seed=11, prefix="RPL",
    )
    async with session_factory() as db:
        async with db.begin():
            await seed_rules(db)
            summary, candidates = await generate_bank_data(db, config)
    manifest = tmp_path / "manifest.json"
    save_manifest(manifest, config=config, summary=summary, candidates=candidates)

    class DummyEngine:
        async def dispose(self):
            return None

    monkeypatch.setattr(replay, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(replay, "async_engine", DummyEngine())
    await replay.run(
        Namespace(manifest=manifest, limit=1, progress_every=100, allow_model=False)
    )
    async with session_factory() as db:
        count = int(
            (await db.execute(select(func.count(RiskAssessment.assessment_id)))).scalar_one()
        )
    assert count == 1
