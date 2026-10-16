"""状态查询与寝室长登录（账号体系：管理员走 /api/auth，寝室长走这里）。"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..models import Account, Dorm
from ..security import (
    account_to_dict,
    authenticate_leader,
    available_modes,
    clean_name,
    client_context,
    current_account,
    hash_password,
    is_admin_port,
    issue_leader_token,
    leader_dorm_from_request,
    list_leader_accounts,
    request_port,
    require_admin,
)
from ..services import report_service, settings_service as ss
from ..util import AppError, client_device, client_ip, now_local

router = APIRouter(prefix="/api/access", tags=["access"])

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]{3,32}$")
MIN_PASSWORD = 6


class LeaderLoginBody(BaseModel):
    room_no: str = ""
    password: str = ""


class LeaderPasswordBody(BaseModel):
    dorm_id: int
    password: str = ""
    # set = 按填写的密码设定；random = 随机生成一个新密码；clear = 取消密码恢复公开
    # 不传 action 时保持老行为：填了密码就 set，没填就 random
    action: str | None = None


class LeaderActiveBody(BaseModel):
    dorm_id: int
    active: bool


# --------------------------------------------------------------------------
# 状态
# --------------------------------------------------------------------------
@router.get("/status")
def access_status(request: Request, db: Session = Depends(get_db)):
    """当前访问者的状态：端口、登录身份、寝室长身份。"""
    account = current_account(db, request)
    leader_dorm = (
        leader_dorm_from_request(db, request) if request.headers.get("x-leader-token") else None
    )
    return {
        "ok": True,
        "is_admin": bool(account and account.role == "admin" and is_admin_port(request)),
        "account": account_to_dict(account) if account else None,
        "logged_in": account is not None,
        "must_change": bool(account and account.must_change),
        "modes": available_modes(request),
        "admin_port": is_admin_port(request),
        "current_port": request_port(request),
        "main_port": config.PORT,
        "admin_port_number": config.ADMIN_PORT,
        "login_required": True,
        "leader": (
            {
                "dorm_id": leader_dorm.id,
                "room_no": leader_dorm.room_no,
                "room_label": leader_dorm.room_label,
                "leader_name": leader_dorm.leader_name,
            }
            if leader_dorm
            else None
        ),
        "server_time": now_local().strftime("%Y-%m-%d %H:%M:%S"),
    }


# --------------------------------------------------------------------------
# 寝室长登录（用户名=宿舍号；也支持用管理员在"账号管理"里建的寝室长账号）
# --------------------------------------------------------------------------
@router.post("/leader/login")
def leader_login(body: LeaderLoginBody, request: Request, db: Session = Depends(get_db)):
    username = clean_name(body.room_no)[:64]
    password = (body.password or "").strip()

    # 1) 宿舍号 + 验证密码
    dorm, reason = authenticate_leader(db, username, password)
    if dorm is not None:
        ss.write_audit(
            db,
            actor=dorm.leader_name or dorm.room_no,
            role="leader",
            action="寝室长登录",
            target=dorm.room_no,
            detail="宿舍号 + 验证密码",
            ip=client_ip(request),
        )
        db.commit()
        return {
            "ok": True,
            "token": issue_leader_token(dorm),
            "dorm": {
                "dorm_id": dorm.id,
                "room_no": dorm.room_no,
                "room_label": dorm.room_label,
                "leader_name": dorm.leader_name,
                "leader_phone": dorm.leader_phone,
            },
            "message": f"登录成功，已进入 {dorm.room_no}",
        }

    raise AppError(reason or "登录失败", 403)


@router.get("/leader/me")
def leader_me(request: Request, db: Session = Depends(get_db)):
    dorm = leader_dorm_from_request(db, request)
    if dorm is None:
        account = current_account(db, request)
        if account is not None and account.role == "leader" and account.dorm_id:
            dorm = db.get(Dorm, account.dorm_id)
    if dorm is None:
        raise AppError("还没有登录", 403)
    return {
        "ok": True,
        "dorm": {
            "dorm_id": dorm.id,
            "room_no": dorm.room_no,
            "room_label": dorm.room_label,
            "leader_name": dorm.leader_name,
            "leader_phone": dorm.leader_phone,
        },
    }


# --------------------------------------------------------------------------
# 管理员给寝室设身份
# --------------------------------------------------------------------------
@router.post("/leader/password")
def set_leader_password(
    body: LeaderPasswordBody,
    request: Request,
    db: Session = Depends(get_db),
    _: Account = Depends(require_admin),
):
    """管理员给指定寝室设置 / 重置 / 取消验证密码。

    action 取值：
    - `set`    ：用管理员指定的密码
    - `random` ：随机生成一个新的
    - `clear`  ：取消密码，这间寝室恢复「谁都能直接填报」
    """
    import secrets as _secrets

    dorm = db.get(Dorm, body.dorm_id)
    if dorm is None:
        raise AppError("寝室不存在", 404)

    action = (body.action or "").strip().lower()
    raw = (body.password or "").strip()
    if not action:
        action = "set" if raw else "random"

    if action == "clear":
        dorm.leader_password = ""
        for account in list_leader_accounts(db, dorm.id):
            account.active = False
        db.commit()
        ss.write_audit(
            db,
            actor=client_context(request)["display_name"],
            role="admin",
            action="取消寝室验证密码",
            target=dorm.room_no,
            detail="已取消密码，这间寝室恢复公开填报",
            ip=client_ip(request),
        )
        db.commit()
        return {
            "ok": True,
            "room_no": dorm.room_no,
            "password": "",
            "action": "clear",
            "generated": False,
            "locked": False,
            "message": f"已取消 {dorm.room_no} 的验证密码，现在任何人都能直接选它填报",
        }

    if action == "set":
        if not raw:
            raise AppError("要设置密码就请填写 6 位以上的密码；想取消密码请点「取消密码」")
        if len(raw) < MIN_PASSWORD:
            raise AppError(f"密码至少 {MIN_PASSWORD} 位")
        if len(raw) > 64:
            raise AppError("密码最多 64 位")
        generated = False
    else:
        raw = f"{_secrets.randbelow(900000) + 100000}"
        generated = True

    dorm.leader_password = hash_password(raw)
    # 如果这间寝室已经有寝室长账号，密码同步过去，两处保持一致
    for account in list_leader_accounts(db, dorm.id):
        account.password_hash = hash_password(raw)
        account.active = True
    db.commit()
    ss.write_audit(
        db,
        actor=client_context(request)["display_name"],
        role="admin",
        action="重置寝室验证密码" if generated else "设置寝室验证密码",
        target=dorm.room_no,
        detail="随机生成" if generated else "管理员指定",
        ip=client_ip(request),
    )
    db.commit()
    return {
        "ok": True,
        "room_no": dorm.room_no,
        "password": raw,
        "action": "random" if generated else "set",
        "generated": generated,
        "locked": True,
        "message": f"{dorm.room_no} 的验证密码：{raw}（账号名就是宿舍号 {dorm.room_no}）",
    }


@router.post("/leader/active")
def toggle_leader_active(
    body: LeaderActiveBody,
    request: Request,
    db: Session = Depends(get_db),
    actor: Account = Depends(require_admin),
):
    """启用 / 停用某间寝室的寝室长身份。"""
    dorm = db.get(Dorm, body.dorm_id)
    if dorm is None:
        raise AppError("寝室不存在", 404)
    linked = list_leader_accounts(db, dorm.id)
    for account in linked:
        account.active = bool(body.active)
    if not linked and body.active and dorm.leader_password:
        pass  # 没有独立账号时，宿舍号+验证密码这条路依然可用
    if not body.active:
        # 停用：连验证密码一起取消，避免"停了还能登"
        dorm.leader_password = ""
    db.commit()
    ss.write_audit(
        db,
        actor=actor.display_name or actor.username,
        role="admin",
        action="启用寝室长账号" if body.active else "停用寝室长账号",
        target=dorm.room_no,
        ip=client_ip(request),
    )
    db.commit()
    return {
        "ok": True,
        "active": bool(body.active),
        "message": f"{dorm.room_no} 的寝室长身份已{'启用' if body.active else '停用'}",
    }


@router.post("/leader/assign")
def assign_leader(
    request: Request,
    dorm_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    actor: Account = Depends(require_admin),
):
    """把某位成员指定为这间寝室的寝室长。"""
    dorm = db.get(Dorm, dorm_id)
    if dorm is None:
        raise AppError("寝室不存在", 404)
    member = report_service.find_member(db, member_id)
    if member is None or member.dorm_id != dorm.id:
        raise AppError("成员不属于这间寝室", 404)

    for other in report_service.dorm_members(db, dorm.id, active_only=False):
        other.role = "宿舍长" if other.id == member.id else "成员"
    dorm.leader_name = member.name
    dorm.leader_phone = member.phone or dorm.leader_phone
    for account in list_leader_accounts(db, dorm.id):
        account.display_name = member.name
    db.commit()
    ss.write_audit(
        db,
        actor=actor.display_name or actor.username,
        role="admin",
        action="指定寝室长",
        target=dorm.room_no,
        detail=f"{member.name}",
        ip=client_ip(request),
    )
    db.commit()
    return {"ok": True, "message": f"已把 {member.name} 设为 {dorm.room_no} 的寝室长"}
