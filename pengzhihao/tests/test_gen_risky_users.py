"""物流风险样本构造覆盖。"""
from scripts.gen_business_data import SEED, build_rows


def test_six_named_high_risk_senders_exist():
    users, _, shipments, _, _ = build_rows(SEED)
    user_ids = {row["user_id"] for row in users}
    special = {"U_RNAME", "U_DANGER", "U_CROSS", "U_COD", "U_FREQ", "U_ADDR"}
    assert special <= user_ids
    assert special <= {row["sender_id"] for row in shipments if row["risk_label"] == 1}


def test_each_risk_sender_has_stable_samples():
    shipments = build_rows(SEED)[2]
    counts = {}
    for shipment in shipments:
        if shipment["risk_label"]:
            counts[shipment["sender_id"]] = counts.get(shipment["sender_id"], 0) + 1
    assert counts == {
        "U_RNAME": 15,
        "U_DANGER": 15,
        "U_CROSS": 15,
        "U_COD": 15,
        "U_FREQ": 15,
        "U_ADDR": 15,
    }
