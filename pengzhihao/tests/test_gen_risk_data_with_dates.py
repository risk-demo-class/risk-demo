"""固定种子物流造数脚本测试。"""
from scripts.gen_business_data import SEED, build_rows


def test_business_data_is_deterministic():
    first = build_rows(SEED)
    second = build_rows(SEED)
    assert first == second


def test_business_data_volume_and_risk_coverage():
    users, addresses, shipments, items, extras = build_rows(SEED)
    assert len(users) == 80
    assert len(addresses) == 100
    assert len(shipments) == 300
    assert len(items) >= 300
    assert extras
    patterns = {row["risk_pattern"] for row in shipments if row["risk_pattern"]}
    assert patterns == {
        "实名信息异常",
        "危险品瞒报",
        "跨境重量申报异常",
        "代收货款高拒收",
        "高频凌晨寄件",
        "共享临时偏远地址",
    }


def test_positive_ratio_is_stable():
    shipments = build_rows(SEED)[2]
    positives = sum(row["risk_label"] for row in shipments)
    assert positives == 90
