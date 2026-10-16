"""数据库备份：定时自动备份 + 保留最近 N 份。

用 SQLite 官方 backup 接口（不是简单复制文件），
所以 WAL 里还没落盘的数据也不会丢。
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from .. import config
from ..util import now_local

log = logging.getLogger("dorm.backup")

DEFAULT_KEEP = 30


def create_backup(*, keep: int = DEFAULT_KEEP, tag: str = "") -> dict[str, Any]:
    """生成一份数据库备份，并清理过旧的备份。返回 {ok, path, size, message}。"""
    config.ensure_dirs()
    stamp = now_local().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{tag}" if tag else ""
    backup_path = config.BACKUP_DIR / f"app_{stamp}{suffix}.db"

    try:
        if backup_path.exists():
            backup_path.unlink()
        # 先把 WAL 合并进主库，再备份，保证内容是最新的
        source = sqlite3.connect(str(config.DB_PATH))
        try:
            source.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            target = sqlite3.connect(str(backup_path))
            try:
                source.backup(target)
            finally:
                target.close()
        finally:
            source.close()
    except Exception as exc:  # noqa: BLE001
        log.exception("数据库备份失败")
        return {"ok": False, "path": "", "size": 0, "message": f"备份失败：{exc}"}

    size = backup_path.stat().st_size
    removed = cleanup_backups(keep=keep)
    log.info("数据库备份完成：%s（%.1f KB），清理旧备份 %s 份", backup_path.name, size / 1024, removed)
    return {
        "ok": True,
        "path": str(backup_path),
        "name": backup_path.name,
        "size": size,
        "removed": removed,
        "message": f"备份完成：{backup_path.name}（{size / 1024:.1f} KB）",
    }


def list_backups() -> list[dict[str, Any]]:
    """列出所有备份，新的在前。"""
    config.ensure_dirs()
    items: list[dict[str, Any]] = []
    for path in sorted(config.BACKUP_DIR.glob("app_*.db"), reverse=True):
        try:
            stat = path.stat()
        except OSError:
            continue
        items.append(
            {
                "name": path.name,
                "size": stat.st_size,
                "size_text": f"{stat.st_size / 1024:.1f} KB",
                "created_at": now_local().fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "path": str(path),
            }
        )
    return items


def cleanup_backups(keep: int = DEFAULT_KEEP) -> int:
    """只保留最近 keep 份，其余删掉。返回删除数量。"""
    if keep <= 0:
        return 0
    files = sorted(config.BACKUP_DIR.glob("app_*.db"), reverse=True)
    removed = 0
    for path in files[keep:]:
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def backup_path_by_name(name: str) -> Path | None:
    """按文件名找备份（防止路径穿越）。"""
    safe = Path(name).name
    if not safe.startswith("app_") or not safe.endswith(".db"):
        return None
    path = config.BACKUP_DIR / safe
    return path if path.exists() else None
