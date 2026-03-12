from __future__ import annotations

import logging
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

class BaseStore:
    """
    SQLite 存储基类，统一管理连接、事务和并发配置。
    提供 WAL 模式支持、事务原子性保证以及连接注入（conn=）模式。
    """

    def __init__(self, db_path: Path, timeout: float = 30.0) -> None:
        self._db_path: Path = db_path
        self._timeout: float = timeout
        self._lock: threading.Lock = threading.Lock()
        self._init_base_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """获取带 WAL 模式和忙时重试的连接。"""
        conn = sqlite3.connect(self._db_path, timeout=self._timeout)
        conn.row_factory = sqlite3.Row
        try:
            # 开启 WAL 模式提升并发读写性能
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            yield conn
        finally:
            conn.close()

    def _init_base_schema(self) -> None:
        """初始化数据库目录并调用子类的建表逻辑。"""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def init_schema(self) -> None:
        """具体的建表逻辑由子类实现。"""
        raise NotImplementedError("Subclasses must implement init_schema()")

    @contextmanager
    def transaction(self, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        """
        统一的事务包装器。
        使用 SQLite 自身的忙时重试机制（timeout=30s）处理并发。
        """
        with self._connect() as conn:
            try:
                if immediate:
                    conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    @contextmanager
    def _tx(self, conn: sqlite3.Connection | None = None) -> Iterator[sqlite3.Connection]:
        """
        便捷的连接/事务注入器。
        如果传入了现有 conn，则复用；否则开启新事务。
        """
        if conn is not None:
            yield conn
            return
        with self.transaction() as tx_conn:
            yield tx_conn

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """简易的单条 SQL 执行工具。"""
        with self._connect() as conn:
            res = conn.execute(sql, params)
            conn.commit()
            return res
