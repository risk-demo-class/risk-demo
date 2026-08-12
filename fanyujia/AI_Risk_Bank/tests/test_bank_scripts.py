"""银行造数脚本应能从项目根目录直接运行。"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("script", ["gen_business_data.py", "gen_bank_risk_data.py"])
def test_bank_generator_script_can_show_help_when_run_directly(script: str) -> None:
    result = subprocess.run(
        [sys.executable, f"scripts/{script}", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_bank_application_imports_without_ecommerce_models() -> None:
    """银行应用启动时不应再依赖已移除的电商 ORM 模型。"""
    result = subprocess.run(
        [sys.executable, "-c", "from scripts.main import app; print(app.title)"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        check=False,
    )

    assert result.returncode == 0, result.stderr
