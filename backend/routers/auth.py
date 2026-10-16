"""登录、登出、账号管理（管理员账号 + 寝室长账号）。"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..models import Account, Dorm
from ..security import (
    SESSION_COOKIE,
    SESSION_DAYS,
    account_to_dict,
    authenticate_account,
    current_account,
    find_account,
    hash_password,
    is_admin_port,
    issue_session,
    require_admin,
    require_login,
    verify_password,
)
from ..services import report_service, settings_service as ss
from ..util import AppError, client_device, client_ip, now_local

router = APIRouter(tags=["auth"])

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]{3,32}$")
MIN_PASSWORD = 6


class LoginBody(BaseModel):
    username: str = ""
    password: str = ""
    remember: bool = True


class PasswordBody(BaseModel):
    old_password: str = ""
    new_password: str = ""


class AccountBody(BaseModel):
    username: str = ""
    password: str = ""
    display_name: str = ""
    role: str = "admin"  # admin / leader
    dorm_id: int = 0
    room_no: str = ""
    phone: str = ""
    note: str = ""
    active: bool = True


class AccountPatch(BaseModel):
    display_name: str | None = None
    phone: str | None = None
    note: str | None = None
    active: bool | None = None
    dorm_id: int | None = None
    room_no: str | None = None


class ResetPasswordBody(BaseModel):
    new_password: str = ""  # 留空 = 随机生成一个


def _check_password(password: str) -> str:
    value = (password or "").strip()
    if len(value) < MIN_PASSWORD:
        raise AppError(f"密码至少 {MIN_PASSWORD} 位")
    if len(value) > 64:
        raise AppError("密码最多 64 位")
    return value


def _random_password() -> str:
    import secrets as _secrets

    return f"{_secrets.randbelow(900000) + 100000}"


def _set_session_cookie(response, token: str, request: Request) -> None:
    from fastapi import Response

    if isinstance(response, Response):
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=SESSION_DAYS * 86400,
            httponly=True,
            samesite="lax",
        )


# --------------------------------------------------------------------------
# 登录 / 登出
# --------------------------------------------------------------------------
@router.post("/api/auth/login")
def login(body: LoginBody, request: Request, db: Session = Depends(get_db)):
    account, reason = authenticate_account(db, body.username, body.password)
    if account is None:
        raise AppError(reason or "登录失败", 403)

    # 管理端口只允许管理员账号登录。
    # 这样寝室长账号即使在管理端地址输入正确密码，也拿不到管理端会话，
    # 从根上避免"学生登录后进管理员面板"。
    if is_admin_port(request) and account.role != "admin":
        ss.write_audit(
            db,
            actor=account.display_name or account.username,
            role=account.role,
            action="登录被拒",
            target=account.username,
            detail="寝室长账号尝试登录管理端，已拒绝",
            ip=client_ip(request),
            user_agent=client_device(request),
        )
        db.commit()
        raise AppError(
            "这是寝室长账号，不能登录管理端。请到填报端登录："
            f"http://{request.url.hostname or ''}:{config.PORT}",
            403,
        )

    account.last_login_at = now_local()
    account.last_login_ip = client_ip(request)
    account.last_login_device = client_device(request)
    db.commit()
    ss.write_audit(
        db,
        actor=account.display_name or account.username,
        role=account.role,
        action="登录",
        target=account.username,
        detail=f"{account.role_text if hasattr(account, 'role_text') else account.role} 登录成功",
        ip=client_ip(request),
        user_agent=client_device(request),
    )
    db.commit()

    token = issue_session(account)
    dorm = db.get(Dorm, account.dorm_id) if account.dorm_id else None
    from fastapi.responses import JSONResponse

    response = JSONResponse(
        {
            "ok": True,
            "token": token,
            "account": account_to_dict(account, dorm=dorm),
            "message": f"欢迎回来，{account.display_name or account.username}",
        }
    )
    response.set_cookie(
        SESSION_COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax"
    )
    return response


@router.post("/api/auth/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    account = current_account(db, request)
    if account is not None:
        ss.write_audit(
            db,
            actor=account.display_name or account.username,
            role=account.role,
            action="退出登录",
            target=account.username,
            ip=client_ip(request),
        )
        db.commit()
    from fastapi.responses import JSONResponse

    response = JSONResponse({"ok": True, "message": "已退出登录"})
    response.delete_cookie(SESSION_COOKIE)
    return response


@router.get("/api/auth/me")
def me(request: Request, db: Session = Depends(get_db)):
    account = current_account(db, request)
    if account is None:
        return {"ok": True, "logged_in": False, "account": None}
    dorm = db.get(Dorm, account.dorm_id) if account.dorm_id else None
    return {"ok": True, "logged_in": True, "account": account_to_dict(account, dorm=dorm)}


@router.post("/api/auth/password")
def change_my_password(
    body: PasswordBody,
    request: Request,
    db: Session = Depends(get_db),
    account: Account = Depends(require_login),
):
    """修改自己的密码（管理员和寝室长都能用）。"""
    if account.password_hash and not verify_password(body.old_password, account.password_hash):
        raise AppError("原密码不正确", 403)
    new_password = _check_password(body.new_password)
    if account.password_hash and verify_password(new_password, account.password_hash):
        raise AppError("新密码不能和原密码一样")
    account.password_hash = hash_password(new_password)
    account.must_change = False
    db.commit()
    ss.write_audit(
        db,
        actor=account.display_name or account.username,
        role=account.role,
        action="修改密码",
        target=account.username,
        ip=client_ip(request),
    )
    db.commit()
    return {"ok": True, "message": "密码已修改，下次请用新密码登录"}


# --------------------------------------------------------------------------
# 账号管理（管理员）
# --------------------------------------------------------------------------
PERMISSION_DENIED = "只有管理员能管理账号"


def _resolve_dorm(db: Session, *, dorm_id: int = 0, room_no: str = "") -> Dorm | None:
    if dorm_id:
        dorm = db.get(Dorm, dorm_id)
        if dorm is None:
            raise AppError("指定的寝室不存在", 404)
        return dorm
    room = (room_no or "").strip()
    if not room:
        return None
    from ..security import find_dorm_by_login

    dorm = find_dorm_by_login(db, room)
    if dorm is None:
        raise AppError(f"没有找到宿舍号 {room}", 404)
    return dorm


@router.get("/api/accounts")
def list_accounts(
    request: Request,
    db: Session = Depends(get_db),
    role: str | None = None,
    keyword: str = "",
    _: Account = Depends(require_admin),
):
    query = select(Account).order_by(Account.role, Account.username)
    if role in ("admin", "leader"):
        query = query.where(Account.role == role)
    rows = list(db.execute(query).scalars())
    key = (keyword or "").strip().lower()
    dorms = {dorm.id: dorm for dorm in report_service.list_dorms(db, active_only=False)}
    items = []
    for account in rows:
        data = account_to_dict(account, dorm=dorms.get(account.dorm_id))
        if key and key not in f"{account.username}{account.display_name}{account.phone}{data['dorm_label']}".lower():
            continue
        items.append(data)
    return {
        "ok": True,
        "items": items,
        "total": len(items),
        "admin_count": sum(1 for a in rows if a.role == "admin"),
        "leader_count": sum(1 for a in rows if a.role == "leader"),
        "active_count": sum(1 for a in rows if a.active),
    }


@router.post("/api/accounts")
def create_account(
    body: AccountBody,
    request: Request,
    db: Session = Depends(get_db),
    actor: Account = Depends(require_admin),
):
    role = (body.role or "admin").strip().lower()
    if role not in ("admin", "leader"):
        raise AppError("角色只能是 admin（管理员）或 leader（寝室长）")

    dorm = _resolve_dorm(db, dorm_id=body.dorm_id, room_no=body.room_no)
    username = (body.username or "").strip()
    if role == "leader" and not username and dorm is not None:
        username = dorm.room_no
    if not USERNAME_PATTERN.match(username):
        raise AppError("用户名 3-32 位，只能用字母、数字、下划线、点、短横线")
    if role == "leader" and dorm is None:
        raise AppError("寝室长账号必须绑定一间寝室")

    if find_account(db, username) is not None:
        raise AppError(f"账号 {username} 已经存在")

    raw_password = (body.password or "").strip()
    generated = False
    if not raw_password:
        raw_password = _random_password()
        generated = True
    else:
        raw_password = _check_password(raw_password)

    account = Account(
        username=username,
        display_name=(body.display_name or "").strip() or username,
        password_hash=hash_password(raw_password),
        role=role,
        dorm_id=dorm.id if dorm is not None else 0,
        phone=(body.phone or "").strip(),
        note=(body.note or "").strip(),
        active=bool(body.active),
        must_change=generated,
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    if role == "leader" and dorm is not None:
        # 寝室长账号的密码同时生效为"该寝室的验证密码"，两条路都能登
        dorm.leader_password = hash_password(raw_password)
        if not dorm.leader_name:
            dorm.leader_name = account.display_name
        db.commit()

    ss.write_audit(
        db,
        actor=actor.display_name or actor.username,
        role="admin",
        action="新增账号",
        target=account.username,
        detail=f"{'管理员' if role == 'admin' else '寝室长'}"
        + (f"（{dorm.room_no}）" if dorm is not None else "")
        + ("，随机生成密码" if generated else "，指定密码"),
        ip=client_ip(request),
        user_agent=client_device(request),
    )
    db.commit()
    return {
        "ok": True,
        "account": account_to_dict(account, dorm=dorm),
        "password": raw_password,
        "generated": generated,
        "message": f"账号 {account.username} 已创建"
        + (f"，初始密码：{raw_password}" if generated else ""),
    }


@router.patch("/api/accounts/{account_id}")
def update_account(
    account_id: int,
    body: AccountPatch,
    request: Request,
    db: Session = Depends(get_db),
    actor: Account = Depends(require_admin),
):
    account = db.get(Account, account_id)
    if account is None:
        raise AppError("账号不存在", 404)

    changed: list[str] = []
    if body.display_name is not None:
        account.display_name = body.display_name.strip()[:60] or account.username
        changed.append("名称")
    if body.phone is not None:
        account.phone = body.phone.strip()[:40]
        changed.append("电话")
    if body.note is not None:
        account.note = body.note.strip()[:200]
        changed.append("备注")
    if body.room_no is not None or body.dorm_id is not None:
        dorm = _resolve_dorm(db, dorm_id=body.dorm_id or 0, room_no=body.room_no or "")
        account.dorm_id = dorm.id if dorm is not None else 0
        changed.append("绑定寝室")
    if body.active is not None:
        if account.is_owner and not body.active:
            raise AppError("超级管理员账号不能停用")
        if account.id == actor.id and not body.active:
            raise AppError("不能停用自己正在使用的账号")
        account.active = bool(body.active)
        changed.append("启用" if account.active else "停用")
    db.commit()

    ss.write_audit(
        db,
        actor=actor.display_name or actor.username,
        role="admin",
        action="修改账号",
        target=account.username,
        detail="、".join(changed) or "无变化",
        ip=client_ip(request),
    )
    db.commit()
    dorm = db.get(Dorm, account.dorm_id) if account.dorm_id else None
    return {"ok": True, "account": account_to_dict(account, dorm=dorm), "message": "已保存"}


@router.post("/api/accounts/{account_id}/password")
def reset_account_password(
    account_id: int,
    body: ResetPasswordBody,
    request: Request,
    db: Session = Depends(get_db),
    actor: Account = Depends(require_admin),
):
    """管理员给某个账号重置密码（留空则随机生成一个）。"""
    account = db.get(Account, account_id)
    if account is None:
        raise AppError("账号不存在", 404)

    raw = (body.new_password or "").strip()
    generated = False
    if not raw:
        raw = _random_password()
        generated = True
    else:
        raw = _check_password(raw)

    account.password_hash = hash_password(raw)
    account.must_change = generated
    db.commit()

    dorm = db.get(Dorm, account.dorm_id) if account.dorm_id else None
    if dorm is not None:
        # 同步成该寝室的验证密码，保证两处一致
        dorm.leader_password = hash_password(raw)
        db.commit()

    ss.write_audit(
        db,
        actor=actor.display_name or actor.username,
        role="admin",
        action="重置账号密码",
        target=account.username,
        detail="随机生成" if generated else "管理员指定",
        ip=client_ip(request),
    )
    db.commit()
    return {
        "ok": True,
        "account": account_to_dict(account, dorm=dorm),
        "password": raw,
        "generated": generated,
        "message": f"{account.username} 的新密码：{raw}",
    }


@router.delete("/api/accounts/{account_id}")
def delete_account(
    account_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: Account = Depends(require_admin),
):
    account = db.get(Account, account_id)
    if account is None:
        raise AppError("账号不存在", 404)
    if account.is_owner:
        raise AppError("超级管理员账号不能删除")
    if account.id == actor.id:
        raise AppError("不能删除自己正在使用的账号")

    dorm = db.get(Dorm, account.dorm_id) if account.dorm_id else None
    if dorm is not None:
        # 账号删了，这间寝室恢复"谁都能直接填报"
        dorm.leader_password = ""
    username = account.username
    db.delete(account)
    db.commit()

    ss.write_audit(
        db,
        actor=actor.display_name or actor.username,
        role="admin",
        action="删除账号",
        target=username,
        detail=f"同时取消了 {dorm.room_no} 的密码" if dorm is not None else "",
        ip=client_ip(request),
    )
    db.commit()
    return {"ok": True, "message": f"账号 {username} 已删除"}


@router.get("/api/accounts/stats")
def account_stats(
    request: Request,
    db: Session = Depends(get_db),
    _: Account = Depends(require_admin),
):
    total = db.execute(select(func.count()).select_from(Account)).scalar() or 0
    admins = db.execute(
        select(func.count()).select_from(Account).where(Account.role == "admin")
    ).scalar() or 0
    leaders = db.execute(
        select(func.count()).select_from(Account).where(Account.role == "leader")
    ).scalar() or 0
    active = db.execute(
        select(func.count()).select_from(Account).where(Account.active.is_(True))
    ).scalar() or 0
    dorms = report_service.list_dorms(db, active_only=False)
    with_password = [dorm for dorm in dorms if dorm.leader_password]
    unlinked = [dorm for dorm in dorms if not any(
        row.dorm_id == dorm.id for row in db.execute(select(Account).where(Account.role == "leader")).scalars()
    )]
    return {
        "ok": True,
        "total": total,
        "admins": admins,
        "leaders": leaders,
        "active": active,
        "dorm_total": len(dorms),
        "dorm_with_password": len(with_password),
        "dorm_without_account": len(unlinked),
    }


@router.post("/api/accounts/batch-leader")
def batch_create_leader_accounts(
    request: Request,
    db: Session = Depends(get_db),
    actor: Account = Depends(require_admin),
    only_missing: bool = True,
):
    """给寝室批量建寝室长账号（用户名 = 宿舍号，密码随机生成）。"""
    dorms = report_service.list_dorms(db, active_only=False)
    existing = {
        row.dorm_id
        for row in db.execute(select(Account).where(Account.role == "leader")).scalars()
    }
    created: list[dict[str, str]] = []
    for dorm in dorms:
        if only_missing and dorm.id in existing:
            continue
        account = find_account(db, dorm.room_no)
        raw = _random_password()
        if account is None:
            account = Account(
                username=dorm.room_no,
                display_name=dorm.leader_name or dorm.room_no,
                password_hash=hash_password(raw),
                role="leader",
                dorm_id=dorm.id,
                must_change=True,
                note="批量创建",
            )
            db.add(account)
        else:
            account.password_hash = hash_password(raw)
            account.role = "leader"
            account.dorm_id = dorm.id
        dorm.leader_password = hash_password(raw)
        db.commit()
        created.append({"room_no": dorm.room_no, "username": account.username, "password": raw})

    ss.write_audit(
        db,
        actor=actor.display_name or actor.username,
        role="admin",
        action="批量创建寝室长账号",
        detail=f"新建 {len(created)} 个",
        ip=client_ip(request),
    )
    db.commit()
    return {"ok": True, "items": created, "total": len(created), "message": f"已创建 {len(created)} 个寝室长账号"}


# --------------------------------------------------------------------------
# 寝室长账号（控制台里的"寝室长验证密码"）
# --------------------------------------------------------------------------
@router.get("/api/access/leader/accounts")
def leader_accounts(
    request: Request,
    db: Session = Depends(get_db),
    _: Account = Depends(require_admin),
):
    """控制台：所有寝室的寝室长账号状态。"""
    dorms = report_service.list_dorms(db, active_only=False)
    accounts = {
        row.dorm_id: row
        for row in db.execute(select(Account).where(Account.role == "leader")).scalars()
    }
    items = []
    for dorm in dorms:
        account = accounts.get(dorm.id)
        items.append(
            {
                "dorm_id": dorm.id,
                "room_no": dorm.room_no,
                "room_label": dorm.room_label,
                "building": dorm.building,
                "leader_name": dorm.leader_name,
                "leader_phone": dorm.leader_phone,
                "member_count": len(report_service.dorm_members(db, dorm.id)),
                "has_password": bool(dorm.leader_password),
                "locked": bool(dorm.leader_password),
                "active": dorm.active,
                "account_id": account.id if account else 0,
                "account_username": account.username if account else dorm.room_no,
                "account_active": bool(account.active) if account else True,
                "has_account": account is not None,
            }
        )
    return {
        "ok": True,
        "items": items,
        "with_password": sum(1 for dorm in dorms if dorm.leader_password),
        "with_account": len(accounts),
        "total": len(dorms),
    }
