"""访问上下文与权限校验。

本系统的访问分成三条线：

1. **普通访问（默认）**：任何人打开网页 → 选自己的寝室 → 填写。不需要账号。
2. **寝室长验证**：每个寝室可以设一个账号（登录名 = 宿舍号）与密码。
   寝室长验证后，填报表单会固定到自己的寝室，也可以改本寝室成员。
3. **管理员设备授权**：管理页面（宿舍与人员、提醒推送、系统配置、控制台）
   只有被授权的设备能打开。第一个设备用「控制台安装码」激活，之后由管理员
   在控制台生成一次性访问码给其他设备使用。

这里只做身份识别与门禁判断，具体规则由各路由调用。
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from contextvars import ContextVar
from typing import Any
from urllib.parse import unquote

from fastapi import Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from itsdangerous import URLSafeTimedSerializer

from . import config
from .database import get_db
from .models import Account, Dorm
from .util import client_device, client_ip, now_local

ANONYMOUS = "匿名填报"
MAX_NAME_LEN = 40
SESSION_DAYS = config.SESSION_DAYS

# 当前请求的设备描述（由中间件写入，日志写入时读取）
_current_device: ContextVar[str] = ContextVar("dorm_current_device", default="")


def set_current_device(value: str) -> None:
    _current_device.set(value or "")


def current_device() -> str:
    return _current_device.get()

LEADER_SESSION_DAYS = 120

ROLE_PUBLIC = "public"
ROLE_LEADER = "leader"
ROLE_ADMIN = "admin"


# --------------------------------------------------------------------------
# 名称与基础上下文
# --------------------------------------------------------------------------
def clean_name(value: Any) -> str:
    """规范化提交人名称（自动处理 URL 编码）。"""
    text = str(value or "").strip()
    if "%" in text:
        try:
            decoded = unquote(text, encoding="utf-8", errors="strict")
        except Exception:  # noqa: BLE001
            decoded = text
        if decoded.strip():
            text = decoded.strip()
    text = text.replace("\n", " ").replace("\r", " ")
    return text[:MAX_NAME_LEN]


def client_context(request: Request) -> dict[str, Any]:
    """当前访问者上下文：只描述“谁在操作”，权限另算。"""
    name = clean_name(request.headers.get("x-client-name")) or ANONYMOUS
    return {
        "display_name": name,
        "is_anonymous": name == ANONYMOUS,
        "ip": client_ip(request),
        "time": now_local().strftime("%Y-%m-%d %H:%M:%S"),
    }


def submitter_from(request: Request, body_name: str = "") -> str:
    """填报人：请求体里写的名字优先，其次请求头，最后匿名。"""
    return clean_name(body_name) or client_context(request)["display_name"]


# --------------------------------------------------------------------------
# 端口分流：主端口只服务公开页面，管理端口才提供管理接口
# --------------------------------------------------------------------------
# 只允许在管理端口访问的接口前缀
ADMIN_API_PREFIXES = (
    "/api/access/code",
    "/api/access/devices",
    "/api/access/leader/accounts",
    "/api/access/leader/password",
    "/api/access/leader/assign",
    "/api/access/leader/active",
    "/api/logs",  # 填写日志 / 操作日志只给管理端
    "/api/accounts",  # 账号管理
    "/api/classes",  # 班级管理
    "/api/fund",  # 班费
)
# 这些接口虽然公开页面也要用，但只有管理端口允许“写”
ADMIN_WRITE_RULES = (
    ("/api/settings", ("PUT", "POST", "DELETE")),
    ("/api/dorms", ("POST", "PUT", "DELETE", "PATCH")),
    ("/api/members", ("POST", "PUT", "DELETE", "PATCH")),
    ("/api/jobs", ("POST",)),
    ("/api/system/reset-data", ("POST",)),
)

# 这些写操作在公开端口也放行，具体能不能改由「寝室有没有设密码」决定
# （见 assert_dorm_access：没设密码的寝室谁都能改，设了密码的必须寝室长登录）
PUBLIC_WRITE_EXCEPTIONS = (
    ("PUT", "/api/members"),
)
# 管理页面（前端路由）
ADMIN_PAGES = ("dorms", "push", "config", "console")


def request_port(request: Request) -> int:
    """请求打到的是哪个端口（优先 Host 头里的端口，其次服务端 socket）。"""
    host = request.headers.get("host", "")
    if ":" in host:
        tail = host.rsplit(":", 1)[-1]
        if tail.isdigit():
            return int(tail)
    server = request.scope.get("server") or ("", 0)
    try:
        return int(server[1])
    except (TypeError, ValueError, IndexError):
        return 0


def is_admin_port(request: Request) -> bool:
    from . import config

    port = request_port(request)
    if port in (0, config.PORT):
        return False
    return port == config.ADMIN_PORT


def is_admin_only_request(method: str, path: str) -> bool:
    """这个请求是不是只能从管理端口进来。"""
    if path.startswith(ADMIN_API_PREFIXES):
        return True
    if path.startswith("/api/access/devices"):
        return True
    upper = (method or "GET").upper()
    for allowed_method, prefix in PUBLIC_WRITE_EXCEPTIONS:
        if upper == allowed_method and (
            path == prefix or path.startswith(prefix + "/") or path.startswith(prefix + "?")
        ):
            return False
    for prefix, methods in ADMIN_WRITE_RULES:
        if path == prefix or path.startswith(prefix + "/") or path.startswith(prefix + "?"):
            if upper in methods:
                return True
    return False


def available_modes(request: Request) -> list[str]:
    """当前端口支持哪些界面。"""
    if is_admin_port(request):
        return ["admin"]
    return ["public", "leader"]


# --------------------------------------------------------------------------
# 令牌与密码
# --------------------------------------------------------------------------
def new_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def token_hash(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    """PBKDF2-SHA256，格式 pbkdf2$迭代次数$盐$散列。"""
    if not password:
        raise ValueError("密码不能为空")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000).hex()
    return f"pbkdf2$200000${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    if not stored or not password:
        return False
    if stored.startswith("pbkdf2$"):
        try:
            _, iterations, salt, digest = stored.split("$", 3)
            calc = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations)
            ).hex()
        except Exception:  # noqa: BLE001
            return False
        return hmac.compare_digest(calc, digest)
    return hmac.compare_digest(password, stored)


def new_access_code() -> str:
    """人类好念的 6 位数字（用于自动生成初始密码）。"""
    return f"{secrets.randbelow(900000) + 100000}"


# --------------------------------------------------------------------------
# 账号会话（管理员 / 寝室长登录）
# --------------------------------------------------------------------------
SESSION_COOKIE = "dorm_session"


def _signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(config.secret_key(), salt="dorm-account-session")


def issue_session(account: Account) -> str:
    return _signer().dumps(
        {"uid": account.id, "username": account.username, "role": account.role, "dorm_id": account.dorm_id}
    )


def parse_session(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    try:
        return _signer().loads(token, max_age=SESSION_DAYS * 86400)
    except Exception:  # noqa: BLE001
        return None


def request_session_token(request: Request) -> str:
    """会话令牌：请求头优先（前端方便），其次 Cookie。"""
    return (
        request.headers.get("x-session-token")
        or request.cookies.get(SESSION_COOKIE)
        or ""
    ).strip()


def current_account(db: Session, request: Request) -> Account | None:
    """当前登录账号（没登录或已停用就返回 None）。"""
    payload = parse_session(request_session_token(request))
    if not payload or not payload.get("uid"):
        return None
    account = db.get(Account, int(payload["uid"]))
    if account is None or not account.active:
        return None
    return account


def find_account(db: Session, username: str) -> Account | None:
    name = (username or "").strip()
    if not name:
        return None
    account = db.execute(
        select(Account).where(func.lower(Account.username) == name.lower())
    ).scalar_one_or_none()
    return account


def authenticate_account(db: Session, username: str, password: str) -> tuple[Account | None, str]:
    """账号密码登录。返回 (账号, 错误说明)。"""
    name = (username or "").strip()
    if not name:
        return None, "请填写用户名"
    if not password:
        return None, "请填写密码"
    account = find_account(db, name)
    if account is None:
        return None, "用户名或密码不正确"
    if not account.active:
        return None, "这个账号已被停用，请联系管理员"
    if not account.password_hash or not verify_password(password, account.password_hash):
        return None, "用户名或密码不正确"
    return account, ""


def require_admin(request: Request, db: Session = Depends(get_db)) -> Account:
    """管理端门禁：必须用管理员账号登录。"""
    account = current_account(db, request)
    if account is None:
        raise HTTPException(
            status_code=401,
            detail="请先用管理员账号登录管理端",
        )
    if account.role != "admin":
        raise HTTPException(status_code=403, detail="这个账号不是管理员，没有管理权限")
    return account


def require_login(request: Request, db: Session = Depends(get_db)) -> Account:
    """任意已登录账号（管理员或寝室长）。"""
    account = current_account(db, request)
    if account is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return account


def account_to_dict(account: Account, *, dorm: Dorm | None = None) -> dict[str, Any]:
    return {
        "id": account.id,
        "username": account.username,
        "display_name": account.display_name,
        "role": account.role,
        "role_text": "管理员" if account.role == "admin" else "寝室长",
        "dorm_id": account.dorm_id,
        "dorm_label": (dorm.room_label if dorm else "") or "",
        "phone": account.phone,
        "note": account.note,
        "active": account.active,
        "is_owner": account.is_owner,
        "must_change": account.must_change,
        "last_login_at": account.last_login_at.strftime("%Y-%m-%d %H:%M:%S") if account.last_login_at else "",
        "last_login_ip": account.last_login_ip,
        "last_login_device": account.last_login_device,
        "created_at": account.created_at.strftime("%Y-%m-%d %H:%M:%S") if account.created_at else "",
    }


def list_leader_accounts(db: Session, dorm_id: int) -> list[Account]:
    """某间寝室绑定的寝室长账号。"""
    return list(
        db.execute(
            select(Account).where(Account.role == "leader", Account.dorm_id == dorm_id)
        ).scalars()
    )


def ensure_owner_account(db: Session) -> tuple[Account, str]:
    """确保有一个可登录的超级管理员，并返回**一个确定能用的密码**。

    返回 (账号, 可用的初始密码)。已有账号时，如果 admin_code 里的密码已经
    登录不上了（例如管理员自己改过密码），会把密码重置回 admin_code 并返回它，
    保证安装脚本打印出来的密码一定是能用的。
    """
    from .services import settings_service as ss

    owner = db.execute(
        select(Account).where(Account.role == "admin").order_by(Account.id)
    ).scalars().first()

    if owner is not None:
        owner.is_owner = True
        owner.active = True
        known = (ss.get_setting(db, "admin_code") or "").strip()
        if known and verify_password(known, owner.password_hash):
            db.commit()
            return owner, ""  # 密码没变，调用方用 admin_code 即可
        if not known:
            known = new_access_code()
            ss.set_setting(db, "admin_code", known)
        owner.password_hash = hash_password(known)
        db.commit()
        return owner, known

    raw = (ss.get_setting(db, "admin_code") or "").strip() or new_access_code()
    ss.set_setting(db, "admin_code", raw)
    owner = Account(
        username="admin",
        display_name="生活委员",
        password_hash=hash_password(raw),
        role="admin",
        is_owner=True,
        must_change=False,
        note="超级管理员（安装时自动创建）",
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)
    return owner, raw


# --------------------------------------------------------------------------
# 寝室长验证
# --------------------------------------------------------------------------
def find_dorm_by_login(db: Session, username: str) -> Dorm | None:
    """登录名就是宿舍号（容错：去掉楼栋前缀也试一次）。"""
    username = (username or "").strip()
    if not username:
        return None
    dorm = db.execute(select(Dorm).where(Dorm.room_no == username)).scalar_one_or_none()
    if dorm:
        return dorm
    tail = username.split("-")[-1].split("号")[-1].strip()
    if tail and tail != username:
        dorm = db.execute(select(Dorm).where(Dorm.room_no == tail)).scalar_one_or_none()
    return dorm


def authenticate_leader(db: Session, username: str, password: str) -> tuple[Dorm | None, str]:
    """寝室长验证。返回 (寝室, 错误说明)。

    密码是**可选**的：
      - 没设密码：返回 None + 提示，但这个人照样能在公开页面正常填报自己的寝室
      - 设了密码：密码正确才返回寝室
    """
    dorm = find_dorm_by_login(db, username)
    if dorm is None:
        return None, "没有找到这个宿舍号，请检查是否输入正确（例如 6-213）"
    if not dorm.leader_password:
        return None, "这间寝室还没有设置验证密码，直接选寝室填写即可；需要寝室长界面的话请让管理员在控制台设置密码"
    if not verify_password(password, dorm.leader_password):
        return None, "密码不正确（忘记密码请让管理员在「管理控制台」重置）"
    return dorm, ""


def _leader_serializer():
    from itsdangerous import URLSafeTimedSerializer

    from . import config

    return URLSafeTimedSerializer(config.secret_key(), salt="dorm-leader")


def issue_leader_token(dorm: Dorm) -> str:
    """签发寝室长通行令牌（签名 + 过期时间，服务器无需存会话）。"""
    return _leader_serializer().dumps({"dorm_id": dorm.id, "room_no": dorm.room_no})


def leader_dorm_from_request(db: Session, request: Request) -> Dorm | None:
    """从请求头 X-Leader-Token 解析寝室长身份。"""
    token = (request.headers.get("x-leader-token") or "").strip()
    if not token:
        return None
    from itsdangerous import BadSignature, SignatureExpired

    try:
        data = _leader_serializer().loads(token, max_age=LEADER_SESSION_DAYS * 86400)
    except (BadSignature, SignatureExpired):
        return None
    except Exception:  # noqa: BLE001
        return None
    dorm_id = int(data.get("dorm_id") or 0)
    if not dorm_id:
        return None
    return db.get(Dorm, dorm_id)


def require_leader(db: Session, request: Request) -> Dorm:
    dorm = leader_dorm_from_request(db, request)
    if dorm is None:
        raise HTTPException(status_code=403, detail="请先用寝室长账号验证后再操作")
    return dorm


def dorm_locked(dorm: Dorm) -> bool:
    """这间寝室是否已经设置了验证密码（设置后就要凭寝室长账户操作）。"""
    return bool(dorm and dorm.leader_password)


def assert_dorm_access(db: Session, request: Request, dorm: Dorm, what: str = "操作") -> None:
    """写操作的统一门禁：

    - 管理端口：**只有管理员账号**才始终放行（管理员能看到全部、改全部）
    - 公开端口：没设密码的寝室任何人都能{what}；设了密码的寝室必须用该寝室的寝室长账号登录

    注意：这里必须校验 role == "admin"。以前只判断"是否已登录"，
    结果寝室长账号只要在管理端口登录，就能改任意宿舍——已修复。
    """
    account = current_account(db, request)
    if is_admin_port(request) and account is not None and account.role == "admin":
        return
    if not dorm_locked(dorm):
        return
    leader_dorm = leader_dorm_from_request(db, request)
    if leader_dorm is None or leader_dorm.id != dorm.id:
        raise HTTPException(
            status_code=403,
            detail=f"{dorm.room_no} 已由寝室长设置密码，{what}需要先用该寝室的寝室长账号登录"
            "（入口页 →「我是寝室长（登录）」）",
        )


def can_write_dorm(db: Session, request: Request, dorm: Dorm) -> bool:
    """前端用来判断当前身份能不能写这间寝室。"""
    account = current_account(db, request)
    if is_admin_port(request) and account is not None and account.role == "admin":
        return True
    if not dorm_locked(dorm):
        return True
    leader_dorm = leader_dorm_from_request(db, request)
    return bool(leader_dorm and leader_dorm.id == dorm.id)
