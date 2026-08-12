"""pytest 配置: 把项目根加入 sys.path, 让 tests 能 import app.*"""
import os
import sys

# 项目根 (tele-risk/) 加入 sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
