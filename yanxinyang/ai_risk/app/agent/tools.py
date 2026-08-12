# -*- coding: utf-8 -*-
"""L5 AI 层 · tools.py —— 8 个 @tool 工具

对应教学宝典《第 11 章 11.2》：

| # | 工具 | 作用 |
|---|------|------|
| 1 | `risk_check`                 | 触发一次风控检查 |
| 2 | `query_cases`                | 查案件（带状态过滤）|
| 3 | `query_user_profile`         | 查用户风险画像 |
| 4 | `manage_blacklist`           | 黑名单增删查（4 子动作）|
| 5 | `query_dashboard_stats`      | 仪表盘统计 |
| 6 | `analyze_risk_trend`         | 风险趋势分析（按天）|
| 7 | `analyze_rule_effectiveness` | 规则命中率分析 |
| 8 | `query_business_data`        | 业务数据查询（订单/售后/地址）|

**关键设计（宝典 11.2 原文）**：
    内部 `_impl` 函数做实际工作，`@tool` 函数做薄包装 + 类型注解（让 LLM 知道怎么调）。

`@tool` 装饰器：LangChain 装上就用 LangChain 的；没有 LangChain 时用本文件内的
等价实现（保留 `.name` / `.description` / `.args_schema` / `.invoke()`），
所以**同一份工具代码在有/无 LangChain 环境下都能跑**。
"""
from __future__ import annotations

import inspect
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from app.database import Session, pool
from app.engine import ml_model
from app.framework import HTTPError
from app.models import BLACKLIST_TYPES, EVENT_TYPES
from app.service import case as case_service
from app.service import event as event_service
from app.service.action_log import record_action

logger = logging.getLogger("ai_risk.agent.tools")

# ====================================================================== @tool 装饰器
try:                                                  # 真实 LangChain 环境
    from langchain_core.tools import tool as _lc_tool  # type: ignore
    _HAS_LANGCHAIN = True
except Exception:                                     # noqa: BLE001
    _lc_tool = None                                   # type: ignore[assignment]
    _HAS_LANGCHAIN = False


class ToolSpec:
    """零依赖版 @tool —— 与 LangChain BaseTool 的关键属性保持同名。"""

    def __init__(self, func: Callable[..., str]) -> None:
        self.func = func
        self.name = func.__name__
        self.description = (func.__doc__ or "").strip()
        sig = inspect.signature(func)
        self.args_schema: Dict[str, Dict[str, Any]] = {}
        for pname, param in sig.parameters.items():
            annotation = param.annotation
            type_name = getattr(annotation, "__name__", str(annotation))
            self.args_schema[pname] = {
                "type": {"str": "string", "int": "integer", "float": "number",
                         "bool": "boolean"}.get(type_name, "string"),
                "required": param.default is inspect.Parameter.empty,
                "default": None if param.default is inspect.Parameter.empty else param.default,
            }

    # LangChain 同名调用入口
    def invoke(self, args: Optional[Dict[str, Any]] = None) -> str:
        return self.func(**(args or {}))

    def run(self, args: Optional[Dict[str, Any]] = None) -> str:
        return self.invoke(args)

    def __call__(self, *a: Any, **kw: Any) -> str:
        return self.func(*a, **kw)

    def spec(self) -> Dict[str, Any]:
        """给 /api/agent/tools 与前端「工具箱」页渲染。"""
        return {"name": self.name, "description": self.description,
                "args": self.args_schema, "backend": "langchain" if _HAS_LANGCHAIN else "builtin"}


def tool(func: Callable[..., str]) -> Any:
    """双模 @tool：有 LangChain 用官方的（同时保留 spec），否则用内置 ToolSpec。"""
    spec = ToolSpec(func)
    if _HAS_LANGCHAIN and _lc_tool is not None:
        wrapped = _lc_tool(func)                       # type: ignore[misc]
        try:
            wrapped.__dict__["_ai_risk_spec"] = spec.spec()
        except Exception:                              # noqa: BLE001
            pass
        return wrapped
    return spec


def _db() -> Session:
    return Session(pool.acquire())


def _ok(payload: Any) -> str:
    """工具统一返回 JSON 字符串（LLM 侧最好解析）。"""
    return json.dumps(payload, ensure_ascii=False, default=str)


