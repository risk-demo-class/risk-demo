"""对已启动的本地服务执行只读演示；风险检查需显式参数。"""
from __future__ import annotations

import argparse
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def call(base_url: str, path: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
    request = Request(
        base_url + path,
        data=body,
        headers={"Content-Type": "application/json", "X-Operator": "demo-smoke"},
        method="POST" if payload else "GET",
    )
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="医疗风控本地烟雾演示")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--with-risk-check", action="store_true", help="显式新增一次 CLM0000001 风险评估")
    args = parser.parse_args()
    try:
        health = call(args.base_url, "/health")
        overview = call(args.base_url, "/api/dashboard/overview")
        assistant = call(args.base_url, "/api/agent/chat", {"question": "当前待审核案件数量？"})
        result = {"health": health, "overview": overview, "assistant": assistant}
        if args.with_risk_check:
            result["risk_check"] = call(args.base_url, "/api/risk/check", {
                "event_type": "医保结算",
                "source_id": "CLM0000001",
                "user_id": "PAT000001",
                "event_data": {"channel": "demo-smoke"},
            })
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except HTTPError as exc:
        raise SystemExit(f"请求失败: HTTP {exc.code} {exc.read().decode('utf-8', errors='replace')}") from exc


if __name__ == "__main__":
    main()
