# -*- coding: utf-8 -*-
"""数据库层 —— 对应教学宝典《第 13 章：数据库层》

宝典生产实现：
    async_engine = create_async_engine(settings.get_database_url_async(),
                                       pool_size=10, max_overflow=20, pool_recycle=3600)
    AsyncSessionLocal = async_sessionmaker(bind=async_engine, ...)

本文件用标准库 sqlite3 实现**同构语义**，逐条对齐宝典 13.2 的关键设计：

| 宝典设计                        | 本实现                                                  |
|--------------------------------|--------------------------------------------------------|
| 全异步 SQLAlchemy 2.x           | 线程池 + 连接池（不阻塞请求处理，接口保持 async 可包装）      |
| 连接池 10+20                    | ConnectionPool(pool_size=10, max_overflow=20)          |
| pool_recycle=3600s             | 超过 3600s 的空闲连接丢弃重建                              |
| 显式 try/finally + db.close()   | get_db() / session_scope() 全部显式 close，绝不依赖隐式退出 |
| Base.metadata 汇总 24 张表      | models.ALL_TABLES 汇总 24 张表 + 1 审计表                  |
"""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Sequence

from app.config import settings

logger = logging.getLogger("ai_risk.database")


class Base:
    """宝典 13.3：``class Base(DeclarativeBase)``。

    所有 ORM 继承它，启动时 ``Base.metadata`` 自动汇总 24 张表。
    本项目用轻量声明式表描述（见 models.py），Base.metadata 由 models 注册。
    """

    metadata: Dict[str, "Any"] = {}

    @classmethod
    def register(cls, table: Any) -> Any:
        cls.metadata[table.name] = table
        return table


# ====================================================================== 连接池
class ConnectionPool:
    """最小可用连接池：pool_size 常驻 + max_overflow 溢出 + pool_recycle 回收。"""

    def __init__(self, path: str, pool_size: int, max_overflow: int, recycle: int) -> None:
        self._path = path
        self._pool_size = pool_size
        self._max_overflow = max_overflow
        self._recycle = recycle
        self._idle: List[tuple[sqlite3.Connection, float]] = []
        self._checked_out = 0
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)

    # ------------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=30.0, check_same_thread=False,
                               isolation_level="")           # 隐式开启事务，末尾一次 commit
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")               # 读写并发
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.commit()
        return conn

    def acquire(self) -> sqlite3.Connection:
        deadline = time.time() + 30
        with self._cond:
            while True:
                while self._idle:
                    conn, born = self._idle.pop()
                    if self._recycle and (time.time() - born) > self._recycle:
                        try:                                  # pool_recycle：过期连接丢弃
                            conn.close()
                        except sqlite3.Error:
                            pass
                        continue
                    self._checked_out += 1
                    return conn
                if self._checked_out < self._pool_size + self._max_overflow:
                    self._checked_out += 1
                    return self._connect()
                if not self._cond.wait(timeout=max(0.0, deadline - time.time())):
                    raise TimeoutError("数据库连接池耗尽（pool_size=10 + max_overflow=20）")

    def release(self, conn: sqlite3.Connection, broken: bool = False) -> None:
        with self._cond:
            self._checked_out -= 1
            if broken or len(self._idle) >= self._pool_size:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
            else:
                self._idle.append((conn, time.time()))
            self._cond.notify()

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {"idle": len(self._idle), "checked_out": self._checked_out,
                    "pool_size": self._pool_size, "max_overflow": self._max_overflow}

    def dispose(self) -> None:
        with self._lock:
            for conn, _ in self._idle:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
            self._idle.clear()


pool = ConnectionPool(settings.DB_PATH, settings.DB_POOL_SIZE,
                      settings.DB_MAX_OVERFLOW, settings.DB_POOL_RECYCLE)


