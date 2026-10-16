"""数据库引擎与会话。"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from . import config
from .models import Base

log = logging.getLogger("dorm.db")

config.ensure_dirs()

# SQLite 是本地文件数据库，建立连接的开销极小。
# 用 NullPool（不池化）可以彻底避免连接池耗尽：
# 发消息最长要重试 4 次、耗时约 2 分钟，如果池化会长时间占住连接，
# 一旦并发稍高就会报 "QueuePool limit ... reached"，进而拖垮后台长连接任务。
engine = create_engine(
    f"sqlite:///{config.DB_PATH.as_posix()}",
    connect_args={
        "check_same_thread": False,
        "timeout": 30,          # 写锁等待 30 秒，避免 "database is locked"
    },
    poolclass=NullPool,          # 不池化：每个会话独立连接，用完即关
    future=True,
)


@event.listens_for(engine, "connect")
def _sqlite_pragma(dbapi_connection, _record):  # pragma: no cover - 驱动回调
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(engine)
    _migrate()
    log.info("数据库已就绪：%s", config.DB_PATH)


# 老库升级：补齐后加的列（SQLite 不支持自动加列）
NEW_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "reports": [("ip", "VARCHAR(64) DEFAULT ''"), ("user_agent", "VARCHAR(300) DEFAULT ''")],
    "audit_logs": [("user_agent", "VARCHAR(300) DEFAULT ''")],
    "push_logs": [
        ("ip", "VARCHAR(64) DEFAULT ''"),
        ("user_agent", "VARCHAR(300) DEFAULT ''"),
    ],
    "accounts": [
        ("is_owner", "BOOLEAN DEFAULT 0"),
        ("must_change", "BOOLEAN DEFAULT 0"),
        ("last_login_device", "VARCHAR(300) DEFAULT ''"),
    ],
    "dorms": [
        ("leader_password", "VARCHAR(200) DEFAULT ''"),
        ("room_label", "VARCHAR(120) DEFAULT ''"),
        ("class_id", "INTEGER DEFAULT 0"),
    ],
    "fund_settings": [("class_id", "INTEGER DEFAULT 0")],
    "fund_entries": [("class_id", "INTEGER DEFAULT 0")],
    "bot_groups": [("class_id", "INTEGER DEFAULT 0")],
    "push_logs": [
        ("ip", "VARCHAR(64) DEFAULT ''"),
        ("user_agent", "VARCHAR(300) DEFAULT ''"),
        ("class_id", "INTEGER DEFAULT 0"),
    ],
}


def _drop_room_unique_index(connection) -> None:
    """多班级后宿舍号只在班级内唯一：把 dorms.room_no 上的全局唯一索引换成普通索引。

    老库的 room_no 列带 unique 约束（索引 ix_dorms_room_no），不删掉的话
    两个班级出现同号宿舍（比如都是 207）会插入失败。
    """
    indexes = connection.execute("PRAGMA index_list(dorms)").fetchall()
    for row in indexes:
        index_name = row[1]
        unique = row[2]
        columns = [r[2] for r in connection.execute(f"PRAGMA index_info({index_name})").fetchall()]
        if unique and columns == ["room_no"]:
            connection.execute(f"DROP INDEX IF EXISTS {index_name}")
            log.warning("数据库升级：dorms.room_no 的全局唯一索引 %s 已移除（多班级允许同号宿舍）", index_name)
    connection.execute("CREATE INDEX IF NOT EXISTS ix_dorms_room_no ON dorms (room_no)")


def _migrate() -> None:
    """给老数据库补列，幂等，可以反复执行。"""
    import sqlite3

    connection = sqlite3.connect(str(config.DB_PATH))
    try:
        existing_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for table, columns in NEW_COLUMNS.items():
            existing = {
                row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if not existing:
                continue
            for name, definition in columns:
                if name in existing:
                    continue
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
                log.warning("数据库升级：%s 增加列 %s", table, name)
        if "dorms" in existing_tables:
            _drop_room_unique_index(connection)
        connection.commit()
    finally:
        connection.close()


def get_db() -> Iterator[Session]:
    """FastAPI 依赖。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """后台任务/脚本用的事务上下文。"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
