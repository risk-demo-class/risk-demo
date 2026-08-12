# -*- coding: utf-8 -*-
r"""微型模板引擎 —— Jinja2 的**零依赖等价物**

宝典要求前端用模板渲染（`web/templates/`），但项目不允许 pip install。
本模块实现 Jinja2 最常用的 3 个语法，教学时可一一对照：

| Jinja2                       | 本引擎                | 说明                     |
|------------------------------|----------------------|--------------------------|
| `{{ name }}`                 | `{{ name }}`         | 变量替换（自动 HTML 转义）  |
| `{{ name \| safe }}`         | `{{ name \| safe }}` | 不转义（用于嵌入 HTML 片段）|
| `{% include "partial.html" %}`| 同左                 | 片段包含（支持递归嵌套）    |

刻意**不实现** `{% for %}` / `{% if %}` —— 因为本项目是 SPA：
数据全部由前端 JS 通过 30 个 API 拉取渲染，服务端模板只负责「骨架 + 片段拼装」。
这样职责边界最清晰，也避免自研模板引擎陷入无底洞。
"""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any, Dict

_VAR_RE = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(\|\s*safe\s*)?}}")
_INCLUDE_RE = re.compile(r"""{%\s*include\s+["']([^"']+)["']\s*%}""")

_MAX_INCLUDE_DEPTH = 8


class TemplateError(Exception):
    """模板不存在或包含层级过深。"""


class TemplateEngine:
    """按目录加载模板，带一层内存缓存（DEBUG 模式下自动失效）。"""

    def __init__(self, directory: Path, cache: bool = True) -> None:
        self.directory = Path(directory)
        self.cache_enabled = cache
        self._cache: Dict[str, str] = {}

    # ------------------------------------------------------------ 读取
    def _read(self, name: str) -> str:
        if self.cache_enabled and name in self._cache:
            return self._cache[name]
        target = (self.directory / name).resolve()
        # 防目录穿越：解析后的真实路径必须仍在模板目录内
        if not str(target).startswith(str(self.directory.resolve())):
            raise TemplateError(f"非法模板路径: {name}")
        if not target.is_file():
            raise TemplateError(f"模板不存在: {name}")
        text = target.read_text(encoding="utf-8")
        if self.cache_enabled:
            self._cache[name] = text
        return text

    # ------------------------------------------------------------ 渲染
    def _expand_includes(self, text: str, depth: int = 0) -> str:
        if depth > _MAX_INCLUDE_DEPTH:
            raise TemplateError(f"include 嵌套超过 {_MAX_INCLUDE_DEPTH} 层，疑似循环包含")
        if "{% include" not in text:
            return text

        def repl(match: "re.Match[str]") -> str:
            return self._expand_includes(self._read(match.group(1)), depth + 1)

        return _INCLUDE_RE.sub(repl, text)

    def render(self, name: str, **context: Any) -> str:
        text = self._expand_includes(self._read(name))

        def repl(match: "re.Match[str]") -> str:
            key, safe = match.group(1), match.group(2)
            if key not in context:
                return match.group(0)          # 未提供的变量原样保留，便于排查
            value = context[key]
            raw = "" if value is None else str(value)
            return raw if safe else html.escape(raw, quote=True)

        return _VAR_RE.sub(repl, text)

    def clear_cache(self) -> None:
        self._cache.clear()


__all__ = ["TemplateEngine", "TemplateError"]
