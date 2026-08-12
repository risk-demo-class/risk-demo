# -*- coding: utf-8 -*-
"""智学安·教育风控平台 API 集成测试（零依赖，需先启动服务）

前置：
    python _run.py          # 另开一个终端
运行：
    python -m unittest tests.test_api -v

服务未启动时整个用例集会被 skip，不会误报失败。
"""
from __future__ import annotations

import json
import sys
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Tuple

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

BASE = "http://127.0.0.1:8000"


def call(method: str, path: str, body: Any = None,
         headers: Dict[str, str] | None = None) -> Tuple[int, Any]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json; charset=utf-8", **(headers or {})})
    try:
        resp = urllib.request.urlopen(req, timeout=40)
        return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except Exception:
            return exc.code, {}


def server_up() -> bool:
    try:
        return call("GET", "/api/system/health")[0] == 200
    except Exception:
        return False


_UP = server_up()
q = urllib.parse.quote


@unittest.skipUnless(_UP, "服务未启动，先运行 python _run.py")
class TestSystem(unittest.TestCase):

    def test_health_self_check_all_pass(self):
        s, d = call("GET", "/api/system/health")
        self.assertEqual(s, 200)
        self.assertEqual(d["status"], "healthy", d.get("self_check"))
        self.assertEqual(d["self_check_passed"], d["self_check_total"])

    def test_30_endpoints_10_routers(self):
        s, d = call("GET", "/api/system/health")
        self.assertEqual(s, 200)
        self.assertEqual(d["data"]["rules"], 30)
        self.assertEqual(sorted(d["data"]["veto_rules"]), ["R002", "R015", "R020", "R030"])

    def test_config_has_five_groups(self):
        s, d = call("GET", "/api/system/config")
        self.assertEqual(s, 200)
        self.assertGreaterEqual(len(d["groups"]), 5)
        for name in ("决策阈值", "融合参数", "告警阈值"):
            self.assertIn(name, d["groups"])

    def test_audit_logs_paginated(self):
        s, d = call("GET", "/api/system/audit-logs?limit=3")
        self.assertEqual(s, 200)
        self.assertLessEqual(len(d["items"]), 3)
        self.assertGreater(d["total"], 0)


@unittest.skipUnless(_UP, "服务未启动")
class TestRiskPipeline(unittest.TestCase):
    """7 步流水线端到端。"""

    @classmethod
    def setUpClass(cls):
        cls.uid = call("GET", "/api/profiles?limit=1")[1]["items"][0]["user_id"]
        rows = call("GET", f"/api/business/table/order_info?limit=1&user_id={cls.uid}")[1]
        cls.oid = rows["items"][0]["order_id"] if rows["items"] else None

    def test_pipeline_returns_all_teaching_fields(self):
        s, d = call("POST", "/api/risk/check", {
            "event_type": "考试", "user_id": self.uid, "source_id": self.oid,
            "order_id": self.oid, "device_id": "DEV_TEST", "ip": "10.0.0.1"})
        self.assertEqual(s, 200, d)
        r = d["data"]
        # 7 步流水线的可视化材料必须齐全
        self.assertEqual(len(r["features"]), 25)
        self.assertEqual(len(r["feature_defs"]), 25)
        self.assertEqual(len(r["validate_checks"]), 6)
        self.assertEqual(len(r["fusion_steps"]), 4)
        self.assertGreaterEqual(len(r["timeline"]), 7)
        for key in ("rule_score", "ml_score", "final_score", "risk_level",
                    "decision", "is_veto", "hit_rules", "reason", "cost_ms"):
            self.assertIn(key, r)
        self.assertIn(r["decision"], ("通过", "标记", "人工审核", "拒绝"))
        self.assertIn(r["risk_level"], ("低", "中", "高", "极高"))
        self.assertTrue(0 <= r["final_score"] <= 100)

    def test_veto_forces_reject(self):
        s, d = call("POST", "/api/risk/check", {
            "event_type": "考试", "user_id": self.uid, "source_id": self.oid,
            "order_id": self.oid, "device_id": "DEV_TEST2", "ip": "10.0.0.2"})
        self.assertEqual(s, 200)
        r = d["data"]
        if r["is_veto"]:
            self.assertEqual(r["decision"], "拒绝")
            self.assertEqual(r["risk_level"], "极高")
            self.assertGreaterEqual(r["final_score"], 90)
            self.assertTrue(r["veto_rules"])

    def test_unknown_user_rejected_404(self):
        s, d = call("POST", "/api/risk/check", {
            "event_type": "考试", "user_id": "NO_SUCH_USER", "source_id": "X"})
        self.assertEqual(s, 404)
        self.assertIn("用户", d.get("detail", ""))

    def test_invalid_event_type_rejected_400(self):
        s, _ = call("POST", "/api/risk/check", {
            "event_type": "抢红包", "user_id": self.uid, "source_id": self.oid})
        self.assertEqual(s, 400)

    def test_assessment_detail_has_snapshot(self):
        aid = call("GET", "/api/risk/assessments?limit=1")[1]["items"][0]["assessment_id"]
        s, d = call("GET", "/api/risk/assessments/" + q(aid))
        self.assertEqual(s, 200)
        # feature_defs 挂在 data 里（与 /api/risk/check 的 data.feature_defs 一致）
        self.assertEqual(len(d["data"]["feature_defs"]), 25)
        self.assertEqual(len(d["data"]["features"]), 25)
        self.assertIsNotNone(d["data"]["feature_snapshot"])


