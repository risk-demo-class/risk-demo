from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def test_login_rule_groups_and_permission_boundary() -> None:
    suffix = uuid4().hex[:8]
    role_code = f"TEST_VIEWER_{suffix.upper()}"
    username = f"测试员_{suffix}"
    password = "viewer123456"

    with TestClient(app, follow_redirects=False) as anonymous:
        assert anonymous.get("/api/dashboard").status_code == 401
        assert anonymous.get("/").status_code == 303
        assert anonymous.post(
            "/api/auth/login", json={"username": "administer", "password": "wrong-password"}
        ).status_code == 401

    with TestClient(app) as admin:
        response = admin.post(
            "/api/auth/login", json={"username": "administer", "password": "123456"}
        )
        assert response.status_code == 200
        me = admin.get("/api/auth/me").json()
        assert "iam:manage" in me["permissions"]

        orders_asc = admin.get(
            "/api/orders", params={"sort_by": "risk_score", "sort_order": "asc", "page_size": 100}
        )
        assert orders_asc.status_code == 200
        order_scores = [item["risk_score"] for item in orders_asc.json()["items"]]
        assert order_scores == sorted(order_scores)
        order_detail = admin.get(
            f"/api/orders/{orders_asc.json()['items'][0]['order_id']}"
        )
        assert order_detail.status_code == 200
        assessment = order_detail.json()["assessment"]
        assert 0 <= assessment["model_probability"] <= 1
        assert 0 <= assessment["model_score"] <= 100
        assert assessment["model_version"].startswith("xgb-")

        reviews_desc = admin.get(
            "/api/reviews",
            params={"status": "PENDING", "sort_by": "risk_score", "sort_order": "desc", "page_size": 100},
        )
        assert reviews_desc.status_code == 200
        review_scores = [item["risk_score"] for item in reviews_desc.json()["items"]]
        assert review_scores == sorted(review_scores, reverse=True)

        blacklist_asc = admin.get(
            "/api/blacklist", params={"sort_by": "entry_id", "sort_order": "asc", "page_size": 100}
        )
        assert blacklist_asc.status_code == 200
        blacklist_ids = [item["entry_id"] for item in blacklist_asc.json()["items"]]
        assert blacklist_ids == sorted(blacklist_ids)

        audit_asc = admin.get(
            "/api/audit", params={"sort_by": "operator", "sort_order": "asc", "page_size": 100}
        )
        assert audit_asc.status_code == 200
        audit_operators = [item["operator"] for item in audit_asc.json()["items"]]
        assert audit_operators == sorted(audit_operators)
        assert admin.get("/api/orders", params={"sort_by": "unsafe_column"}).status_code == 422

        groups = admin.get("/api/rule-groups")
        assert groups.status_code == 200
        assert len(groups.json()["items"]) == 8

        overview = admin.get("/api/iam/overview").json()
        dashboard_permission = next(
            item for item in overview["permissions"] if item["permission_code"] == "dashboard:view"
        )
        role_response = admin.post(
            "/api/iam/roles",
            json={
                "role_code": role_code,
                "role_name": "自动化只读测试",
                "description": "集成测试临时角色",
                "permission_ids": [dashboard_permission["permission_id"]],
            },
        )
        assert role_response.status_code == 201
        role_id = role_response.json()["role_id"]
        user_id = None
        try:
            legacy_response = admin.post(
                "/api/iam/users",
                json={
                    "username": f"legacy_{suffix}",
                    "display_name": "旧多角色请求",
                    "password": password,
                    "role_ids": [role_id],
                },
            )
            assert legacy_response.status_code == 422
            user_response = admin.post(
                "/api/iam/users",
                json={
                    "username": username,
                    "display_name": "权限边界测试",
                    "password": password,
                    "role_id": role_id,
                },
            )
            assert user_response.status_code == 201
            assert [item["role_id"] for item in user_response.json()["roles"]] == [role_id]
            user_id = user_response.json()["staff_user_id"]

            with TestClient(app) as viewer:
                assert viewer.post(
                    "/api/auth/login", json={"username": username, "password": password}
                ).status_code == 200
                assert viewer.get("/api/dashboard").status_code == 200
                assert viewer.get("/api/orders").status_code == 403
                assert viewer.get("/api/iam/overview").status_code == 403
        finally:
            if user_id is not None:
                assert admin.delete(f"/api/iam/users/{user_id}").status_code == 200
            assert admin.delete(f"/api/iam/roles/{role_id}").status_code == 200
