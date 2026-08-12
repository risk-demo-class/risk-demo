"""
pytest 公共配置.

关键: pytest-asyncio 每个测试函数用独立 event loop, 而全局 async_engine
连接池会把上一个 loop 创建的 aiomysql 连接复用给下一个 loop → 报
"Future attached to a different loop". autouse fixture 在每次测试后
dispose 引擎清空连接池, 强制下个测试新建连接 (代价: 慢一点, 稳很多).
"""
import pytest

from app.database import async_engine


@pytest.fixture(autouse=True)
async def _dispose_engine_after_each_test():
    yield
    await async_engine.dispose()
