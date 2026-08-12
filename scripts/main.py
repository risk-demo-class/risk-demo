"""
电商风控系统 - 应用入口
启动 FastAPI 服务，注册所有路由和中间件
"""
# 将项目根目录加入 Python 路径
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import logging.config


from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pydantic import ValidationError

from app.api import (
    agent_router,
    alert_router,
    assessment_router,
    blacklist_router,
    case_router,
    dashboard_router,
    page_router,
    profile_router,
    risk_router,
    rule_router,
)

# 【P4-L4 2026-08-08】统一日志配置: 业务 logger + uvicorn 全走 console + logs/app.log
# 用 dictConfig 而不是 basicConfig, 这样能精细控制 handlers / formatters
from app.logging_config import LOGGING_CONFIG
logging.config.dictConfig(LOGGING_CONFIG)

# 【P4-L3 2026-08-08】lifespan: 启动/停止后台调度器
# 替代旧的 @app.on_event("startup") (FastAPI 0.93+ 已 deprecated)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动: 启动案件超时关闭 + 告警检查调度
    from app.scheduler import start_scheduler, stop_scheduler, is_running
    start_scheduler()
    app.state.scheduler_running = is_running()
    yield
    # 停止: 优雅关闭调度 (等当前轮跑完, 最多 10s)
    await stop_scheduler()
    app.state.scheduler_running = False

app = FastAPI(
    title="物流风控系统",
    description="基于规则引擎 + XGBoost + AI Agent 的物流行业风险控制系统",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------- 全局 422 / Pydantic 校验错误 中文翻译 ----------
# 覆盖 Pydantic v2 常见 type (最常出问题的一批). 未覆盖到的保持原文 (兜底).
# 格式参考: https://docs.pydantic.dev/latest/errors/validation_errors/
_PYDANTIC_MSG_ZH = {
    # ---- 类型类 ----
    "int_parsing":           "值必须是整数",
    "int_from_float":        "值必须是整数 (不允许小数)",
    "float_parsing":         "值必须是数字",
    "bool_parsing":          "值必须是布尔值 (true/false)",
    "string_parsing":        "值必须是字符串",
    "value_error":           "值非法",

    # ---- Input should be a valid X (Pydantic v2 通用句式) ----
    "Input should be a valid integer":     "必须是合法整数",
    "Input should be a valid number":      "必须是合法数字",
    "Input should be a valid string":      "必须是合法字符串",
    "Input should be a valid boolean":     "必须是 true 或 false",
    "Input should be a valid list":        "必须是数组 (list)",
    "Input should be a valid dictionary":  "必须是对象 (dict)",
    "Input should be a valid object":      "必须是合法对象",
    "Input should be a valid datetime":    "必须是合法日期时间 (ISO 格式)",
    "Input should be a valid date":        "必须是合法日期 (YYYY-MM-DD)",

    # ---- 范围 / 约束类 ----
    "greater_than_equal":     "值必须大于等于 {ge}",
    "less_than_equal":        "值必须小于等于 {le}",
    "greater_than":           "值必须大于 {gt}",
    "less_than":              "值必须小于 {lt}",
    "string_too_short":       "字符串太短 (至少 {min_length} 个字符)",
    "string_too_long":        "字符串太长 (最多 {max_length} 个字符)",
    "too_short":              "列表太短 (至少 {min_length} 项)",
    "too_long":               "列表太长 (最多 {max_length} 项)",
    "multiple_of":            "值必须是 {multiple_of} 的倍数",

    # ---- 枚举 / Literal ----
    "literal_error":          "值必须是以下之一: {expected}",

    # ---- 通用 ----
    "missing":                "缺少必填字段",
    "unexpected_keyword":     "含有不允许的额外字段",
    "forbidden":              "该字段不允许出现",
    "none_required":          "该字段必须为 null",
    "assertion_error":        "自定义校验失败",
}

def _translate_zh(msg_en: str, ctx_type: str | None, ctx: dict | None) -> str:
    """把 Pydantic 英文 msg 尽量翻译成中文. 失败则保留英文."""
    try:
        # 1) 直接整句匹配 (最高优先级)
        if msg_en in _PYDANTIC_MSG_ZH:
            tmpl = _PYDANTIC_MSG_ZH[msg_en]
            if ctx:
                return tmpl.format(**{k: ctx.get(k, '') for k in ['ge', 'le', 'gt', 'lt', 'min_length', 'max_length', 'multiple_of', 'expected'] if k in tmpl})
            return tmpl
        # 2) 用 error.type 匹配 (更稳定, 不随 Pydantic 英文措辞波动)
        if ctx_type and ctx_type in _PYDANTIC_MSG_ZH:
            tmpl = _PYDANTIC_MSG_ZH[ctx_type]
            if ctx:
                return tmpl.format(**{k: ctx.get(k, '') for k in ['ge', 'le', 'gt', 'lt', 'min_length', 'max_length', 'multiple_of', 'expected'] if k in tmpl})
            return tmpl
        # 3) 未命中 -> 返回英文原文
        return msg_en
    except Exception:
        return msg_en

def _rewrite_detail(errors):
    """递归把 FastAPI 返回的 errors 列表 [{loc, type, msg, input, ctx}...] 的 msg 中文化."""
    if not isinstance(errors, list):
        return errors
    rewritten = []
    for item in errors:
        if not isinstance(item, dict):
            rewritten.append(item)
            continue
        new_item = dict(item)
        new_item['msg'] = _translate_zh(
            str(item.get('msg', '')),
            item.get('type'),
            item.get('ctx'),
        )
        rewritten.append(new_item)
    return rewritten

@app.exception_handler(ValidationError)
async def _pydantic_validation_error_handler(request: Request, exc: ValidationError):
    # 手动在业务里 raise ValidationError 的场景 (极少数)
    return JSONResponse(
        status_code=422,
        content={"detail": _rewrite_detail(exc.errors())},
    )

# FastAPI 路由参数 / Body 校验失败 -> RequestValidationError (走这个)
try:
    from fastapi.exceptions import RequestValidationError
except Exception:  # pragma: no cover
    RequestValidationError = None  # type: ignore

if RequestValidationError is not None:
    @app.exception_handler(RequestValidationError)
    async def _request_validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"detail": _rewrite_detail(exc.errors())},
        )

# 挂载静态资源
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app.mount("/static", StaticFiles(directory=os.path.join(_BASE_DIR, "static")), name="static")

# 注册路由
app.include_router(page_router)
app.include_router(risk_router)
app.include_router(rule_router)
app.include_router(case_router)
app.include_router(blacklist_router)
app.include_router(profile_router)
app.include_router(dashboard_router)
app.include_router(agent_router)
app.include_router(alert_router)   # 【P4-L2】告警路由
app.include_router(assessment_router)   # 【P3-S9】评估历史路由

if __name__ == "__main__":
    import uvicorn
    # 【P4-L3】reload=True 跟 lifespan 有点冲突, 调度器会启 2 次. 生产用 gunicorn (无 reload)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
