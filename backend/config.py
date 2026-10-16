"""全局路径与运行配置。

所有可调参数都集中在这里，部署时可以通过环境变量覆盖。
"""
from __future__ import annotations

import os
from pathlib import Path

from . import __version__

BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"
STATIC_DIR = BACKEND_DIR / "static"

# DATA_DIR 允许通过环境变量迁移到别的磁盘，例如 /www/dorm-data
DATA_DIR = Path(os.environ.get("DORM_DATA_DIR", BASE_DIR / "data")).resolve()
DB_PATH = DATA_DIR / "app.db"
EXPORT_DIR = DATA_DIR / "exports"
UPLOAD_DIR = DATA_DIR / "uploads"
BACKUP_DIR = DATA_DIR / "backups"
LOG_DIR = DATA_DIR / "logs"

APP_NAME = os.environ.get("DORM_APP_NAME", "生活助手")
HOST = os.environ.get("DORM_HOST", "0.0.0.0")
# 主端口：同学选寝室填写 + 寝室长界面（公开访问）
PORT = int(os.environ.get("DORM_PORT", "8090"))
# 管理端口：管理员界面（需要设备授权），与主端口分开
ADMIN_PORT = int(os.environ.get("DORM_ADMIN_PORT", "8091"))

# 时间库：所有“今天”的判定都用这个时区
TIMEZONE = os.environ.get("DORM_TIMEZONE", "Asia/Shanghai")

# 会话签名密钥：首次启动会自动写入 data/secret.key
SESSION_COOKIE = "dorm_session"
SESSION_DAYS = 30

# 默认管理员（仅首次初始化数据库时创建）
DEFAULT_ADMIN_USERNAME = os.environ.get("DORM_ADMIN_USER", "admin")
DEFAULT_ADMIN_PASSWORD = os.environ.get("DORM_ADMIN_PASSWORD", "admin123")

DEVICE_STALE_MINUTES = 15  # 已废弃：不再采集设备指纹，仅保留占位

VERSION = __version__


def ensure_dirs() -> None:
    for path in (DATA_DIR, EXPORT_DIR, UPLOAD_DIR, BACKUP_DIR, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)


def secret_key() -> str:
    """会话密钥，持久化到磁盘，重启后登录状态不失效。"""
    ensure_dirs()
    key_file = DATA_DIR / "secret.key"
    if key_file.exists():
        value = key_file.read_text(encoding="utf-8").strip()
        if value:
            return value
    import secrets

    value = secrets.token_urlsafe(48)
    key_file.write_text(value, encoding="utf-8")
    return value
