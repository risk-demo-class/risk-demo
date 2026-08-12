"""启动制造业风控 Web 服务。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="启动制造业风控 Web 服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--reload", action="store_true", help="开发调试时开启自动重载")
    args = parser.parse_args()
    print(f"Web 服务启动：http://{args.host}:{args.port}")
    uvicorn.run("web_app:app", host=args.host, port=args.port, reload=args.reload)