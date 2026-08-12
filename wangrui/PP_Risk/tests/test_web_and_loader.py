from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models_business import BUSINESS_MODELS
from scripts.load_simulated_data import _convert
from sqlalchemy import Boolean, Column, DateTime, Numeric


def test_required_web_routes_are_registered() -> None:
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "PP Risk" in response.text
        assert client.get("/transactions").status_code == 200
        assert client.get("/interactions").status_code == 200


def test_frontend_assets_exist() -> None:
    for path in (
        Path("templates/base.html"),
        Path("templates/dashboard.html"),
        Path("static/app.css"),
        Path("static/app.js"),
    ):
        assert path.is_file()


def test_loader_converts_database_types() -> None:
    assert _convert(Column(Boolean), "1") is True
    assert str(_convert(Column(Numeric(10, 2)), "12.50")) == "12.50"
    assert _convert(Column(DateTime(timezone=True)), "2026-08-11T00:00:00Z").year == 2026


def test_loader_targets_all_40_business_models() -> None:
    assert len(BUSINESS_MODELS) == 40
