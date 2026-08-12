from httpx import ASGITransport, AsyncClient

from app.api import app


async def test_all_seven_management_pages_and_static_asset_are_available() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for path in ("/", "/rules", "/cases", "/assessments", "/risk-check", "/chat", "/blacklist"):
            response = await client.get(path)
            assert response.status_code == 200, path
            assert "风控中心" in response.text
        static_response = await client.get("/static/app.js")

    assert static_response.status_code == 200
    assert "content-type" in static_response.headers


async def test_root_is_business_dashboard_while_docs_remains_available() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        root = await client.get("/")
        docs = await client.get("/docs")

    assert "银行风险态势总览" in root.text
    assert docs.status_code == 200
    assert "swagger-ui" in docs.text
