"""pytest 全局配置."""

import os

# 测试环境不加载 XGBoost 模型, 避免 OpenMP 线程导致进程退出挂起
os.environ.setdefault("XGB_ENABLED", "false")
os.environ.setdefault("LLM_ENABLED", "false")
os.environ.setdefault("ALERT_SCHEDULER_INTERVAL_MIN", "0")
