# -*- coding: utf-8 -*-
"""微型 Web 框架 —— 替代 FastAPI 的**零依赖等价物**

为什么自带框架？项目要求"打开 PyCharm 直接 Run 就能跑"，不允许 pip 安装。
本框架刻意做成 FastAPI 的同构 API，教学时可以一一对照：

| FastAPI                          | 本框架                                |
|----------------------------------|--------------------------------------|
| `APIRouter(prefix=..., tags=..)` | `Router(prefix=..., tags=..)`         |
| `@router.post("/check")`         | `@router.post("/check")`              |
| `HTTPException(status_code=403)` | `HTTPError(403, "...")`               |
| `app.include_router(r)`          | `app.include_router(r)`               |
| `/docs` Swagger UI               | `/docs` 自动生成的端点清单页             |
| `StreamingResponse` (SSE)        | `SSEResponse`（HTTP/1.0 + 不 keep-alive）|
"""
from __future__ import annotations

import json
import logging
import re
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

logger = logging.getLogger("ai_risk.http")

JSONEncodable = Any


class HTTPError(Exception):
    """对齐 FastAPI 的 HTTPException。"""

    def __init__(self, status_code: int, detail: str, code: str = "") -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.code = code or f"E{status_code}"


class JsonEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:  # noqa: D102
        if isinstance(o, (datetime, date)):
            return o.strftime("%Y-%m-%d %H:%M:%S") if isinstance(o, datetime) else o.isoformat()
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, set):
            return sorted(o)
        if hasattr(o, "__dict__"):
            return {k: v for k, v in vars(o).items() if not k.startswith("_")}
        return str(o)


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, cls=JsonEncoder)


@dataclass
class Request:
    method: str
    path: str
    query: Dict[str, List[str]]
    headers: Dict[str, str]
    body: bytes
    path_params: Dict[str, str] = field(default_factory=dict)
    client_ip: str = ""

    # ------------------------------------------------------------ 参数读取
    def q(self, name: str, default: Any = None) -> Any:
        values = self.query.get(name)
        return values[0] if values else default

    def q_int(self, name: str, default: int = 0) -> int:
        raw = self.q(name)
        try:
            return int(str(raw))
        except (TypeError, ValueError):
            return default

    def q_bool(self, name: str, default: bool = False) -> bool:
        raw = self.q(name)
        if raw is None:
            return default
        return str(raw).strip().lower() in ("1", "true", "yes", "on")

    def json(self) -> Dict[str, Any]:
        if not self.body:
            return {}
        try:
            data = json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPError(400, f"请求体不是合法 JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise HTTPError(400, "请求体必须是 JSON 对象")
        return data

    def wants_sse(self) -> bool:
        return "text/event-stream" in self.headers.get("accept", "")


@dataclass
class Response:
    body: bytes
    status: int = 200
    content_type: str = "application/json; charset=utf-8"
    headers: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def json(cls, data: Any, status: int = 200) -> "Response":
        return cls(dumps(data).encode("utf-8"), status)

    @classmethod
    def html(cls, text: str, status: int = 200) -> "Response":
        return cls(text.encode("utf-8"), status, "text/html; charset=utf-8")

    @classmethod
    def text(cls, text: str, status: int = 200) -> "Response":
        return cls(text.encode("utf-8"), status, "text/plain; charset=utf-8")


@dataclass
class SSEResponse:
    """Server-Sent Events（宝典 11.1 `DeepAgent -.SSE.-> User`）。

    ⚠️ 标准库 http.server 做 SSE 的两个坑（已处理）：
        1. 必须 `protocol_version = "HTTP/1.0"`
        2. **不要**发送 `Connection: keep-alive`，否则连接不关闭、客户端一直挂起
    """

    events: Iterable[Tuple[str, Any]]
    status: int = 200


@dataclass
class Route:
    method: str
    path: str
    regex: "re.Pattern[str]"
    handler: Callable[..., Any]
    summary: str
    tags: List[str]
    router: str


_PARAM_RE = re.compile(r"{([a-zA-Z_][a-zA-Z0-9_]*)}")


def _compile(path: str) -> "re.Pattern[str]":
    pattern = _PARAM_RE.sub(lambda m: f"(?P<{m.group(1)}>[^/]+)", path)
    return re.compile(f"^{pattern}$")


class Router:
    """对齐 FastAPI 的 APIRouter。"""

    def __init__(self, prefix: str = "", tags: Optional[List[str]] = None, name: str = "") -> None:
        self.prefix = prefix.rstrip("/")
        self.tags = tags or []
        self.name = name or (tags[0] if tags else prefix.strip("/"))
        self.routes: List[Route] = []

    def _add(self, method: str, path: str, summary: str) -> Callable:
        def decorator(func: Callable) -> Callable:
            full = f"{self.prefix}{path}" or "/"
            self.routes.append(Route(method, full, _compile(full), func,
                                     summary, list(self.tags), self.name))
            return func
        return decorator

    def get(self, path: str, summary: str = "") -> Callable:
        return self._add("GET", path, summary)

    def post(self, path: str, summary: str = "") -> Callable:
        return self._add("POST", path, summary)

    def put(self, path: str, summary: str = "") -> Callable:
        return self._add("PUT", path, summary)

    def delete(self, path: str, summary: str = "") -> Callable:
        return self._add("DELETE", path, summary)


class RiskApp:
    """对齐 FastAPI 应用对象。"""

    def __init__(self, title: str, version: str) -> None:
        self.title = title
        self.version = version
        self.routes: List[Route] = []
        self._static: List[Tuple[str, Any]] = []
        self._startup: List[Callable[[], None]] = []

    # ------------------------------------------------------------ 注册
    def include_router(self, router: Router) -> None:
        self.routes.extend(router.routes)

    def mount_static(self, url_prefix: str, directory: Any) -> None:
        self._static.append((url_prefix.rstrip("/"), directory))

    def on_startup(self, func: Callable[[], None]) -> Callable[[], None]:
        self._startup.append(func)
        return func

    def run_startup(self) -> None:
        for func in self._startup:
            func()

    # ------------------------------------------------------------ 分发
    def match(self, method: str, path: str) -> Tuple[Optional[Route], Dict[str, str], bool]:
        path_exists = False
        for route in self.routes:
            m = route.regex.match(path)
            if not m:
                continue
            path_exists = True
            if route.method == method:
                return route, {k: unquote(v) for k, v in m.groupdict().items()}, True
        return None, {}, path_exists

    def api_catalog(self) -> List[Dict[str, Any]]:
        """/docs 与前端「API 目录」页共用。"""
        grouped: Dict[str, List[Dict[str, str]]] = {}
        for route in self.routes:
            if not route.path.startswith("/api/"):
                continue
            grouped.setdefault(route.router, []).append(
                {"method": route.method, "path": route.path, "summary": route.summary})
        return [{"router": name, "endpoints": eps} for name, eps in grouped.items()]

    def api_endpoint_count(self) -> int:
        return sum(1 for r in self.routes if r.path.startswith("/api/"))


CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
    ".woff2": "font/woff2", ".map": "application/json",
}


