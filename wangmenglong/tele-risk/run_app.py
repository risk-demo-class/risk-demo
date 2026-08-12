"""
电信风控系统 - 一键启动脚本 (带自检).

启动前自检:
  1. MySQL 是否在跑 (localhost:3306)
  2. 数据库是否已初始化 (telecom_risk_rule 表能否查询)
  3. XGBoost 模型文件是否存在 (可选)
  4. 8001 端口是否被占

跑法: python run_app.py
"""
import os
import socket
import sys

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pymysql  # noqa: E402


def _check_mysql():
    """检查 MySQL + telecom 库."""
    try:
        conn = pymysql.connect(
            host="localhost", port=3306, user="root", password="123321",
            database="telecom", connect_timeout=3,
        )
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM telecom_risk_rule")
            count = cur.fetchone()[0]
        conn.close()
        return "OK", f"MySQL 可连, telecom_risk_rule 有 {count} 条规则"
    except pymysql.err.OperationalError as e:
        if "Unknown database" in str(e):
            return "WARN", "telecom 库不存在, 跑: python scripts/init_db.py --yes && python scripts/init_rules.py --yes"
        if "doesn't exist" in str(e).lower():
            return "WARN", "telecom_risk_rule 表不存在, 跑: python scripts/init_rules.py --yes"
        return "WARN", f"MySQL 连不上: {e}"
    except Exception as e:
        return "WARN", f"MySQL 状态未知: {e}"


def _check_port(port=8001):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        sock.bind(("0.0.0.0", port))
        return "OK", f"端口 {port} 空闲"
    except OSError:
        return "WARN", f"端口 {port} 被占"
    finally:
        sock.close()


def _check_xgb_model():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "engine", "xgb_model.json")
    if os.path.exists(path):
        return "OK", f"XGBoost 模型存在 ({os.path.getsize(path) // 1024} KB)"
    return "WARN", "XGBoost 模型不存在 (纯规则模式可跑), 训练: python scripts/train_xgb_model.py"


def main():
    print("=" * 60)
    print("【电信风控系统 - 启动自检】")
    print("=" * 60)
    checks = [
        ("MySQL", _check_mysql),
        ("端口 8001", lambda: _check_port(8001)),
        ("XGBoost 模型", _check_xgb_model),
    ]
    has_fail = False
    for name, fn in checks:
        try:
            level, msg = fn()
        except Exception as e:
            level, msg = "WARN", f"自检异常: {e}"
        mark = {"OK": "OK", "WARN": "WARN"}.get(level, "??")
        print(f"  [{mark}] {name:<14} {msg}")
        if level == "FAIL":
            has_fail = True
    print("=" * 60)
    if has_fail:
        print("有致命问题, 启动取消.")
        sys.exit(1)

    print("启动 uvicorn (端口 8001)...")
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=False)


if __name__ == "__main__":
    main()
