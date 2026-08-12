"""
API 冒烟测试: 启动服务后验证全部核心接口.
用法: python scripts/api_smoke.py
"""
import json
import os
import sys

import httpx

BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")


def check(name: str, resp: httpx.Response, expect_status: int = 200) -> None:
    ok = resp.status_code == expect_status
    marker = "OK " if ok else "FAIL"
    print(f"[{marker}] {name}: HTTP {resp.status_code}")
    if not ok:
        print(f"        body: {resp.text[:300]}")
    assert ok, f"{name} 期望 {expect_status}, 实际 {resp.status_code}"


def main():
    client = httpx.Client(base_url=BASE, timeout=30)
    test_rule_id = f"R9{os.getpid() % 90:02d}"
    test_bl_value = f"SMOKE{os.getpid()}"

    # 页面
    for path in ["/", "/rules", "/cases", "/assessments", "/risk-check", "/blacklist", "/chat"]:
        resp = client.get(path)
        check(f"页面 {path}", resp)

    # 仪表盘
    resp = client.get("/api/dashboard/stats")
    check("仪表盘统计", resp)
    stats = resp.json()
    print(f"   -> 订单 {stats['total_bookings']}, 规则 {stats['enabled_rules']}, 评估 {stats['assessments']}, 待审 {stats['pending_cases']}")

    # 规则列表
    resp = client.get("/api/rules", params={"page": 1, "page_size": 5})
    check("规则列表", resp)
    rules = resp.json()
    print(f"   -> 规则总数 {rules['total']}")

    # 规则详情 + 启停
    resp = client.get("/api/rules/R001")
    check("规则详情 R001", resp)
    resp = client.patch("/api/rules/R001/toggle")
    check("规则启停 R001", resp)
    client.patch("/api/rules/R001/toggle")  # 恢复

    # 新增临时规则 + 更新 + 删除
    rule_body = {
        "rule_id": test_rule_id, "rule_name": "冒烟测试规则", "rule_category": "综合风险",
        "event_type": "通用", "rule_condition": {"field": "user_total_bookings", "op": ">=", "value": 100},
        "risk_level": "高", "risk_score": 70, "action": "人工审核", "priority": 0,
        "description": "API 冒烟测试",
    }
    resp = client.post("/api/rules", json=rule_body)
    check(f"新增规则 {test_rule_id}", resp, 200)
    resp = client.put(f"/api/rules/{test_rule_id}", json={"rule_name": "冒烟测试规则-改"})
    check(f"更新规则 {test_rule_id}", resp)
    resp = client.delete(f"/api/rules/{test_rule_id}")
    check(f"删除规则 {test_rule_id}", resp)

    # 风控检查 (下单 → 大额拒绝)
    resp = client.post("/api/risk/check", json={
        "event_type": "下单", "source_id": "RISKB00200", "user_id": "RISK002",
        "event_data": {"booking_id": "RISKB00200"},
    })
    check("风控检查 RISK002", resp)
    r = resp.json()
    print(f"   -> 评分 {r['final_score']}, 决策 {r['decision']}, 命中 {r['rule_count']} 条规则, ML={r['ml_score']}")

    # 退改申请事件
    resp = client.post("/api/risk/check", json={
        "event_type": "退改申请", "source_id": "RF001", "user_id": "U001",
        "event_data": {"refund_id": "RF001"},
    })
    check("风控检查 退改申请 RF001", resp)

    # 理赔申请事件
    resp = client.post("/api/risk/check", json={
        "event_type": "理赔申请", "source_id": "CL001", "user_id": "U002",
        "event_data": {"claim_id": "CL001"},
    })
    check("风控检查 理赔申请 CL001", resp)

    # 灵活入参: 只给用户ID / 只给设备ID / 只给业务ID
    resp = client.post("/api/risk/check", json={"user_id": "U003"})
    check("风控检查 仅用户ID", resp)
    r = resp.json()
    print(f"   -> 事件={r.get('event_type', '')}, 决策={r['decision']}")

    resp = client.post("/api/risk/check", json={"device_id": "DEV001"})
    check("风控检查 仅设备ID", resp)

    resp = client.post("/api/risk/check", json={"source_id": "RISKB00200"})
    check("风控检查 仅业务ID", resp)
    r = resp.json()
    print(f"   -> 识别用户={r['user_id']}, 决策={r['decision']}")

    resp = client.post("/api/risk/check", json={})
    check("风控检查 空入参应拒绝", resp, 400)

    # 黑名单
    resp = client.get("/api/blacklists")
    check("黑名单列表", resp)
    resp = client.post("/api/blacklists", json={
        "blacklist_type": "用户", "blacklist_value": test_bl_value, "reason": "冒烟测试",
    })
    check("新增黑名单", resp)
    bl_id = resp.json()["blacklist_id"]
    resp = client.delete(f"/api/blacklists/{bl_id}")
    check("删除黑名单", resp)

    # 案件
    resp = client.get("/api/cases", params={"page": 1, "page_size": 5})
    check("案件列表", resp)
    cases = resp.json()
    print(f"   -> 案件总数 {cases['total']}")
    if cases["items"]:
        cid = cases["items"][0]["case_id"]
        resp = client.get(f"/api/cases/{cid}")
        check("案件详情", resp)

    # 评估历史
    resp = client.get("/api/assessments", params={"page": 1, "page_size": 5})
    check("评估历史列表", resp)
    assessments = resp.json()
    print(f"   -> 评估总数 {assessments['total']}")
    if assessments["items"]:
        aid = assessments["items"][0]["assessment_id"]
        resp = client.get(f"/api/assessments/{aid}")
        check("评估详情", resp)

    # 画像
    resp = client.get("/api/profile/U003")
    check("用户画像 U003", resp)

    # Agent
    resp = client.get("/api/agent/health")
    check("Agent 健康检查", resp)
    resp = client.post("/api/agent/chat", json={"message": "有哪些风险规则"})
    check("Agent 对话", resp)
    print(f"   -> {resp.json()['reply'][:60]}...")

    # 告警
    resp = client.post("/api/alerts/check")
    check("告警手动检查", resp)
    resp = client.get("/api/alerts")
    check("告警列表", resp)

    print("\nAPI 冒烟测试全部通过 ✔")


if __name__ == "__main__":
    main()
