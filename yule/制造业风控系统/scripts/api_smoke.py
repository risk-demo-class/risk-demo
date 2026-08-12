"""
制造业风控系统 - Web API 冒烟验证 (需要服务已启动: python scripts/main.py)

用法:
  python scripts/api_smoke.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx


BASE = "http://localhost:8000"


def main():
    with httpx.Client(timeout=30) as client:
        # 1. 设备保修
        r = client.post(BASE + "/api/risk/check", json={
            "event_type": "设备保修", "source_id": "WR_002_01", "user_id": "RISK002",
        })
        print("POST 设备保修:", r.status_code)
        if r.status_code == 200:
            d = r.json()
            print(f"  decision={d['decision']} score={d['final_score']} level={d['risk_level']} ml={d['ml_score']}")
            print(f"  rules={[(h['rule_id'], h['rule_name']) for h in d['triggered_rules']]}")

        # 2. 经销商订货 (大额囤货)
        r2 = client.post(BASE + "/api/risk/check", json={
            "event_type": "经销商订货", "source_id": "ORD_003_001",
            "user_id": "RISK003", "order_id": "ORD_003_001",
        })
        print("\nPOST 经销商订货:", r2.status_code)
        if r2.status_code == 200:
            d = r2.json()
            print(f"  decision={d['decision']} score={d['final_score']} level={d['risk_level']}")
            print(f"  rules={[h['rule_id'] for h in d['triggered_rules']]}")

        # 3. 黑名单经销商拦截
        r3 = client.post(BASE + "/api/risk/check", json={
            "event_type": "经销商订货", "source_id": "ORD_008_001",
            "user_id": "RISK008", "order_id": "ORD_008_001",
        })
        print("\nPOST 黑经销商拦截:", r3.status_code)
        if r3.status_code == 200:
            d = r3.json()
            print(f"  decision={d['decision']} blocked_by={d.get('blocked_by')}")


if __name__ == "__main__":
    main()
