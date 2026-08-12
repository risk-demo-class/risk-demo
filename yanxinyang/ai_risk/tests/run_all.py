# -*- coding: utf-8 -*-
"""一键跑全部测试（单元 + 集成 + 前端渲染）。

用法：
    python tests/run_all.py

会自动判断服务是否在跑：
    未启动 → 只跑单元测试，并提示如何启动
    已启动 → 单元 + 集成 + 前端页面渲染（前端需要 node，缺了就跳过）
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _line(title: str) -> None:
    print("\n" + "=" * 68)
    print("  " + title)
    print("=" * 68)


def main() -> int:
    from tests.test_api import server_up

    up = server_up()
    failed = 0

    _line("① 核心引擎单元测试（规则引擎 / 双轨融合 / 状态机 / 25 维特征）")
    loader = unittest.TestLoader()
    res = unittest.TextTestRunner(verbosity=2).run(loader.loadTestsFromName("tests.test_core"))
    failed += len(res.failures) + len(res.errors)

    _line("② API 集成测试（30 个端点 / 7 步流水线 / SSE）")
    if not up:
        print("服务未启动，跳过。请另开终端运行： python _run.py")
    else:
        res = unittest.TextTestRunner(verbosity=2).run(loader.loadTestsFromName("tests.test_api"))
        failed += len(res.failures) + len(res.errors)

    _line("③ 前端 12 页渲染冒烟（Node 最小 DOM 桩）")
    node = shutil.which("node")
    if not up:
        print("服务未启动，跳过。")
    elif not node:
        print("未找到 node，跳过前端渲染测试（不影响后端功能）。")
    else:
        proc = subprocess.run([node, str(_ROOT / "tests" / "smoke_pages.js")],
                              cwd=str(_ROOT), text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            failed += 1

    _line("汇总")
    if failed:
        print(f"存在 {failed} 处失败，请查看上方输出。")
        return 1
    print("全部测试通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