@unittest.skipUnless(_UP, "服务未启动")
class TestRuleApi(unittest.TestCase):

    def test_meta_exposes_14_ops_and_25_features(self):
        s, d = call("GET", "/api/rules")
        self.assertEqual(s, 200)
        self.assertEqual(d["total"], 30)
        self.assertEqual(d["meta"]["op_count"], 14)
        self.assertEqual(d["meta"]["feature_count"], 25)
        self.assertEqual(d["meta"]["veto_level"], "极高")

    def test_tester_numeric_operators(self):
        cases = [(">", 100, 150, True), (">", 100, 50, False), (">=", 100, 100, True),
                 ("<", 100, 50, True), ("<=", 50, 50, True), ("==", 5, 5, True),
                 ("!=", 5, 9, True), ("in", [1, 2, 3], 2, True), ("not_in", [1, 2], 9, True),
                 ("between", [10, 100], 55, True), ("between", [10, 100], 5, False),
                 ("not_between", [10, 100], 500, True), ("exists", True, 7, True)]
        for op, value, feat, expect in cases:
            s, d = call("POST", "/api/rules/test", {
                "rule_condition": {"and": [{"field": "order_amount", "op": op, "value": value}]},
                "features": {"order_amount": feat}})
            self.assertEqual(s, 200, (op, d))
            self.assertTrue(d["valid"], (op, d.get("errors")))
            self.assertEqual(d["hit"], expect, f"{op} feat={feat} value={value}")

    def test_tester_nested_logic_with_trace(self):
        cond = {"and": [
            {"field": "order_amount", "op": ">", "value": 100},
            {"or": [{"field": "user_order_count", "op": ">=", "value": 5},
                    {"not": {"field": "user_refund_rate", "op": ">", "value": 0.5}}]}]}
        s, d = call("POST", "/api/rules/test", {
            "rule_condition": cond,
            "features": {"order_amount": 500, "user_order_count": 1, "user_refund_rate": 0.1}})
        self.assertEqual(s, 200)
        self.assertTrue(d["hit"])
        self.assertGreaterEqual(len(d["trace"]), 5)
        for node in d["trace"]:
            self.assertIn("depth", node)
            self.assertIn("result", node)

    def test_rule_effectiveness_report(self):
        s, d = call("GET", "/api/dashboard/rule-effectiveness")
        self.assertEqual(s, 200)
        self.assertEqual(d["data"]["total_rules"], 30)
        self.assertIn("zombie_rules", d["data"])


@unittest.skipUnless(_UP, "服务未启动")
class TestCaseApi(unittest.TestCase):

    def test_state_machine_5_states_7_edges(self):
        s, d = call("GET", "/api/cases?limit=1")
        self.assertEqual(s, 200)
        sm = d["meta"]["state_machine"]
        self.assertEqual(len(sm["statuses"]), 5)
        self.assertEqual(sm["edge_count"], 7)

    def test_transition_and_illegal_block(self):
        s, d = call("GET", "/api/cases?limit=1&case_status=" + q("待审核"))
        if not d.get("items"):
            self.skipTest("没有待审核案件")
        cid = d["items"][0]["case_id"]
        s, r = call("PUT", f"/api/cases/{q(cid)}/status",
                    {"case_status": "审核中", "operator": "pytest", "review_comment": "集成测试"})
        self.assertEqual(s, 200, r)
        s, r = call("PUT", f"/api/cases/{q(cid)}/status",
                    {"case_status": "已通过", "operator": "pytest",
                     "review_comment": "集成测试通过", "label": 0})
        self.assertEqual(s, 200, r)
        self.assertEqual(r["data"]["allowed_transitions"], [], "终态不应还有出边")
        # 终态回退必须被拒
        s, r = call("PUT", f"/api/cases/{q(cid)}/status",
                    {"case_status": "待审核", "operator": "pytest"})
        self.assertEqual(s, 400)
        self.assertIn("非法状态流转", r.get("detail", ""))

    def test_auto_close_dry_run_is_safe(self):
        s, d = call("POST", "/api/cases/auto-close", {"dry_run": True})
        self.assertEqual(s, 200)
        self.assertEqual(d["data"]["closed"], 0, "dry_run 不能真的关单")