def _err(message: str) -> str:
    return json.dumps({"success": False, "error": message}, ensure_ascii=False)


# ====================================================================== 1 risk_check
def _risk_check_impl(event_type: str, user_id: str, source_id: str,
                     amount: float = 0.0) -> Dict[str, Any]:
    if event_type not in EVENT_TYPES:
        raise HTTPError(400, f"event_type 必须是 {list(EVENT_TYPES)} 之一")
    payload: Dict[str, Any] = {"event_type": event_type, "user_id": user_id,
                               "source_id": source_id}
    if amount:
        payload["amount"] = amount
    db = _db()
    try:
        result = event_service.process_event(db, payload, operator="ai_agent")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    # 只回传 LLM 需要的字段，省 token
    return {
        "assessment_id": result["assessment_id"], "case_id": result["case_id"],
        "rule_score": result["rule_score"], "ml_score": result["ml_score"],
        "final_score": result["final_score"], "risk_level": result["risk_level"],
        "decision": result["decision"], "is_veto": result["is_veto"],
        "hit_rules": [{"rule_id": h.get("rule_id"), "rule_name": h.get("rule_name"),
                       "risk_level": h.get("risk_level"), "risk_score": h.get("risk_score")}
                      for h in result["hit_rules"]],
        "reason": result["reason"], "cost_ms": result["cost_ms"],
    }


