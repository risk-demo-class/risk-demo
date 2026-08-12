"""
pytest 全局配置 (conftest.py)

Windows 上系统 Temp 目录 (C:/Users/<user>/AppData/Local/Temp/pytest-of-<user>)
可能出现权限残留 (WinError 5: 拒绝访问), 导致所有用 tmp_path fixture 的测试
在 setup 阶段 os.scandir() 崩溃.

修复: 通过 pytest_configure 钩子, 未显式传 --basetemp 时默认用项目内 .pytest_tmp.
"""
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pytest_configure(config):
    if not getattr(config.option, "basetemp", None):
        config.option.basetemp = os.path.join(_PROJECT_ROOT, ".pytest_tmp")
