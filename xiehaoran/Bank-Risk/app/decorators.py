"""
银行风控系统 - 通用装饰器 (复用基线)
"""
import functools
import time


def print_execution_time(func):
    """打印函数耗时 (debug 用)."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            print(f"[perf] {func.__name__} 耗时 {time.perf_counter() - t0:.3f}s")
    return wrapper