@tool
def risk_check(event_type: str, user_id: str, source_id: str, amount: float = 0.0) -> str:
    """对指定用户的一笔学习行为单据触发风控检查（7 步流水线），返回评分与决策。

    参数：
        event_type: 事件类型，必须是 考试 / 作业 / 选课 / 成绩申诉 之一
        user_id: 用户 ID，例如 1001（库中为纯数字）
        source_id: 来源单号。考试/作业传学习记录号（如 ORD10010001）；选课传选课记录号；成绩申诉传申诉记录 ID
        amount: 投入金额（可选），传了会与学习记录金额做一致性校验
    """
    try:
        return _ok({"success": True, "data": _risk_check_impl(event_type, user_id, source_id, amount)})
    except HTTPError as exc:
        return _err(f"{exc.status_code} {exc.detail}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("risk_check 工具失败")
        return _err(str(exc))


# ====================================================================== 2 query_cases
def _query_cases_impl(case_status: str = "", user_id: str = "", limit: int = 10) -> Dict[str, Any]:
    db = _db()
    try:
        data = case_service.list_cases(db, active_only=not case_status, case_status=case_status,
                                       user_id=user_id, limit=max(1, min(limit, 50)))
        stats = case_service.case_stats(db)
    finally:
        db.close()
    items = [{k: c.get(k) for k in ("case_id", "user_id", "event_type", "case_status",
                                    "risk_level", "final_score", "reviewer", "create_time")}
             for c in data["items"]]
    return {"total": data["total"], "items": items, "status_summary": stats["summary"],
            "state_machine": case_service.state_machine_doc()["transitions"]}


@tool
def query_cases(case_status: str = "", user_id: str = "", limit: int = 10) -> str:
    """查询风控案件列表，可按状态与用户过滤。不传状态时只返回活跃案件（待审核+审核中）。

    参数：
        case_status: 案件状态，可选 待审核 / 审核中 / 已通过 / 已拒绝 / 已关闭
        user_id: 用户 ID（可选）
        limit: 返回条数，默认 10，最大 50
    """
    try:
        return _ok({"success": True, "data": _query_cases_impl(case_status, user_id, limit)})
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


# ====================================================================== 3 query_user_profile
def _query_user_profile_impl(user_id: str) -> Dict[str, Any]:
    db = _db()
    try:
        user = db.fetch_one("SELECT user_id, user_name, phone, user_level, register_time "
                            "FROM user_info WHERE user_id = ?", [user_id])
        if not user:
            raise HTTPError(404, f"用户不存在: {user_id}")
        profile = db.fetch_one("SELECT * FROM risk_user_profile WHERE user_id = ?", [user_id])
        recent = db.fetch_all(
            "SELECT event_type, source_id, final_score, risk_level, decision, create_time "
            "FROM risk_assessment WHERE user_id = ? ORDER BY create_time DESC LIMIT 5", [user_id])
        cases = db.scalar("SELECT COUNT(*) FROM risk_case WHERE user_id = ? AND deleted_at IS NULL",
                          [user_id])
        black = db.fetch_all(
            "SELECT blacklist_type, blacklist_value, risk_level, reason FROM risk_blacklist "
            "WHERE deleted_at IS NULL AND is_enabled = 1 AND "
            "((blacklist_type = '用户' AND blacklist_value = ?) OR "
            " (blacklist_type = '手机号' AND blacklist_value = ?))",
            [user_id, user.get("phone") or ""])
    finally:
        db.close()
    return {"user": user, "profile": profile or {"note": "该用户暂无风控事件"},
            "recent_assessments": recent, "case_count": cases, "blacklist_hits": black}


@tool
def query_user_profile(user_id: str) -> str:
    """查询指定用户的风险画像：累计事件数、四种决策计数、历史最高/平均分、画像等级、撞黑情况。

    参数：
        user_id: 用户 ID，例如 1001（库中为纯数字；也兼容 U0001 写法）
    """
    try:
        return _ok({"success": True, "data": _query_user_profile_impl(user_id)})
    except HTTPError as exc:
        return _err(f"{exc.status_code} {exc.detail}")
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


# ====================================================================== 4 manage_blacklist
def _manage_blacklist_impl(action: str, blacklist_type: str = "", value: str = "",
                           reason: str = "", operator: str = "ai_agent") -> Dict[str, Any]:
    """4 个子动作：list / add / remove / check（宝典 11.2 工具 4）。"""
    action = (action or "list").strip().lower()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db = _db()
    try:
        if action == "list":
            params: List[Any] = []
            clause = "deleted_at IS NULL AND is_enabled = 1"
            if blacklist_type:
                clause += " AND blacklist_type = ?"
                params.append(blacklist_type)
            rows = db.fetch_all(
                f"SELECT blacklist_id, blacklist_type, blacklist_value, risk_level, reason, "
                f"hit_count, expire_time, create_time FROM risk_blacklist WHERE {clause} "
                f"ORDER BY create_time DESC LIMIT 30", params)
            return {"action": "list", "total": len(rows), "items": rows}

        if action == "check":
            if not value:
                raise HTTPError(400, "check 动作需要 value")
            rows = db.fetch_all(
                "SELECT blacklist_type, blacklist_value, risk_level, reason FROM risk_blacklist "
                "WHERE deleted_at IS NULL AND is_enabled = 1 AND blacklist_value = ?", [value])
            return {"action": "check", "value": value, "hit": bool(rows), "items": rows}

        if action == "add":
            if blacklist_type not in BLACKLIST_TYPES:
                raise HTTPError(400, f"blacklist_type 必须是 {list(BLACKLIST_TYPES)} 之一")
            if not value:
                raise HTTPError(400, "add 动作需要 value")
            exists = db.fetch_one(
                "SELECT blacklist_id FROM risk_blacklist WHERE blacklist_type = ? "
                "AND blacklist_value = ? AND deleted_at IS NULL AND is_enabled = 1",
                [blacklist_type, value])
            if exists:
                return {"action": "add", "created": False,
                        "message": f"{blacklist_type} {value} 已在黑名单中"}
            new_id = db.insert("risk_blacklist", {
                "blacklist_type": blacklist_type, "blacklist_value": value,
                "risk_level": "高", "reason": reason or "AI 助手建议拉黑",
                "source": "系统", "operator": operator, "hit_count": 0,
                "is_enabled": 1, "create_time": now})
            record_action(db, operator=operator, action_type="新增黑名单", target_type="黑名单",
                          target_id=str(new_id),
                          after_value={"blacklist_type": blacklist_type, "value": value},
                          remark=reason or "AI 助手操作")
            db.commit()
            return {"action": "add", "created": True, "blacklist_id": new_id}

        if action == "remove":
            if not value:
                raise HTTPError(400, "remove 动作需要 value")
            rows = db.fetch_all(
                "SELECT * FROM risk_blacklist WHERE blacklist_value = ? AND deleted_at IS NULL"
                + (" AND blacklist_type = ?" if blacklist_type else ""),
                [value] + ([blacklist_type] if blacklist_type else []))
            if not rows:
                return {"action": "remove", "removed": 0, "message": f"{value} 不在黑名单中"}
            for row in rows:
                db.update("risk_blacklist", {"deleted_at": now, "is_enabled": 0},
                          "blacklist_id = ?", [row["blacklist_id"]])
                record_action(db, operator=operator, action_type="解除黑名单",
                              target_type="黑名单", target_id=str(row["blacklist_id"]),
                              before_value=row, remark=reason or "AI 助手操作")
            db.commit()
            return {"action": "remove", "removed": len(rows)}

        raise HTTPError(400, f"未知动作: {action}，可选 list / add / remove / check")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@tool
def manage_blacklist(action: str, blacklist_type: str = "", value: str = "",
                     reason: str = "") -> str:
    """管理黑名单，支持 4 个子动作。

    参数：
        action: list（列表）/ add（新增）/ remove（解除）/ check（检测是否命中）
        blacklist_type: 用户 / 手机号 / 地址 / 设备 / IP（add 必填，list、remove 可选）
        value: 黑名单值（add / remove / check 必填）
        reason: 拉黑或解除原因
    """
    try:
        return _ok({"success": True,
                    "data": _manage_blacklist_impl(action, blacklist_type, value, reason)})
    except HTTPError as exc:
        return _err(f"{exc.status_code} {exc.detail}")
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


# ====================================================================== 5 query_dashboard_stats
def _query_dashboard_stats_impl() -> Dict[str, Any]:
    db = _db()
    try:
        total_assessments = db.scalar("SELECT COUNT(*) FROM risk_assessment")
        decisions = {r["decision"]: r["cnt"] for r in db.fetch_all(
            "SELECT decision, COUNT(*) AS cnt FROM risk_assessment GROUP BY decision")}
        levels = {r["risk_level"]: r["cnt"] for r in db.fetch_all(
            "SELECT risk_level, COUNT(*) AS cnt FROM risk_assessment GROUP BY risk_level")}
        cases = case_service.case_stats(db)
        avg_score = float(db.scalar("SELECT COALESCE(AVG(final_score),0) FROM risk_assessment"))
        veto = db.scalar("SELECT COUNT(*) FROM risk_assessment WHERE is_veto = 1")
        blacklist = db.scalar("SELECT COUNT(*) FROM risk_blacklist "
                              "WHERE deleted_at IS NULL AND is_enabled = 1")
        rules_enabled = db.scalar("SELECT COUNT(*) FROM risk_rule "
                                  "WHERE deleted_at IS NULL AND is_enabled = 1")
    finally:
        db.close()
    return {"total_assessments": total_assessments, "decision_histogram": decisions,
            "risk_level_histogram": levels, "case_stats": cases,
            "avg_final_score": round(avg_score, 2), "veto_count": veto,
            "blacklist_total": blacklist, "rules_enabled": rules_enabled,
            "model_loaded": ml_model.is_model_loaded()}


@tool
def query_dashboard_stats() -> str:
    """查询风控大盘核心统计：评估总量、四种决策分布、风险等级分布、案件状态、平均分、一票否决次数。"""
    try:
        return _ok({"success": True, "data": _query_dashboard_stats_impl()})
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


# ====================================================================== 6 analyze_risk_trend
def _analyze_risk_trend_impl(days: int = 7) -> Dict[str, Any]:
    days = max(1, min(days, 90))
    start = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    db = _db()
    try:
        rows = db.fetch_all(
            """SELECT date(create_time) AS d, COUNT(*) AS total,
                      SUM(CASE WHEN decision = '拒绝' THEN 1 ELSE 0 END) AS reject_cnt,
                      SUM(CASE WHEN decision = '人工审核' THEN 1 ELSE 0 END) AS review_cnt,
                      COALESCE(AVG(final_score),0) AS avg_score
               FROM risk_assessment WHERE date(create_time) >= ?
               GROUP BY date(create_time) ORDER BY d""", [start])
    finally:
        db.close()
    series = [{"date": r["d"], "total": r["total"], "reject": r["reject_cnt"],
               "review": r["review_cnt"], "avg_score": round(float(r["avg_score"]), 2)}
              for r in rows]
    total = sum(s["total"] for s in series)
    reject = sum(s["reject"] for s in series)
    trend = "数据不足"
    if len(series) >= 4:
        half = len(series) // 2
        first = sum(s["avg_score"] for s in series[:half]) / max(half, 1)
        second = sum(s["avg_score"] for s in series[half:]) / max(len(series) - half, 1)
        diff = second - first
        trend = "风险上升" if diff > 3 else ("风险下降" if diff < -3 else "基本平稳")
    return {"days": days, "series": series, "total": total, "reject": reject,
            "reject_rate": round(reject / total * 100, 2) if total else 0.0,
            "trend": trend}


@tool
def analyze_risk_trend(days: int = 7) -> str:
    """按天分析风险趋势：每日评估量、拒绝量、人工审核量、平均分，并给出上升/下降判断。

    参数：
        days: 分析最近多少天，默认 7，最大 90
    """
    try:
        return _ok({"success": True, "data": _analyze_risk_trend_impl(days)})
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


# ====================================================================== 7 analyze_rule_effectiveness
def _analyze_rule_effectiveness_impl(top_n: int = 10) -> Dict[str, Any]:
    top_n = max(1, min(top_n, 30))
    db = _db()
    try:
        rules = db.fetch_all(
            "SELECT rule_id, rule_name, rule_category, risk_level, risk_score, hit_count, "
            "is_enabled FROM risk_rule WHERE deleted_at IS NULL ORDER BY hit_count DESC")
        total_assessments = db.scalar("SELECT COUNT(*) FROM risk_assessment")
    finally:
        db.close()
    total_hits = sum(int(r["hit_count"] or 0) for r in rules)
    for row in rules:
        hits = int(row["hit_count"] or 0)
        row["hit_share"] = round(hits / total_hits * 100, 2) if total_hits else 0.0
    zombies = [r["rule_id"] for r in rules
               if int(r["hit_count"] or 0) == 0 and int(r["is_enabled"] or 0) == 1]
    return {"total_rules": len(rules), "total_hits": total_hits,
            "total_assessments": total_assessments,
            "overall_hit_rate": round(total_hits / total_assessments * 100, 2)
            if total_assessments else 0.0,
            "top_rules": rules[:top_n], "zombie_rules": zombies,
            "zombie_count": len(zombies)}


@tool
def analyze_rule_effectiveness(top_n: int = 10) -> str:
    """分析规则命中率：命中 TOP N 规则、命中占比、以及从未命中的"僵尸规则"清单。

    参数：
        top_n: 返回命中最多的前 N 条规则，默认 10，最大 30
    """
    try:
        return _ok({"success": True, "data": _analyze_rule_effectiveness_impl(top_n)})
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


# ====================================================================== 8 query_business_data
_BUSINESS_QUERIES: Dict[str, Dict[str, str]] = {
    "学习记录": {"table": "order_info", "user_col": "user_id",
             "cols": "order_id, user_id, order_status, total_amount, pay_amount, "
                     "discount_amount, receive_id, create_time, pay_time"},
    "选课": {"table": "postsale", "user_col": "user_id",
             "cols": "postsale_id, user_id, order_id, postsale_type, postsale_status, "
                     "refund_amount, reason, create_time"},
    "关联实体": {"table": "user_address", "user_col": "user_id",
             "cols": "address_id, user_id, province, city, detail_address, is_default, create_time"},
    "申诉": {"table": "refund_record", "user_col": "",
             "cols": "refund_id, order_id, refund_amount, refund_status, refund_reason, create_time"},
    "反馈": {"table": "complaint_record", "user_col": "user_id",
             "cols": "complaint_id, user_id, order_id, complaint_type, complaint_content, "
                     "handle_status, create_time"},
    "登录": {"table": "login_log", "user_col": "user_id",
             "cols": "log_id, user_id, login_ip, login_city, device_id, login_status, login_time"},
}


def _query_business_data_impl(data_type: str, user_id: str = "", limit: int = 10) -> Dict[str, Any]:
    conf = _BUSINESS_QUERIES.get((data_type or "").strip())
    if conf is None:
        raise HTTPError(400, f"data_type 必须是 {list(_BUSINESS_QUERIES)} 之一")
    limit = max(1, min(limit, 50))
    where = "1=1"
    params: List[Any] = []
    if user_id:
        if conf["user_col"]:
            where = f'{conf["user_col"]} = ?'
            params.append(user_id)
        else:                                       # 退款表要 join 订单才知道用户
            where = "order_id IN (SELECT order_id FROM order_info WHERE user_id = ?)"
            params.append(user_id)
    db = _db()
    try:
        rows = db.fetch_all(
            f'SELECT {conf["cols"]} FROM "{conf["table"]}" WHERE {where} '
            f"ORDER BY create_time DESC LIMIT ?", params + [limit])
        total = db.scalar(f'SELECT COUNT(*) FROM "{conf["table"]}" WHERE {where}', params)
    finally:
        db.close()
    return {"data_type": data_type, "table": conf["table"], "total": total, "items": rows}


@tool
def query_business_data(data_type: str, user_id: str = "", limit: int = 10) -> str:
    """查询原始业务数据，用于核对风控结论。

    参数：
        data_type: 订单 / 售后 / 地址 / 退款 / 投诉 / 登录
        user_id: 用户 ID（可选，不传则查全量最近记录）
        limit: 返回条数，默认 10，最大 50
    """
    try:
        return _ok({"success": True, "data": _query_business_data_impl(data_type, user_id, limit)})
    except HTTPError as exc:
        return _err(f"{exc.status_code} {exc.detail}")
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


# ====================================================================== 汇总
ALL_TOOLS: List[Any] = [
    risk_check, query_cases, query_user_profile, manage_blacklist,
    query_dashboard_stats, analyze_risk_trend, analyze_rule_effectiveness, query_business_data,
]
assert len(ALL_TOOLS) == 8, "宝典 11.2：必须是 8 个 @tool"

#: name → (tool, impl) 映射，无 LLM 时的"本地工具直连"模式用它
TOOL_IMPLS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "risk_check": _risk_check_impl,
    "query_cases": _query_cases_impl,
    "query_user_profile": _query_user_profile_impl,
    "manage_blacklist": _manage_blacklist_impl,
    "query_dashboard_stats": _query_dashboard_stats_impl,
    "analyze_risk_trend": _analyze_risk_trend_impl,
    "analyze_rule_effectiveness": _analyze_rule_effectiveness_impl,
    "query_business_data": _query_business_data_impl,
}

