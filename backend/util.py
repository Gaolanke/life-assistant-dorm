"""通用工具：时间、密码、请求指纹、异常。"""
from __future__ import annotations

import os
import re
import secrets
from datetime import date, datetime, timedelta
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from fastapi import Request

from . import config

TZ = ZoneInfo(config.TIMEZONE)


class AppError(Exception):
    """业务异常，会被转换成 JSON 错误响应。"""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# --------------------------------------------------------------------------
# 时间
# --------------------------------------------------------------------------
def now_local() -> datetime:
    """当前本地时间（去掉时区信息，方便存 SQLite）。"""
    return datetime.now(TZ).replace(tzinfo=None, microsecond=0)


def today() -> date:
    return now_local().date()


def from_timestamp(value: float) -> datetime:
    """时间戳转本地（无时区）时间。"""
    return datetime.fromtimestamp(value, TZ).replace(tzinfo=None, microsecond=0)


def parse_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value or "").strip()
    if not text:
        raise AppError("日期不能为空")
    text = text.replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-")
    text = re.sub(r"\s+.*$", "", text)
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%y-%m-%d", "%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if fmt == "%m-%d":
            parsed = parsed.replace(year=today().year)
        return parsed.date()
    raise AppError(f"无法识别的日期格式：{value}")


def date_range(start: date, end: date) -> Iterable[date]:
    cursor = start
    while cursor <= end:
        yield cursor
        cursor += timedelta(days=1)


def fmt_dt(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


def fmt_date(value: date | None) -> str:
    return value.strftime("%Y-%m-%d") if value else ""


def human_gap(value: datetime | None) -> str:
    """输出“3 分钟前”这种相对时间。"""
    if not value:
        return "从未"
    delta = now_local() - value
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "刚刚"
    if seconds < 60:
        return f"{seconds} 秒前"
    if seconds < 3600:
        return f"{seconds // 60} 分钟前"
    if seconds < 86400:
        return f"{seconds // 3600} 小时前"
    return f"{seconds // 86400} 天前"


# --------------------------------------------------------------------------
# 随机串
# --------------------------------------------------------------------------
def random_token(length: int = 24) -> str:
    return secrets.token_urlsafe(length)


# --------------------------------------------------------------------------
# 请求来源
# --------------------------------------------------------------------------
def client_ip(request: Request) -> str:
    for header in ("cf-connecting-ip", "x-real-ip"):
        value = request.headers.get(header)
        if value:
            return value.strip()
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def device_label(user_agent: str) -> str:
    """把 User-Agent 变成一行人类可读的设备描述（系统 · 浏览器）。"""
    raw = (user_agent or "").strip()
    if not raw:
        return ""
    ua = raw.lower()
    system = ""
    for keyword, name in (
        ("windows nt 10", "Windows 10/11"),
        ("windows", "Windows"),
        ("android", "Android"),
        ("iphone", "iPhone"),
        ("ipad", "iPad"),
        ("harmony", "HarmonyOS"),
        ("mac os x", "macOS"),
        ("linux", "Linux"),
    ):
        if keyword in ua:
            system = name
            break
    app = ""
    for keyword, name in (
        ("micromessenger", "微信"),
        ("qqbrowser", "QQ浏览器"),
        ("edg/", "Edge"),
        ("chrome/", "Chrome"),
        ("firefox/", "Firefox"),
        ("safari/", "Safari"),
        ("curl/", "curl"),
        ("python-httpx", "httpx"),
    ):
        if keyword in ua:
            app = name
            break
    return " · ".join(part for part in (system, app) if part) or raw[:60]


def client_device(request: Request) -> str:
    """请求来源设备（用于日志与填报溯源）。"""
    return device_label(request.headers.get("user-agent") or "")[:120]


def safe_filename(name: str, fallback: str = "文件") -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", str(name or "")).strip(" ._")
    return name[:80] or fallback


def env_flag(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
