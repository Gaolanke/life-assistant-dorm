"""scripts/ 下测试脚本共用的登录工具（账号登录 + 会话令牌）。

程序从「设备授权」改成「账号密码登录」以后，所有管理接口都要带
``X-Session-Token``。为了让测试脚本可以反复运行、不依赖「当前密码是什么」，
这里在登录前会把管理员账号的密码重置成一个已知值（只改数据库里的账号记录，
不动 backend/ 的代码）。

用法::

    from auth_client import ensure_admin_client, public_client, ADMIN_BASE, PUBLIC_BASE

    admin = ensure_admin_client()      # 重置 admin 密码 → 登录 → 带好令牌的客户端
    public = public_client()           # 公开端口（8090），没有登录身份

环境变量（都可以不设，有默认值）：

* ``DORM_TEST_ADMIN``     管理端口地址，默认 http://127.0.0.1:8091
* ``DORM_TEST_PUBLIC``    公开端口地址，默认 http://127.0.0.1:8090
* ``DORM_TEST_ADMIN_USER`` 管理员用户名，默认 admin
* ``DORM_TEST_ADMIN_PASSWORD`` 测试用密码，默认 testadmin123
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
for _path in (str(ROOT), str(ROOT / "scripts")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:  # 对齐服务的数据目录（服务的 DORM_DATA_DIR 写在 systemd 单元里）
    import server_env  # noqa: F401
except Exception:  # noqa: BLE001
    server_env = None  # type: ignore[assignment]

PUBLIC_BASE = os.environ.get("DORM_TEST_PUBLIC", "http://127.0.0.1:8090")
ADMIN_BASE = os.environ.get("DORM_TEST_ADMIN", "http://127.0.0.1:8091")

TEST_ADMIN_USER = os.environ.get("DORM_TEST_ADMIN_USER", "admin")
TEST_ADMIN_PASSWORD = os.environ.get("DORM_TEST_ADMIN_PASSWORD", "testadmin123")


def db_data_dir() -> str:
    """脚本将要读写的数据库所在目录（方便判断是不是打到了同一个服务）。"""
    try:
        from backend import config

        return str(config.DB_PATH)
    except Exception:  # noqa: BLE001
        return str(ROOT / "data" / "app.db")


def reset_admin_password(
    password: str = TEST_ADMIN_PASSWORD, username: str = TEST_ADMIN_USER
) -> str:
    """把管理员的登录密码重置成已知值，返回该密码。

    只写 ``accounts`` 表；账号记录本身不新增也不删除（除非真的一个管理员都没有）。
    """
    from sqlalchemy import select

    from backend.database import SessionLocal, init_db
    from backend.models import Account
    from backend.security import ensure_owner_account, hash_password
    from backend.services import settings_service as ss

    init_db()
    db = SessionLocal()
    try:
        ss.ensure_settings(db)
        account = db.execute(
            select(Account).where(Account.username == username)
        ).scalar_one_or_none()
        if account is None:
            # 用户名对不上时，退而求其次：保证系统里至少有一个超级管理员
            ensure_owner_account(db)
            account = db.execute(
                select(Account).where(Account.username == username)
            ).scalar_one_or_none()
        if account is None:
            account = Account(
                username=username,
                display_name=username,
                password_hash=hash_password(password),
                role="admin",
                active=True,
                must_change=False,
            )
            db.add(account)
        account.password_hash = hash_password(password)
        account.active = True
        account.must_change = False
        db.commit()
        return password
    finally:
        db.close()


def login(
    base: str = ADMIN_BASE,
    username: str = TEST_ADMIN_USER,
    password: str = TEST_ADMIN_PASSWORD,
    timeout: float = 40.0,
    **client_kwargs,
) -> tuple[httpx.Client, str, dict]:
    """登录并返回 ``(带令牌的客户端, token, account)``；失败抛 RuntimeError。"""
    client = httpx.Client(
        base_url=base, timeout=timeout, follow_redirects=True, **client_kwargs
    )
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    data: dict = {}
    try:
        data = response.json()
    except Exception:  # noqa: BLE001
        data = {}
    if response.status_code != 200 or not data.get("ok"):
        client.close()
        raise RuntimeError(
            f"管理员登录失败（{base}）：HTTP {response.status_code} {response.text[:200]}\n"
            f"数据库：{db_data_dir()}\n"
            "请确认服务已在跑，且脚本读到的 data/app.db 就是服务用的那个。"
        )
    token = data.get("token") or ""
    client.headers["X-Session-Token"] = token
    return client, token, data.get("account") or {}


def ensure_admin_client(
    base: str = ADMIN_BASE, password: str = TEST_ADMIN_PASSWORD, **kwargs
) -> httpx.Client:
    """重置 admin 密码后登录，返回带 ``X-Session-Token`` 的客户端。"""
    reset_admin_password(password, kwargs.pop("username", TEST_ADMIN_USER))
    client, _token, _account = login(base=base, password=password, **kwargs)
    return client


def try_login(
    base: str = ADMIN_BASE, username: str = "", password: str = "", timeout: float = 40.0
) -> tuple[int, dict]:
    """失败也不抛异常的登录（用于「密码错了要 403」这类反向检查）。"""
    with httpx.Client(base_url=base, timeout=timeout, follow_redirects=True) as client:
        response = client.post(
            "/api/auth/login", json={"username": username, "password": password}
        )
        try:
            data = response.json()
        except Exception:  # noqa: BLE001
            data = {}
        return response.status_code, data


def public_client(base: str = PUBLIC_BASE, **kwargs) -> httpx.Client:
    """公开端口客户端（游客身份，没有任何令牌）。"""
    kwargs.setdefault("timeout", 40.0)
    kwargs.setdefault("follow_redirects", True)
    return httpx.Client(base_url=base, **kwargs)