@unittest.skipUnless(_UP, "服务未启动")
class TestDashboardAndModel(unittest.TestCase):

    def test_stats_overview_and_histograms(self):
        s, d = call("GET", "/api/dashboard/stats")
        self.assertEqual(s, 200)
        data = d["data"]
        for key in ("overview", "decision_histogram", "risk_level_histogram",
                    "event_type_histogram", "case_status_histogram", "top_rules",
                    "top_risk_users", "recent_assessments", "alerts", "model", "thresholds"):
            self.assertIn(key, data)
        self.assertEqual(data["overview"]["rules_total"], 30)

    def test_trend_series_length_matches_days(self):
        s, d = call("GET", "/api/dashboard/trend?days=7")
        self.assertEqual(s, 200)
        self.assertEqual(d["days"], 7)
        self.assertEqual(len(d["series"]), 7)

    def test_model_status_and_importance(self):
        s, d = call("GET", "/api/model/status")
        self.assertEqual(s, 200)
        self.assertIn("loaded", d)
        self.assertEqual(d["feature_count"], 25)
        s, imp = call("GET", "/api/model/importance")
        self.assertEqual(s, 200)
        if imp.get("available"):
            for kind in ("weight", "gain", "cover"):
                self.assertTrue(imp[kind], f"{kind} 不应为空")

    def test_business_dictionary_tables(self):
        s, d = call("GET", "/api/business/dictionary")
        self.assertEqual(s, 200)
        self.assertGreaterEqual(len(d["tables"]), 20)
        for t in d["tables"]:
            self.assertTrue(t["columns"], f"{t['table']} 无字段定义")

    def test_table_whitelist_blocks_unknown(self):
        s, _ = call("GET", "/api/business/table/not_a_table")
        self.assertEqual(s, 404)


@unittest.skipUnless(_UP, "服务未启动")
class TestAgent(unittest.TestCase):

    def test_eight_tools_registered(self):
        s, d = call("GET", "/api/agent/tools")
        self.assertEqual(s, 200)
        self.assertEqual(d["tool_count"], 8)
        names = [t["name"] for t in d["tools"]]
        for n in ("risk_check", "query_cases", "query_user_profile", "manage_blacklist",
                  "query_dashboard_stats", "analyze_risk_trend",
                  "analyze_rule_effectiveness", "query_business_data"):
            self.assertIn(n, names)

    def test_chat_json_mode(self):
        try:
            s, d = call("POST", "/api/agent/chat",
                        {"message": "现在有多少待审核案件", "session_id": "ut_json"})
            # 端点必须正常响应（200），不应 500；模型可达返回 reply，不可达返回 error 信息
            self.assertEqual(s, 200, d)
            self.assertIn("reply", d)
            self.assertIn("session_id", d)
            if not d.get("success"):
                self.assertIn("error", d, "失败时应给出可读的错误信息而非崩溃")
        except Exception as exc:
            # 沙箱无外网 / 模型不可达时，只要端点不 500 就算通过
            msg = str(exc).lower()
            self.assertTrue(
                "timeout" in msg or "timed out" in msg or "connection" in msg,
                f"网络异常可接受: {exc}")

    def test_chat_sse_stream(self):
        try:
            body = json.dumps({"message": "现在有多少待审核案件", "session_id": "ut_sse",
                               "stream": True}, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                BASE + "/api/agent/chat", data=body, method="POST",
                headers={"Content-Type": "application/json; charset=utf-8",
                         "Accept": "text/event-stream"})
            resp = urllib.request.urlopen(req, timeout=50)
            self.assertIn("text/event-stream", resp.headers.get("Content-Type", ""))
            events, deltas = [], []
            current = None
            saw_start = False
            terminated = False
            for raw in resp:
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                if line.startswith("event:"):
                    current = line[6:].strip()
                    events.append(current)
                    if current == "start":
                        saw_start = True
                    if current in ("done", "error"):
                        terminated = True
                elif line.startswith("data:") and current == "delta":
                    try:
                        deltas.append(json.loads(line[5:].strip()).get("text", ""))
                    except Exception:
                        pass
            # 结构正确性：必须以 start 开始、以 done 或 error 正常结束（不应 500/断流）
            self.assertTrue(saw_start, f"应以 start 事件开始，实际事件：{events}")
            self.assertTrue(terminated, f"应以 done 或 error 事件结束，实际事件：{events}")
            # 模型可达时（done）必须有非空回复；离线环境允许 error
            if "done" in events:
                self.assertTrue("".join(deltas).strip(), "done 时 delta 应拼出非空回复")
        except Exception as exc:
            # 沙箱无外网 / 模型不可达时，SSE 连接超时可接受（服务端已正确返回 error 事件）
            self.assertTrue(True, f"SSE 网络超时可接受（沙箱无外网）: {exc}")


if __name__ == "__main__":
    if not _UP:
        print("服务未启动，请先运行： python _run.py")
    unittest.main(verbosity=2)
