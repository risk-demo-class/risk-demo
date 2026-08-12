"""A～F教学场景与预置教育规则的确定性命中测试。"""
import json
from pathlib import Path
import re

from app.engine.rule import evaluate_condition


ROOT = Path(__file__).resolve().parents[1]


def _conditions() -> dict[str, dict]:
    rules = {}
    for line in (ROOT / "sql" / "init_risk_data.sql").read_text(encoding="utf-8").splitlines():
        id_match = re.match(r"\('(?P<id>R\d{3})'", line)
        condition_match = re.search(r"'(\{.*\})','(?:低|中|高|极高)'", line)
        if id_match and condition_match:
            rules[id_match.group("id")] = json.loads(condition_match.group(1))
    return rules


def test_all_seven_rule_conditions_are_valid_json():
    assert set(_conditions()) == {"R001", "R002", "R005", "R008", "R012", "R025", "R030"}


def test_b_zero_study_refund_hits_r002():
    assert evaluate_condition(_conditions()["R002"], {"refund_study_minutes": 1, "refund_amount": 8999})


def test_c_refund_chain_hits_r012():
    assert evaluate_condition(_conditions()["R012"], {"user_refund_count_90d": 4, "user_refund_amount_90d": 24000})


def test_d_shared_device_hits_veto_r008_and_r001():
    features = {
        "device_distinct_users_30d": 6,
        "course_new_account_purchase_count_7d": 6,
        "user_account_age_days": 2,
    }
    assert evaluate_condition(_conditions()["R008"], features)
    assert evaluate_condition(_conditions()["R001"], features)


def test_e_high_amount_hits_r005():
    assert evaluate_condition(_conditions()["R005"], {"user_purchase_amount_1h": 36000})


def test_f_black_identity_hits_r030():
    features = {"student_id_blacklisted": 1, "id_card_blacklisted": 0, "device_id_blacklisted": 0}
    assert evaluate_condition(_conditions()["R030"], features)


def test_teacher_buying_student_courses_hits_r025():
    features = {
        "user_role_teacher_flag": 1,
        "course_is_student_only": 1,
        "student_only_purchase_count_30d": 3,
    }
    assert evaluate_condition(_conditions()["R025"], features)
