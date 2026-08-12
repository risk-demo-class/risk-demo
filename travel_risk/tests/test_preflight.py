"""启动自检单测: 依赖检查 / 端口检查 / 模型检查 均不依赖真实 DB"""
import os
import sys

from run_app import (
    _check_dependencies,
    _check_port_available,
    _check_xgb_model,
    preflight_checks,
)


def test_check_dependencies_ok():
    level, msg = _check_dependencies()
    assert level in ("OK", "FAIL")
    if level == "OK":
        assert "已装" in msg


def test_check_port_free():
    level, msg = _check_port_available(18080)
    assert level in ("OK", "WARN")


def test_check_xgb_model_returns_tuple():
    level, msg = _check_xgb_model()
    assert level in ("OK", "WARN")
    assert isinstance(msg, str)


def test_preflight_returns_six_results():
    results = preflight_checks()
    assert len(results) == 6
    for level, name, msg in results:
        assert level in ("OK", "WARN", "FAIL")
        assert isinstance(name, str)
        assert isinstance(msg, str)
