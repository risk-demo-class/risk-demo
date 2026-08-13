"""统一控制台输出层：让所有脚本保持 init_db.py 的观感。

用法:
    from scripts._console import banner, step, kv, ok, warn, error, summary, progress, silence_loggers

设计约定:
  - 全部走 print 到 stdout, 不依赖第三方库 (tqdm/rich).
  - ANSI 颜色仅 TTY 且未设置 NO_COLOR 时启用; 管道/日志文件里自动关闭.
  - Windows GBK 控制台由各脚本入口 reconfigure(encoding="utf-8") 保证.
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import contextmanager
from typing import Iterable

WIDTH = 70

# 颜色开关: 仅交互式终端 + 未显式禁用
_USE_COLOR = (
    hasattr(sys.stdout, "isatty")
    and bool(sys.stdout.isatty())
    and os.environ.get("NO_COLOR") is None
)


def _paint(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


def bold(text: str) -> str:
    return _paint("1", text)


def cyan(text: str) -> str:
    return _paint("36", text)


def green(text: str) -> str:
    return _paint("32", text)


def yellow(text: str) -> str:
    return _paint("33", text)


def red(text: str) -> str:
    return _paint("31", text)


def banner(title: str, sub: str | None = None) -> None:
    """开头横幅: ==== 标题 ===="""
    print("=" * WIDTH)
    print(bold(title))
    if sub:
        print(sub)
    print("=" * WIDTH)


def footer(text: str) -> None:
    """结尾横幅."""
    print("=" * WIDTH)
    print(bold(text))
    print("=" * WIDTH)


def step(i: int, n: int, desc: str) -> None:
    """步骤标题: [步骤 i/n] 描述"""
    print(f"\n[{cyan(f'步骤 {i}/{n}')}] {desc}")


def kv(key: str, value: object, indent: str = "  ", width: int = 22) -> None:
    """对齐的 键: 值 行."""
    print(f"{indent}{key:<{width}}{value}")


def ok(text: str) -> None:
    print(f"  {green('✓')} {text}")


def warn(text: str) -> None:
    print(f"  {yellow('!')} {text}")


def error(text: str) -> None:
    print(f"  {red('✗')} {text}")


def summary(rows: list[tuple[str, object]], title: str | None = None) -> None:
    """对齐的 key-value 汇总表."""
    if title:
        print(f"\n{title}")
    if not rows:
        return
    width = max(len(str(k)) for k, _ in rows) + 2
    for k, v in rows:
        print(f"  {str(k):<{width}}{v}")


def progress(i: int, total: int, every: int = 100) -> None:
    """轻量进度: 每 every 条覆写一行, 结束补换行."""
    if total <= 0:
        return
    if i % every == 0 or i == total:
        pct = i / total * 100
        print(f"\r  进度: {i}/{total} ({pct:.0f}%)", end="", flush=True)
        if i == total:
            print()


@contextmanager
def silence_loggers(names: Iterable[str], level: int = logging.ERROR):
    """临时抬高指定 logger 级别, 屏蔽批量生成时刷屏的单条日志.

    示例: 生成数据时把 app.service.event 的"撞黑名单"warning 静音,
    由脚本在结尾统一统计撞黑数量再打印一行提示.
    """
    loggers = [logging.getLogger(name) for name in names]
    old_levels = [lg.level for lg in loggers]
    for lg in loggers:
        lg.setLevel(level)
    try:
        yield
    finally:
        for lg, lv in zip(loggers, old_levels):
            lg.setLevel(lv)
