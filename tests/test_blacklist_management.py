from fastapi.testclient import TestClient


def test_blacklist_api_supports_filtered_create_and_remove_flow():
    from app.main import app

    client = TestClient(app)
    created = client.post(
        "/api/blacklist",
        json={
            "blacklist_type": "设备哈希",
            "blacklist_value": "device-demo-black-hash",
            "reason": "演示用关联设备风险",
        },
    )

    assert created.status_code == 201
    created_item = created.json()
    assert created_item["blacklist_type"] == "设备哈希"
    assert created_item["blacklist_value"] == "device-demo-black-hash"

    filtered = client.get("/api/blacklist?blacklist_type=设备哈希")

    assert filtered.status_code == 200
    assert filtered.json()["total"] >= 1
    assert all(item["blacklist_type"] == "设备哈希" for item in filtered.json()["items"])

    removed = client.delete(f"/api/blacklist/{created_item['blacklist_id']}")

    assert removed.status_code == 200
    assert removed.json()["detail"] == "已移除"


def test_blacklist_page_is_available_from_the_source_style_route():
    from app.main import app

    response = TestClient(app).get("/blacklist")

    assert response.status_code == 200
    assert "教育风控黑名单管理" in response.text
    assert 'id="blacklistTableBody"' in response.text