# ====================================================================== Session
class Session:
    """轻量 Session —— API 对齐 SQLAlchemy 的 execute / commit / rollback / close。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._broken = False
        self.closed = False

    # ---------------------------------------------------------- 查询原语
    def execute(self, sql: str, params: Sequence[Any] | Dict[str, Any] = ()) -> sqlite3.Cursor:
        try:
            return self._conn.execute(sql, params)
        except sqlite3.Error:
            self._broken = True
            logger.exception("SQL 执行失败: %s | params=%s", sql, params)
            raise

    def executemany(self, sql: str, seq: Sequence[Sequence[Any]]) -> sqlite3.Cursor:
        try:
            return self._conn.executemany(sql, seq)
        except sqlite3.Error:
            self._broken = True
            logger.exception("SQL 批量执行失败: %s", sql)
            raise

    def fetch_all(self, sql: str, params: Sequence[Any] | Dict[str, Any] = ()) -> List[Dict[str, Any]]:
        return [dict(row) for row in self.execute(sql, params).fetchall()]

    def fetch_one(self, sql: str, params: Sequence[Any] | Dict[str, Any] = ()) -> Optional[Dict[str, Any]]:
        row = self.execute(sql, params).fetchone()
        return dict(row) if row is not None else None

    def scalar(self, sql: str, params: Sequence[Any] | Dict[str, Any] = (), default: Any = 0) -> Any:
        row = self.execute(sql, params).fetchone()
        if row is None:
            return default
        value = row[0]
        return default if value is None else value

    def insert(self, table: str, values: Dict[str, Any]) -> int:
        cols = ", ".join(f'"{c}"' for c in values)
        holders = ", ".join("?" for _ in values)
        cur = self.execute(f'INSERT INTO "{table}" ({cols}) VALUES ({holders})', list(values.values()))
        return int(cur.lastrowid or 0)

    def insert_many(self, table: str, rows: Sequence[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        cols = list(rows[0].keys())
        col_sql = ", ".join(f'"{c}"' for c in cols)
        holders = ", ".join("?" for _ in cols)
        self.executemany(f'INSERT INTO "{table}" ({col_sql}) VALUES ({holders})',
                         [[r[c] for c in cols] for r in rows])
        return len(rows)

    def update(self, table: str, values: Dict[str, Any], where: str, params: Sequence[Any]) -> int:
        sets = ", ".join(f'"{c}" = ?' for c in values)
        cur = self.execute(f'UPDATE "{table}" SET {sets} WHERE {where}',
                           list(values.values()) + list(params))
        return cur.rowcount

    # ---------------------------------------------------------- 事务控制
    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        try:
            self._conn.rollback()
        except sqlite3.Error:
            self._broken = True

    def close(self) -> None:
        """宝典 13.2：**显式 close 更可控**（不依赖隐式 __aexit__）。"""
        if self.closed:
            return
        self.closed = True
        pool.release(self._conn, broken=self._broken)


@contextmanager
def session_scope() -> Iterator[Session]:
    """宝典 13.2 的显式 try/finally + 显式 db.close()。

    语义：整段代码一个事务 —— 正常结束 commit，异常 rollback，**finally 必 close**。
    """
    db = Session(pool.acquire())
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Iterator[Session]:
    """依赖注入风格（对齐 FastAPI ``Depends(get_db)``）：由调用方决定 commit。"""
    db = Session(pool.acquire())
    try:
        yield db
    finally:
        db.close()


def init_database(drop: bool = False) -> Dict[str, int]:
    """建表 + 灌 30 条预置规则（幂等）。"""
    from app import models                      # 延迟导入避免循环
    from app.data.rules_seed import PRESET_RULES

    stats = {"tables": 0, "rules": 0}
    with session_scope() as db:
        if drop:
            for name in reversed(list(models.ALL_TABLES)):
                db.execute(f'DROP TABLE IF EXISTS "{name}"')
        for ddl in models.iter_ddl():
            db.execute(ddl)
        stats["tables"] = len(models.ALL_TABLES)
        existing = {r["rule_id"] for r in db.fetch_all("SELECT rule_id FROM risk_rule")}
        for rule in PRESET_RULES:
            if rule["rule_id"] in existing:
                continue
            db.insert("risk_rule", dict(rule))
            stats["rules"] += 1
    logger.info("数据库初始化完成: %s", stats)
    return stats
