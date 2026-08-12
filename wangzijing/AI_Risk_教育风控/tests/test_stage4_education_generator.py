"""教育版批量风控数据脚本的轻量回归测试。"""
import random
from pathlib import Path

from scripts.gen_education_risk_data import EventSource, choose_source


ROOT = Path(__file__).resolve().parent.parent


def test_generator_only_uses_education_event_types_and_tables():
    source = (ROOT / "scripts" / "gen_education_risk_data.py").read_text(encoding="utf-8")
    for event_type in ("课程报名", "退费申请", "学历认证"):
        assert event_type in source
    for legacy_table in ("region", "sku_info", "postsale", "logistics_complaints"):
        assert legacy_table not in source


def test_risk_ratio_one_always_chooses_risk_source():
    normal = EventSource("课程报名", "ORD001", "EDU001")
    risky = EventSource("退费申请", "REF001", "RISK001")
    rng = random.Random(7)
    assert all(
        choose_source([normal, risky], [risky], risk_ratio=1.0, rng=rng).is_risky
        for _ in range(20)
    )

