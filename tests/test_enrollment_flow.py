from fastapi.testclient import TestClient


def test_normal_enrollment_returns_a_pass_decision():
    from app.main import app

    client = TestClient(app)
    response = client.post(
        "/api/risk/check",
        json={
            "event_type": "课程报名",
            "source_id": "ENR-NORMAL-001",
            "user_id": "STU-NORMAL-001",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "通过"
    assert body["rule_count"] == 0


def test_shared_device_enrollment_requires_manual_review():
    from app.main import app

    client = TestClient(app)
    response = client.post(
        "/api/risk/check",
        json={
            "event_type": "课程报名",
            "source_id": "ENR-RISK-001",
            "user_id": "STU-RISK-01",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "人工审核"
    assert body["rule_count"] == 1
    assert body["triggered_rules"][0]["rule_id"] == "EDU-RULE-001"


def test_blacklisted_enrollment_is_rejected_before_rule_engine():
    from app.main import app

    client = TestClient(app)
    response = client.post(
        "/api/risk/check",
        json={
            "event_type": "课程报名",
            "source_id": "ENR-BLACK-001",
            "user_id": "STU-BLACK-001",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "拒绝"
    assert body["blocked_by"] == "用户黑名单"
    assert body["rule_count"] == 0


def test_low_study_refund_requires_manual_review_and_creates_an_audit_record():
    from app.main import app

    client = TestClient(app)
    response = client.post(
        "/api/risk/check",
        json={
            "event_type": "退费申请",
            "source_id": "REF-RISK-001",
            "user_id": "STU-REFUND-001",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "人工审核"
    assert body["triggered_rules"][0]["rule_id"] == "EDU-RULE-REFUND-001"
    assessment_items = client.get("/api/assessments").json()["items"]
    assert any(item["event_type"] == "退费申请" for item in assessment_items)


def test_repeated_credential_failures_require_manual_review():
    from app.main import app

    client = TestClient(app)
    response = client.post(
        "/api/risk/check",
        json={
            "event_type": "学历认证",
            "source_id": "VER-RISK-003",
            "user_id": "STU-VERIFY-001",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "人工审核"
    assert body["triggered_rules"][0]["rule_id"] == "EDU-RULE-VERIFY-001"
