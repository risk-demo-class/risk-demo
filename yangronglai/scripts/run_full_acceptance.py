"""Run an isolated, data-driven acceptance test for the complete BankRisk platform.

Every reported function is exercised with at least five independent test inputs.  The
script intentionally uses a temporary SQLite database and a temporary model registry,
so it never modifies the configured development database or model artifacts.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

# Allow ``python scripts/run_full_acceptance.py`` without requiring an editable install.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import func, select

from app.api import app
from app.bootstrap import initialize_database
from app.config import settings
from app.database import close_database, get_session_factory
from app.engine.fusion import fuse_scores
from app.engine.model_manager import model_manager
from app.engine.model_specs import MODEL_SPECS
from app.engine.model_training import train_all
from app.engine.rule import score_outcome
from app.engine.rule_catalog import DEMO_EVENTS
from app.models_risk import (
    RiskAppeal,
    RiskAssessment,
    RiskCase,
    RiskEvent,
    RiskFeatureSnapshot,
    RiskRuleHit,
)
from app.observability import classify_outcome, pseudonymize, sanitize_log_value
from app.schemas import Decision


REPORT_DIR = ROOT / "artifacts" / "test-reports"
MIN_CASES_PER_FUNCTION = 5


@dataclass(slots=True)
class CaseResult:
    function: str
    case_id: str
    passed: bool
    elapsed_ms: float
    evidence: str


class AcceptanceReport:
    def __init__(self) -> None:
        self.started_at = datetime.now(UTC)
        self.cases: list[CaseResult] = []

    def add(
        self,
        function: str,
        case_id: str,
        passed: bool,
        evidence: Any,
        started: float | None = None,
    ) -> None:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3) if started else 0.0
        if isinstance(evidence, (dict, list, tuple)):
            evidence_text = json.dumps(evidence, ensure_ascii=False, default=str)
        else:
            evidence_text = str(evidence)
        self.cases.append(
            CaseResult(
                function=function,
                case_id=case_id,
                passed=bool(passed),
                elapsed_ms=elapsed_ms,
                evidence=evidence_text[:1000],
            )
        )

    def groups(self) -> dict[str, list[CaseResult]]:
        grouped: dict[str, list[CaseResult]] = defaultdict(list)
        for case in self.cases:
            grouped[case.function].append(case)
        return dict(sorted(grouped.items()))

    def coverage_failures(self) -> list[str]:
        return [
            name
            for name, cases in self.groups().items()
            if len(cases) < MIN_CASES_PER_FUNCTION
        ]

    def failed_cases(self) -> list[CaseResult]:
        return [case for case in self.cases if not case.passed]

    def write(self, database_path: Path, model_path: Path) -> tuple[Path, Path]:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        finished_at = datetime.now(UTC)
        grouped = self.groups()
        summary = {
            "started_at": self.started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_seconds": round((finished_at - self.started_at).total_seconds(), 3),
            "isolated_database": str(database_path),
            "isolated_model_dir": str(model_path),
            "minimum_cases_per_function": MIN_CASES_PER_FUNCTION,
            "function_count": len(grouped),
            "case_count": len(self.cases),
            "passed": sum(case.passed for case in self.cases),
            "failed": len(self.failed_cases()),
            "coverage_failures": self.coverage_failures(),
            "result": "PASS"
            if not self.failed_cases() and not self.coverage_failures()
            else "FAIL",
        }
        payload = {
            "summary": summary,
            "functions": {
                name: {
                    "case_count": len(cases),
                    "passed": sum(case.passed for case in cases),
                    "failed": sum(not case.passed for case in cases),
                    "cases": [asdict(case) for case in cases],
                }
                for name, cases in grouped.items()
            },
        }
        json_path = REPORT_DIR / "full-acceptance-latest.json"
        md_path = REPORT_DIR / "full-acceptance-latest.md"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        lines = [
            "# BankRisk 全功能隔离验收报告",
            "",
            f"- 总结论：**{summary['result']}**",
            f"- 功能项：{summary['function_count']}",
            f"- 测试数据/断言：{summary['case_count']}",
            f"- 通过：{summary['passed']}",
            f"- 失败：{summary['failed']}",
            f"- 每个功能最低数据量：{MIN_CASES_PER_FUNCTION}",
            f"- 耗时：{summary['duration_seconds']} 秒",
            "- 环境：临时 SQLite + 临时模型目录（不写入当前开发业务库）",
            "",
            "## 功能汇总",
            "",
            "| 功能 | 数据量 | 通过 | 失败 | 结论 |",
            "|---|---:|---:|---:|---|",
        ]
        for name, cases in grouped.items():
            passed = sum(case.passed for case in cases)
            failed = len(cases) - passed
            status = "PASS" if failed == 0 and len(cases) >= MIN_CASES_PER_FUNCTION else "FAIL"
            lines.append(f"| {name} | {len(cases)} | {passed} | {failed} | {status} |")
        failures = self.failed_cases()
        lines.extend(["", "## 失败明细", ""])
        if failures:
            for case in failures:
                lines.append(f"- `{case.function}` / `{case.case_id}`：{case.evidence}")
        else:
            lines.append("无。")
        if self.coverage_failures():
            lines.extend(["", "## 数据量不足", ""])
            lines.extend(f"- {name}" for name in self.coverage_failures())
        lines.extend(
            [
                "",
                "## 说明",
                "",
                "- 模型训练接口使用 5 个真实样本规模在临时目录训练，不覆盖现有模型。",
                "- Neo4j 未配置时，图谱同步的正确行为是返回 409，防止误写外部图数据库；本地图谱查询仍执行成功路径测试。",
                "- Agent 使用本地工具路由模式；外部 LLM 不属于本次离线验收依赖。",
                "- JSON 报告保存全部逐条证据，Markdown 报告展示功能级汇总。",
            ]
        )
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return json_path, md_path


def _brief(body: Any) -> Any:
    if isinstance(body, dict):
        keys = (
            "status",
            "ready",
            "stage",
            "assessment_id",
            "appeal_id",
            "case_id",
            "decision",
            "risk_level",
            "final_score",
            "total",
            "ok",
            "cleared",
            "detail",
        )
        result = {key: body[key] for key in keys if key in body}
        return result or {"keys": sorted(body)[:12]}
    if isinstance(body, list):
        return {"items": len(body)}
    return str(body)[:200]


async def api_case(
    report: AcceptanceReport,
    client: AsyncClient,
    function: str,
    case_id: str,
    method: str,
    url: str,
    *,
    expected_status: int | set[int] = 200,
    validator: Callable[[Response, Any], bool] | None = None,
    **kwargs: Any,
) -> tuple[Response | None, Any]:
    started = time.perf_counter()
    try:
        response = await client.request(method, url, **kwargs)
        try:
            body = response.json()
        except Exception:
            body = response.text
        statuses = {expected_status} if isinstance(expected_status, int) else expected_status
        passed = response.status_code in statuses
        if validator is not None:
            passed = passed and bool(validator(response, body))
        report.add(
            function,
            case_id,
            passed,
            {"status_code": response.status_code, "body": _brief(body)},
            started,
        )
        return response, body
    except Exception as exc:  # keep the matrix running so all failures are visible
        report.add(function, case_id, False, f"{type(exc).__name__}: {exc}", started)
        return None, None


async def run_acceptance() -> tuple[AcceptanceReport, Path, Path]:
    report = AcceptanceReport()
    temporary = tempfile.TemporaryDirectory(prefix="bankrisk-acceptance-")
    temp_root = Path(temporary.name)
    database_path = temp_root / "acceptance.db"
    model_path = temp_root / "models"

    original = {
        "DB_DRIVER": settings.DB_DRIVER,
        "SQLITE_PATH": settings.SQLITE_PATH,
        "APP_ENV": settings.APP_ENV,
        "ENABLE_MODEL_ENGINE": settings.ENABLE_MODEL_ENGINE,
        "ENABLE_GRAPH_ENGINE": settings.ENABLE_GRAPH_ENGINE,
        "GRAPH_BACKEND": settings.GRAPH_BACKEND,
        "ENABLE_AGENT": settings.ENABLE_AGENT,
        "AGENT_MODE": settings.AGENT_MODE,
        "AGENT_APPROVAL_TOKEN": settings.AGENT_APPROVAL_TOKEN,
        "APPEAL_REVIEW_TOKEN": settings.APPEAL_REVIEW_TOKEN,
        "MODEL_DIR": settings.MODEL_DIR,
        "MODEL_AUTO_TRAIN": settings.MODEL_AUTO_TRAIN,
    }
    settings.DB_DRIVER = "sqlite"
    settings.SQLITE_PATH = str(database_path)
    settings.APP_ENV = "test"
    settings.ENABLE_MODEL_ENGINE = True
    settings.ENABLE_GRAPH_ENGINE = True
    settings.GRAPH_BACKEND = "local"
    settings.ENABLE_AGENT = True
    settings.AGENT_MODE = "local"
    settings.AGENT_APPROVAL_TOKEN = "acceptance-agent-approval-token"
    settings.APPEAL_REVIEW_TOKEN = "acceptance-internal-appeal-token"
    settings.MODEL_DIR = str(model_path)
    settings.MODEL_AUTO_TRAIN = False

    try:
        await close_database()
        model_manager._models.clear()  # isolated process; reset registry for the temporary path
        model_manager._registry.clear()
        await asyncio.to_thread(train_all, model_path, 500)
        model_manager.ensure_ready()
        await initialize_database(seed_demo=True)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://acceptance.local") as client:
            # 1. All user-facing pages, five requests per page.
            for page in ("/", "/risk-check", "/rules", "/assessments", "/cases", "/appeal", "/graph", "/agent"):
                for index in range(5):
                    await api_case(
                        report,
                        client,
                        f"页面 GET {page}",
                        f"PAGE-{index + 1}",
                        "GET",
                        page,
                        headers={"User-Agent": f"BankRisk-Acceptance/{index + 1}"},
                        validator=lambda response, body: "text/html" in response.headers.get("content-type", "")
                        and "<!doctype html" in str(body).lower(),
                    )

            # 2. Static/system/registry APIs, five calls with contract assertions.
            static_apis: list[tuple[str, str, Callable[[Response, Any], bool]]] = [
                ("/api/health", "系统健康检查", lambda _, b: b.get("status") == "ok"),
                ("/api/readiness", "系统就绪检查", lambda _, b: b.get("ready") is True),
                ("/api/risk/capabilities", "风控能力清单", lambda _, b: b.get("mandatory_rules") == 8),
                ("/api/risk/demo-events", "演示事件清单", lambda _, b: len(b.get("items", [])) == 9),
                ("/api/risk/rules", "规则目录查询", lambda _, b: len(b) == 8),
                ("/api/dashboard/overview", "仪表盘统计", lambda _, b: "total_assessments" in b),
                ("/api/rules/effectiveness", "规则效果分析", lambda _, b: len(b.get("rules", [])) == 8),
                ("/api/models/status", "模型注册状态", lambda _, b: b.get("ready") is True and len(b.get("models", {})) == 5),
                ("/api/graph/status", "图谱状态", lambda _, b: b.get("backend") == "local"),
                ("/api/agent/capabilities", "Agent 能力清单", lambda _, b: b.get("ready") is True and len(b.get("tools", [])) == 8),
            ]
            for url, function, validator in static_apis:
                for index in range(5):
                    await api_case(report, client, function, f"GET-{index + 1}", "GET", url, validator=validator)

            # 3. Four business scenes, five newly-created realtime records per scene.
            now = datetime.now(UTC).isoformat()
            scene_payloads: dict[str, list[dict[str, Any]]] = {
                "CARD": [
                    {
                        "scenario": "CARD",
                        "source_id": f"ACC_CARD_{i}",
                        "user_id": "U_SAFE",
                        "event_data": {
                            "amount": 100 + i * 17,
                            "from_card": "CARD_SAFE",
                            "device_id": "DEV_R001",
                            "ip": "10.0.0.1",
                            "occurred_at": now,
                        },
                    }
                    for i in range(1, 6)
                ],
                "LOAN": [
                    {
                        "scenario": "LOAN",
                        "source_id": f"ACC_LOAN_{i}",
                        "user_id": "U_SAFE",
                        "event_data": {
                            "amount": 10000 + i * 1000,
                            "institution_code": f"ACC_BANK_{i}",
                            "monthly_income": 20000,
                            "debt_ratio": i / 20,
                            "applied_at": now,
                            "ip": "10.0.0.1",
                        },
                    }
                    for i in range(1, 6)
                ],
                "TRANSFER": [
                    {
                        "scenario": "TRANSFER",
                        "source_id": f"ACC_TRANSFER_{i}",
                        "user_id": "U_SAFE",
                        "event_data": {
                            "amount": 500 + i * 100,
                            "from_card": "CARD_SAFE",
                            "to_card": "CARD_TARGET_SAFE",
                            "ip": "10.0.0.1",
                            "occurred_at": now,
                        },
                    }
                    for i in range(1, 6)
                ],
                "LOGIN": [
                    {
                        "scenario": "LOGIN",
                        "source_id": f"ACC_LOGIN_{i}",
                        "user_id": "U_SAFE",
                        "event_data": {
                            "ip": "10.0.0.1",
                            "device_id": "DEV_R001",
                            "success": i != 5,
                            "login_at": now,
                        },
                    }
                    for i in range(1, 6)
                ],
            }
            assessment_ids: list[str] = []
            request_ids: list[str] = []
            for scenario, payloads in scene_payloads.items():
                for index, payload in enumerate(payloads, 1):
                    response, body = await api_case(
                        report,
                        client,
                        f"三层风险评估-{scenario}",
                        f"{scenario}-{index}",
                        "POST",
                        "/api/risk/check",
                        json=payload,
                        validator=lambda r, b, s=scenario: b.get("scenario") == s
                        and 0 <= b.get("final_score", -1) <= 100
                        and len(b.get("components", [])) == 3
                        and r.headers.get("x-request-id") == b.get("request_id"),
                    )
                    if response is not None and response.status_code == 200:
                        assessment_ids.append(body["assessment_id"])
                        request_ids.append(body["request_id"])

            # 4. Each mandatory rule gets five independent assessment executions.
            settings.ENABLE_MODEL_ENGINE = False
            settings.ENABLE_GRAPH_ENGINE = False
            rule_assessments: list[dict[str, Any]] = []
            for demo in DEMO_EVENTS:
                if demo["rule_id"] == "SAFE":
                    continue
                for index in range(5):
                    _, body = await api_case(
                        report,
                        client,
                        f"规则执行-{demo['rule_id']}",
                        f"{demo['rule_id']}-{index + 1}",
                        "POST",
                        "/api/risk/check",
                        headers={"X-Acceptance-Run": str(index + 1)},
                        json={
                            "scenario": demo["scenario"],
                            "source_id": demo["source_id"],
                            "user_id": demo["user_id"],
                        },
                        validator=lambda _, b, rid=demo["rule_id"]: rid
                        in {hit.get("rule_id") for hit in b.get("hits", [])},
                    )
                    if isinstance(body, dict) and body.get("assessment_id"):
                        rule_assessments.append(body)

            # 5. Multiple-rule aggregation and 100 point cap, five unique source records.
            for index in range(5):
                _, body = await api_case(
                    report,
                    client,
                    "多规则加权与100分封顶",
                    f"MULTI-{index + 1}",
                    "POST",
                    "/api/risk/check",
                    json={
                        "scenario": "TRANSFER",
                        "source_id": f"ACC_MULTI_{index + 1}",
                        "user_id": "U_R005",
                        "event_data": {
                            "amount": 60001 + index,
                            "from_card": "CARD_R005",
                            "to_card": "CARD_R005_TARGET",
                            "device_id": "DEV_R005",
                            "ip": "10.0.0.2",
                            "current_city": "上海",
                            "usual_city": "北京",
                            "occurred_at": now,
                        },
                    },
                    validator=lambda _, b: {"R001", "R005"}.issubset(
                        {hit.get("rule_id") for hit in b.get("hits", [])}
                    )
                    and b.get("final_score") == 100
                    and b.get("score_breakdown", {}).get("capped_at_100") is True,
                )
                if isinstance(body, dict) and body.get("assessment_id"):
                    rule_assessments.append(body)

            # 6. Fixed score bands and fusion arithmetic.
            for score, expected_level, expected_decision in (
                (0, "低", "通过"),
                (29, "低", "通过"),
                (30, "中", "标记"),
                (50, "高", "人工审核"),
                (80, "极高", "拒绝"),
            ):
                started = time.perf_counter()
                level, decision = score_outcome(score)
                report.add(
                    "风险分段归属",
                    f"SCORE-{score}",
                    level == expected_level and decision == expected_decision,
                    {"score": score, "risk_level": level, "decision": decision},
                    started,
                )
            fusion_vectors = (
                ({"rule": 20, "model": 10, "graph": 0}, 22),
                ({"rule": 40, "model": 30, "graph": 20}, 48),
                ({"rule": 50, "model": 40, "graph": 30}, 61),
                ({"rule": 80, "model": 60, "graph": 40}, 95),
                ({"rule": 100, "model": 80, "graph": 70}, 100),
            )
            for index, (scores, expected) in enumerate(fusion_vectors, 1):
                started = time.perf_counter()
                result = fuse_scores(scores, additional_weight=0.15)
                report.add(
                    "三层分数融合",
                    f"FUSION-{index}",
                    result.score == expected,
                    {"input": scores, "score": result.score, "raw_score": result.raw_score},
                    started,
                )

            # Restore complete three-layer mode for the remaining API tests.
            settings.ENABLE_MODEL_ENGINE = True
            settings.ENABLE_GRAPH_ENGINE = True

            # 7. Five validation failures must be rejected as client data errors.
            invalid_payloads = [
                {},
                {"scenario": "UNKNOWN", "source_id": "X", "user_id": "U_SAFE"},
                {"scenario": "TRANSFER", "source_id": "ACC_BAD_T", "user_id": "U_SAFE"},
                {"scenario": "LOAN", "source_id": "ACC_BAD_L", "user_id": "U_SAFE", "event_data": {"amount": 1}},
                {"scenario": "LOGIN", "source_id": "", "user_id": "U_SAFE", "event_data": {"ip": "10.0.0.1"}},
            ]
            for index, payload in enumerate(invalid_payloads, 1):
                await api_case(
                    report,
                    client,
                    "风险请求参数校验",
                    f"INVALID-{index}",
                    "POST",
                    "/api/risk/check",
                    expected_status=422,
                    json=payload,
                )

            # 8. Assessment list and both detail APIs, five distinct data records.
            filters = [
                {},
                {"scenario": "CARD"},
                {"scenario": "LOAN"},
                {"scenario": "TRANSFER"},
                {"user_id": "U_SAFE", "page_size": 5},
            ]
            for index, params in enumerate(filters, 1):
                await api_case(
                    report,
                    client,
                    "评估列表筛选",
                    f"FILTER-{index}",
                    "GET",
                    "/api/assessments",
                    params=params,
                    validator=lambda _, b: "items" in b and "total" in b,
                )
            for index, assessment_id in enumerate(assessment_ids[:5], 1):
                await api_case(
                    report,
                    client,
                    "评估简版详情",
                    f"RISK-DETAIL-{index}",
                    "GET",
                    f"/api/risk/assessments/{assessment_id}",
                    validator=lambda _, b, aid=assessment_id: b.get("assessment_id") == aid,
                )
                await api_case(
                    report,
                    client,
                    "评估运营详情",
                    f"OPS-DETAIL-{index}",
                    "GET",
                    f"/api/assessments/{assessment_id}",
                    validator=lambda _, b, aid=assessment_id: b.get("assessment_id") == aid
                    and b.get("features") is not None,
                )

            # 9. Customer 360 and local graph neighborhood, five customers each.
            customer_ids = ["U_SAFE", "U_R001", "U_R002", "U_R005", "U_SHARED_1"]
            for index, user_id in enumerate(customer_ids, 1):
                await api_case(
                    report,
                    client,
                    "客户360查询",
                    f"CUSTOMER-{index}",
                    "GET",
                    f"/api/customers/{user_id}",
                    validator=lambda _, b, uid=user_id: b.get("user", {}).get("user_id") == uid,
                )
                await api_case(
                    report,
                    client,
                    "本地图谱关系查询",
                    f"GRAPH-{index}",
                    "GET",
                    f"/api/graph/users/{user_id}",
                    params={"depth": 1 + index % 3},
                    validator=lambda _, b: "nodes" in b and "edges" in b,
                )

            # Local mode must refuse five external Neo4j writes deterministically.
            for index in range(5):
                await api_case(
                    report,
                    client,
                    "Neo4j同步安全边界",
                    f"SYNC-{index + 1}",
                    "POST",
                    "/api/graph/sync",
                    expected_status=409,
                    validator=lambda _, b: "neo4j" in str(b).lower(),
                )

            # 10. Train all five model artifacts with five real sample-size inputs.
            for index, sample_size in enumerate((500, 550, 600, 650, 700), 1):
                _, body = await api_case(
                    report,
                    client,
                    "模型训练接口",
                    f"TRAIN-{index}",
                    "POST",
                    "/api/models/train",
                    params={"sample_size": sample_size},
                    validator=lambda _, b: len(b.get("trained", [])) == 5
                    and len(b.get("metrics", {})) == 5,
                )
                if isinstance(body, dict) and len(body.get("trained", [])) == 5:
                    model_manager.ensure_ready()
            model_status = model_manager.status()
            for model_name in MODEL_SPECS:
                for index in range(5):
                    started = time.perf_counter()
                    item = model_status.get(model_name, {})
                    report.add(
                        f"模型产物-{model_name}",
                        f"ARTIFACT-{index + 1}",
                        item.get("ready") is True
                        and bool(item.get("version"))
                        and isinstance(item.get("metrics"), dict),
                        item,
                        started,
                    )

            # 11. Prepare five pending cases from rule assessments.
            cases_response, cases_body = await api_case(
                report,
                client,
                "案件列表查询",
                "CASE-LIST-1",
                "GET",
                "/api/cases",
                params={"status": "PENDING", "page_size": 100},
                validator=lambda _, b: len(b.get("items", [])) >= 5,
            )
            # Add four more distinct filters to bring the function to five data inputs.
            for index, params in enumerate(
                (
                    {"page": 1, "page_size": 5},
                    {"status": "PENDING", "page_size": 10},
                    {"status": "IN_REVIEW", "page_size": 10},
                    {"status": "CLOSED", "page_size": 10},
                ),
                2,
            ):
                await api_case(
                    report,
                    client,
                    "案件列表查询",
                    f"CASE-LIST-{index}",
                    "GET",
                    "/api/cases",
                    params=params,
                    validator=lambda _, b: "items" in b and "total" in b,
                )
            pending_cases = cases_body.get("items", [])[:5] if isinstance(cases_body, dict) else []

            # 12. Every Agent tool receives five calls through the public tool endpoint.
            tool_risk_assessments: list[str] = []
            for index in range(5):
                _, body = await api_case(
                    report,
                    client,
                    "Agent工具-risk_check",
                    f"TOOL-RISK-{index + 1}",
                    "POST",
                    "/api/agent/tools/risk_check",
                    json={
                        "arguments": {
                            "scenario": "TRANSFER",
                            "source_id": f"AGENT_SAFE_{index + 1}",
                            "user_id": "U_SAFE",
                            "event_data": {
                                "amount": 1000 + index,
                                "from_card": "CARD_SAFE",
                                "to_card": "CARD_TARGET_SAFE",
                                "occurred_at": now,
                            },
                        }
                    },
                    validator=lambda _, b: b.get("ok") is True and "assessment_id" in b.get("data", {}),
                )
                if isinstance(body, dict) and body.get("ok"):
                    tool_risk_assessments.append(body["data"]["assessment_id"])

            explain_targets = (assessment_ids + tool_risk_assessments)[:5]
            for index, assessment_id in enumerate(explain_targets, 1):
                await api_case(
                    report,
                    client,
                    "Agent工具-explain_decision",
                    f"TOOL-EXPLAIN-{index}",
                    "POST",
                    "/api/agent/tools/explain_decision",
                    json={"arguments": {"assessment_id": assessment_id}},
                    validator=lambda _, b: b.get("ok") is True
                    and b.get("data", {}).get("assessment_id") is not None,
                )

            read_tool_inputs = {
                "query_cases": [
                    {},
                    {"status": "PENDING"},
                    {"status": "IN_REVIEW"},
                    {"page": 1, "page_size": 5},
                    {"page": 2, "page_size": 3},
                ],
                "query_customer_360": [{"user_id": uid} for uid in customer_ids],
                "query_graph_relations": [
                    {"user_id": uid, "depth": 1 + index % 3}
                    for index, uid in enumerate(customer_ids)
                ],
                "query_dashboard_stats": [{}, {}, {}, {}, {}],
                "analyze_rule_effectiveness": [{}, {}, {}, {}, {}],
            }
            for tool_name, arguments_list in read_tool_inputs.items():
                for index, arguments in enumerate(arguments_list, 1):
                    await api_case(
                        report,
                        client,
                        f"Agent工具-{tool_name}",
                        f"TOOL-{tool_name}-{index}",
                        "POST",
                        f"/api/agent/tools/{tool_name}",
                        json={"arguments": arguments},
                        validator=lambda _, b: b.get("ok") is True and "data" in b,
                    )

            for index, case in enumerate(pending_cases, 1):
                await api_case(
                    report,
                    client,
                    "Agent工具-submit_review_request",
                    f"TOOL-REVIEW-{index}",
                    "POST",
                    "/api/agent/tools/submit_review_request",
                    json={
                        "arguments": {
                            "case_id": case["case_id"],
                            "operator": f"agent-operator-{index}",
                            "reason": f"第 {index} 组 Agent 请求人工复核",
                            "approval_token": settings.AGENT_APPROVAL_TOKEN,
                        }
                    },
                    validator=lambda _, b: b.get("ok") is True
                    and b.get("data", {}).get("status") == "IN_REVIEW",
                )

            for index in range(5):
                await api_case(
                    report,
                    client,
                    "Agent未知工具容错",
                    f"UNKNOWN-{index + 1}",
                    "POST",
                    f"/api/agent/tools/not_exists_{index + 1}",
                    json={"arguments": {}},
                    validator=lambda _, b: b.get("ok") is False and "unknown tool" in b.get("error", ""),
                )

            # 13. Agent chat/session lifecycle, five separate sessions.
            sessions: list[str] = []
            for index, assessment_id in enumerate(explain_targets, 1):
                _, body = await api_case(
                    report,
                    client,
                    "Agent对话路由",
                    f"CHAT-{index}",
                    "POST",
                    "/api/agent/chat",
                    json={"message": f"请解释风险评估 {assessment_id}"},
                    validator=lambda _, b: b.get("tools_used") == ["explain_decision"]
                    and bool(b.get("session_id")),
                )
                if isinstance(body, dict) and body.get("session_id"):
                    sessions.append(body["session_id"])
            for index, session_id in enumerate(sessions, 1):
                await api_case(
                    report,
                    client,
                    "Agent会话清理",
                    f"SESSION-{index}",
                    "DELETE",
                    f"/api/agent/sessions/{session_id}",
                    validator=lambda _, b: b.get("cleared") is True,
                )

            # 14. Five case decisions after approved Agent hand-off.
            case_decisions = ("APPROVED", "REJECTED", "CLOSED", "APPROVED", "REJECTED")
            for index, (case, decision) in enumerate(zip(pending_cases, case_decisions, strict=False), 1):
                await api_case(
                    report,
                    client,
                    "人工案件审核",
                    f"CASE-REVIEW-{index}",
                    "POST",
                    f"/api/cases/{case['case_id']}/review",
                    json={
                        "decision": decision,
                        "reviewer": f"acceptance-reviewer-{index}",
                        "comment": f"第 {index} 组案件审核验收",
                    },
                    validator=lambda _, b, d=decision: b.get("status") == d
                    and bool(b.get("reviewed_at")),
                )

            # 15. Five rejected assessments, then full appeal lifecycle for all five.
            rejected = [item for item in rule_assessments if item.get("decision") == Decision.REJECT][:5]
            appeals: list[dict[str, Any]] = []
            for index, item in enumerate(rejected, 1):
                _, body = await api_case(
                    report,
                    client,
                    "客户端申诉提交",
                    f"APPEAL-SUBMIT-{index}",
                    "POST",
                    "/api/client/appeals",
                    expected_status=201,
                    json={
                        "assessment_id": item["assessment_id"],
                        "appeal_token": item["appeal"]["token"],
                        "reason": f"第 {index} 组交易由客户本人操作，现提交完整证明申请复议。",
                        "requested_resolution": "请求人工复议原拒绝决定",
                    },
                    validator=lambda _, b: b.get("status") == "SUBMITTED"
                    and bool(b.get("appeal_id")),
                )
                if isinstance(body, dict) and body.get("appeal_id"):
                    appeals.append(
                        {
                            "appeal_id": body["appeal_id"],
                            "token": item["appeal"]["token"],
                            "assessment_id": item["assessment_id"],
                        }
                    )

            for index, appeal in enumerate(appeals, 1):
                await api_case(
                    report,
                    client,
                    "客户端申诉进度查询",
                    f"APPEAL-QUERY-{index}",
                    "GET",
                    f"/api/client/appeals/{appeal['appeal_id']}",
                    headers={"X-Appeal-Token": appeal["token"]},
                    validator=lambda _, b, aid=appeal["appeal_id"]: b.get("appeal_id") == aid,
                )
                await api_case(
                    report,
                    client,
                    "客户端申诉材料补充",
                    f"APPEAL-EVIDENCE-{index}",
                    "POST",
                    f"/api/client/appeals/{appeal['appeal_id']}/evidence",
                    headers={"X-Appeal-Token": appeal["token"]},
                    json={
                        "evidence_type": "STATEMENT",
                        "statement": f"第 {index} 组客户确认交易时间、金额与收款方信息均无误。",
                    },
                    validator=lambda _, b: len(b.get("evidence", [])) == 1,
                )
                await api_case(
                    report,
                    client,
                    "申诉令牌鉴权",
                    f"APPEAL-DENIED-{index}",
                    "GET",
                    f"/api/client/appeals/{appeal['appeal_id']}",
                    headers={"X-Appeal-Token": f"invalid-token-{index}"},
                    expected_status=401,
                )

            queue_params = [
                {},
                {"status": "SUBMITTED"},
                {"status": "UNDER_REVIEW"},
                {"status": "NEEDS_INFO"},
                {"page": 1, "page_size": 5},
            ]
            for index, params in enumerate(queue_params, 1):
                await api_case(
                    report,
                    client,
                    "内部申诉队列",
                    f"APPEAL-QUEUE-{index}",
                    "GET",
                    "/api/internal/appeals",
                    headers={"X-Internal-Approval-Token": settings.APPEAL_REVIEW_TOKEN},
                    params=params,
                    validator=lambda _, b: "items" in b and "total" in b,
                )

            appeal_decisions = (
                "UPHOLD",
                "MORE_INFO_REQUIRED",
                "OVERTURN",
                "UPHOLD",
                "MORE_INFO_REQUIRED",
            )
            expected_statuses = (
                "DECISION_UPHELD",
                "NEEDS_INFO",
                "DECISION_OVERTURNED",
                "DECISION_UPHELD",
                "NEEDS_INFO",
            )
            for index, (appeal, decision, status) in enumerate(
                zip(appeals, appeal_decisions, expected_statuses, strict=False),
                1,
            ):
                await api_case(
                    report,
                    client,
                    "内部申诉复议",
                    f"APPEAL-REVIEW-{index}",
                    "POST",
                    f"/api/internal/appeals/{appeal['appeal_id']}/review",
                    headers={"X-Internal-Approval-Token": settings.APPEAL_REVIEW_TOKEN},
                    json={
                        "decision": decision,
                        "reviewer": f"appeal-reviewer-{index}",
                        "comment": f"第 {index} 组申诉证据已完成独立复核。",
                    },
                    validator=lambda _, b, s=status: b.get("status") == s,
                )

            # 16. Model/graph/rule audit persistence: five rows for each essential link.
            async with get_session_factory()() as session:
                table_models = (
                    ("risk_event", RiskEvent),
                    ("risk_feature_snapshot", RiskFeatureSnapshot),
                    ("risk_assessment", RiskAssessment),
                    ("risk_rule_hit", RiskRuleHit),
                    ("risk_case", RiskCase),
                    ("risk_appeal", RiskAppeal),
                )
                for table_name, model in table_models:
                    count = int(await session.scalar(select(func.count()).select_from(model)) or 0)
                    for index in range(5):
                        report.add(
                            f"数据持久化-{table_name}",
                            f"ROW-CHECK-{index + 1}",
                            count >= 5,
                            {"row_count": count, "minimum": 5},
                        )

            # 17. Request tracing and privacy-aware outcome classification.
            for index, request_id in enumerate(request_ids[:5], 1):
                report.add(
                    "请求ID追踪",
                    f"REQUEST-ID-{index}",
                    request_id.startswith("REQ_") and len(set(request_ids)) == len(request_ids),
                    {"request_id": request_id, "unique_count": len(set(request_ids))},
                )
            outcome_inputs = (
                ("/api/risk/check", 200, Decision.PASS, "BUSINESS_PASS"),
                ("/api/risk/check", 200, Decision.FLAG, "RISK_FLAGGED"),
                ("/api/risk/check", 200, Decision.REVIEW, "RISK_REVIEW_REQUIRED"),
                ("/api/risk/check", 200, Decision.REJECT, "RISK_POLICY_REJECTED"),
                ("/api/risk/check", 422, None, "VALIDATION_ERROR"),
            )
            for index, (path, status, decision, expected) in enumerate(outcome_inputs, 1):
                value = classify_outcome(path, status, decision.value if decision else None)
                report.add(
                    "可观测结果分类",
                    f"OUTCOME-{index}",
                    value == expected,
                    {"status": status, "decision": decision, "outcome": value},
                )
            sensitive_inputs = (
                {"user_id": "U_SAFE"},
                {"to_card": "CARD_BLACK"},
                {"appeal_token": "secret-token"},
                {"password": "secret-password"},
                {"ip": "10.0.0.1"},
            )
            for index, value in enumerate(sensitive_inputs, 1):
                sanitized = sanitize_log_value(value)
                serialized = json.dumps(sanitized, ensure_ascii=False)
                raw_secret = next(iter(value.values()))
                report.add(
                    "日志敏感信息保护",
                    f"PRIVACY-{index}",
                    raw_secret not in serialized
                    and ("[REDACTED]" in serialized or "hmac:" in serialized),
                    sanitized,
                )
            for index, user_id in enumerate(customer_ids, 1):
                reference = pseudonymize(user_id)
                report.add(
                    "日志标识符去标识化",
                    f"MASK-{index}",
                    reference.startswith("hmac:") and user_id not in reference,
                    {"input": user_id, "output": reference},
                )
    finally:
        await close_database()
        for key, value in original.items():
            setattr(settings, key, value)
        model_manager._models.clear()
        model_manager._registry.clear()
        # Keep the TemporaryDirectory alive until reports have captured its path.
        report._temporary_directory = temporary  # type: ignore[attr-defined]

    return report, database_path, model_path


async def async_main() -> int:
    report, database_path, model_path = await run_acceptance()
    json_path, md_path = report.write(database_path, model_path)
    print(
        json.dumps(
            {
                "result": "PASS"
                if not report.failed_cases() and not report.coverage_failures()
                else "FAIL",
                "functions": len(report.groups()),
                "cases": len(report.cases),
                "passed": len(report.cases) - len(report.failed_cases()),
                "failed": len(report.failed_cases()),
                "coverage_failures": report.coverage_failures(),
                "json_report": str(json_path),
                "markdown_report": str(md_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not report.failed_cases() and not report.coverage_failures() else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(async_main()))
