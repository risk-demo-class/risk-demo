"""测试隔离：每个测试使用全新临时 SQLite 库并重新播种，避免污染开发库。

背景：``app.database`` 默认使用仓库根的 ``education_risk.db``，而测试直接
import ``app.main``（模块导入时建表并播种）。这导致：
1. 测试会向开发库写入评估、案件并改变案件状态；
2. 再次运行 ``pytest`` 时，``items[0]`` 可能命中上一次运行留下的终态案件，
   出现 ``400 != 200`` 之类的偶发失败。

本文件必须在任何 ``app.*`` 模块被导入前设置环境变量，因此放在 conftest 模块
顶层（pytest 会先加载 conftest，再收集测试模块）。
"""

import os
import tempfile

import pytest

_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["EDUCATION_RISK_DATABASE_URL"] = "sqlite:///" + _TMP_DB.name.replace("\\", "/")

# 此时再导入 app.*，engine 会绑定到上面的临时库。
from app.database import Base, engine, SessionLocal  # noqa: E402
from app.seed import seed_demo_data  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_database():
    """每个测试前重建全部表并重新播种演示数据，保证用例互不依赖、可重复运行。"""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        session.close()
    seed_demo_data()
    yield


@pytest.fixture(scope="session", autouse=True)
def _cleanup_temp_db():
    """会话结束后删除临时测试库文件。"""
    yield
    try:
        os.remove(_TMP_DB.name)
    except OSError:
        pass
