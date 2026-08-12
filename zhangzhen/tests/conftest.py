"""测试配置：强制使用独立的 SQLite 内存数据库。"""

import os


os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["APP_ENV"] = "test"