TOOL_CATALOG: List[Dict[str, Any]] = [
    {"index": 1, "name": "risk_check", "purpose": "触发一次风控检查"},
    {"index": 2, "name": "query_cases", "purpose": "查案件（带状态过滤）"},
    {"index": 3, "name": "query_user_profile", "purpose": "查用户风险画像"},
    {"index": 4, "name": "manage_blacklist", "purpose": "黑名单增删查（4 子动作）"},
    {"index": 5, "name": "query_dashboard_stats", "purpose": "仪表盘统计"},
    {"index": 6, "name": "analyze_risk_trend", "purpose": "风险趋势分析（按天）"},
    {"index": 7, "name": "analyze_rule_effectiveness", "purpose": "规则命中率分析"},
    {"index": 8, "name": "query_business_data", "purpose": "业务数据查询（订单/售后/地址）"},
]


def tool_specs() -> List[Dict[str, Any]]:
    """给 /api/agent/tools 用：8 个工具的名称 / 描述 / 参数。"""
    out: List[Dict[str, Any]] = []
    for meta, obj in zip(TOOL_CATALOG, ALL_TOOLS):
        if isinstance(obj, ToolSpec):
            spec = obj.spec()
        else:                                        # LangChain BaseTool
            spec = obj.__dict__.get("_ai_risk_spec") or {
                "name": getattr(obj, "name", meta["name"]),
                "description": getattr(obj, "description", ""),
                "args": {}, "backend": "langchain"}
        out.append(spec | {"index": meta["index"], "purpose": meta["purpose"]})
    return out
