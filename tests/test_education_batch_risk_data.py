from scripts.gen_risk_data import build_education_requests


def test_batch_requests_cover_all_education_event_types():
    requests = build_education_requests(
        enrollments=[("enr_001", "edu_001")],
        refunds=[("ref_001", "edu_002")],
        rewards=[("reward_001", "edu_003")],
        count=3,
    )

    assert [(item.event_type, item.source_id, item.user_id) for item in requests] == [
        ("课程报名", "enr_001", "edu_001"),
        ("退费申请", "ref_001", "edu_002"),
        ("直播打赏", "reward_001", "edu_003"),
    ]