def make_handler(app: RiskApp) -> type:
    class Handler(BaseHTTPRequestHandler):
        # ⚠️ SSE 必须 HTTP/1.0（见 SSEResponse 注释）
        protocol_version = "HTTP/1.0"
        server_version = f"ZhiXueAn/{app.version}"

        # -------------------------------------------------- 日志
        def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
            logger.info("%s - %s", self.address_string(), fmt % args)

        # -------------------------------------------------- 方法
        def do_GET(self) -> None:  # noqa: N802
            self._handle("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._handle("POST")

        def do_PUT(self) -> None:  # noqa: N802
            self._handle("PUT")

        def do_DELETE(self) -> None:  # noqa: N802
            self._handle("DELETE")

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._send(Response(b"", 204, "text/plain"))

        # -------------------------------------------------- 核心
        def _handle(self, method: str) -> None:
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            try:
                length = int(self.headers.get("content-length") or 0)
            except ValueError:
                length = 0
            body = self.rfile.read(length) if length > 0 else b""
            headers = {k.lower(): v for k, v in self.headers.items()}
            request = Request(method=method, path=path, query=parse_qs(parsed.query),
                              headers=headers, body=body,
                              client_ip=self.client_address[0] if self.client_address else "")

            static = self._match_static(path)
            if static is not None and method == "GET":
                self._send(static)
                return

            route, params, path_exists = app.match(method, path)
            if route is None:
                if path_exists:
                    self._send(Response.json({"detail": f"方法 {method} 不被允许", "code": "E405"}, 405))
                else:
                    self._send(Response.json({"detail": f"接口不存在: {path}", "code": "E404"}, 404))
                return

            request.path_params = params
            try:
                result = route.handler(request)
            except HTTPError as exc:
                logger.warning("业务异常 %s %s -> %s %s", method, path, exc.status_code, exc.detail)
                self._send(Response.json({"detail": exc.detail, "code": exc.code}, exc.status_code))
                return
            except Exception as exc:  # noqa: BLE001
                logger.error("未捕获异常 %s %s: %s\n%s", method, path, exc, traceback.format_exc())
                self._send(Response.json({"detail": f"服务器内部错误: {exc}", "code": "E500"}, 500))
                return

            if isinstance(result, SSEResponse):
                self._send_sse(result)
            elif isinstance(result, Response):
                self._send(result)
            else:
                self._send(Response.json(result))

        # -------------------------------------------------- 静态文件
        def _match_static(self, path: str) -> Optional[Response]:
            for prefix, directory in app._static:  # noqa: SLF001
                if not path.startswith(prefix + "/"):
                    continue
                rel = path[len(prefix) + 1:]
                if ".." in rel:
                    return Response.text("非法路径", 400)
                target = directory / rel
                if not target.is_file():
                    return Response.text(f"静态文件不存在: {rel}", 404)
                ctype = CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")
                return Response(target.read_bytes(), 200, ctype,
                                {"Cache-Control": "no-cache"})
            return None

        # -------------------------------------------------- 发送
        def _send(self, response: Response) -> None:
            try:
                self.send_response(response.status)
                self.send_header("Content-Type", response.content_type)
                self.send_header("Content-Length", str(len(response.body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
                self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
                for key, value in response.headers.items():
                    self.send_header(key, value)
                self.end_headers()
                if response.body:
                    self.wfile.write(response.body)
            except (BrokenPipeError, ConnectionResetError):
                logger.debug("客户端提前断开: %s", self.path)

        def _send_sse(self, response: SSEResponse) -> None:
            try:
                self.send_response(response.status)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Accel-Buffering", "no")
                # 注意：绝不发送 Connection: keep-alive
                self.end_headers()
                for event, payload in response.events:
                    chunk = f"event: {event}\ndata: {dumps(payload)}\n\n"
                    self.wfile.write(chunk.encode("utf-8"))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                logger.debug("SSE 客户端断开: %s", self.path)

    return Handler


def serve(app: RiskApp, host: str, port: int) -> None:
    app.run_startup()
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    httpd.daemon_threads = True
    logger.info("服务已启动: http://%s:%d  (API 端点 %d 个)", host, port, app.api_endpoint_count())
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在关闭...")
    finally:
        httpd.server_close()
