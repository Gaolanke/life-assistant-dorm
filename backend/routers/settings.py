"""系统配置、消息模板、机器人对接、定时任务、推送日志。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import scheduler as sched
from ..database import get_db
from ..security import client_context, is_admin_port, require_admin
from ..services import class_service, notify_service, push_service, report_service, settings_service as ss
from ..util import AppError, client_ip, now_local, parse_date

router = APIRouter(prefix="/api", tags=["settings"])


class SettingsBody(BaseModel):
    values: dict[str, Any] = {}
    reschedule: bool = True


class TestBody(BaseModel):
    kind: str = "qqbot"  # qqbot / notify / preview
    group_id: str = ""
    message: str = ""
    day: str = ""
    class_id: int = 0


# 公开端（8090）允许读到的配置：都是展示/功能参数，不含任何密钥
PUBLIC_SETTING_KEYS = {
    "school_name",
    "class_name",
    "commissary_name",
    "teacher_name",
    "app_display_name",
    "qq_report_time",
    "auto_export_time",
    "absence_reasons",
    "site_notice",
}

# 这些是密钥类配置，公开端一律不返回（管理端才返回，页面上也会打码显示）
SECRET_SETTING_KEYS = {
    "qqbot_secret",
}


@router.get("/settings")
def get_settings(request: Request, db: Session = Depends(get_db)):
    """读配置。

    公开端口：只返回 PUBLIC_SETTING_KEYS 里的安全字段，密钥一律不返回。
    管理端口：由端口中间件保证必须是管理员登录，返回全部配置。

    （以前这个接口在公开端口会明文返回 qqbot_secret，
      属于严重泄露，已修复。）
    """
    rows = ss.setting_rows(db)
    admin_side = is_admin_port(request)

    values: dict[str, str] = {}
    meta: list[dict[str, str]] = []
    for row in rows:
        if row.key in SECRET_SETTING_KEYS and not admin_side:
            continue
        if not admin_side and row.key not in PUBLIC_SETTING_KEYS:
            continue
        values[row.key] = row.value
        if admin_side:
            meta.append(
                {
                    "key": row.key,
                    "group": row.group,
                    "description": row.description,
                }
            )

    return {
        "ok": True,
        "values": values,
        "meta": meta,
        "template_vars": ss.template_vars_doc() if admin_side else [],
        "jobs": sched.job_status() if admin_side else [],
        "server_time": now_local().strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.put("/settings")
def put_settings(
    body: SettingsBody,
    request: Request,
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    if not body.values:
        raise AppError("没有要保存的内容")
    ss.update_settings(db, body.values)

    # 改了 QQ 机器人凭证（AppID / AppSecret / 开关）就立刻重连长连接，
    # 这样用户换机器人后不用重启服务。
    if any(
        k in body.values
        for k in ("qqbot_app_id", "qqbot_secret", "qqbot_ws_enabled", "qqbot_enabled")
    ):
        try:
            from ..services import qqbot_gateway

            qqbot_gateway.reconnect_soon(SessionLocal)
        except Exception:  # noqa: BLE001
            pass

    if body.reschedule:
        # 时间类配置改了要重新装载定时任务
        if any(key in body.values for key in ("qq_report_time", "auto_export_time", "reminders")):
            try:
                sched.reload_schedule()
            except Exception:  # noqa: BLE001
                pass
    ss.write_audit(
        db,
        actor=client_context(request)["display_name"],
        role="public",
        action="修改系统配置",
        detail="、".join(body.values.keys())[:500],
        ip=client_ip(request),
    )
    db.commit()
    return {"ok": True, "message": "配置已保存并立即生效", "values": ss.all_settings(db), "jobs": sched.job_status()}


@router.post("/settings/test")
async def test_push(
    body: TestBody,
    request: Request,
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    day = parse_date(body.day) if body.day else now_local().date()
    if body.kind == "preview":
        return {
            "ok": True,
            "group_report": notify_service.build_group_report(db, day),
            "reminder": notify_service.build_missing_reminder(db, day),
        }
    if body.kind == "qqbot":
        group = body.group_id.strip()
        if not group:
            return await push_service.check_qqbot(db)
        content = body.message.strip() or notify_service.build_group_report(db, day)
        result = await push_service.send_group_message(db, group, content)
        return {**result, "content": content}
    if body.kind == "notify":
        # 「提醒推送」页的「立即发送到 QQ 群」：按当前班级出内容、发到该班绑定的群
        cid = class_service.resolve_class_id(db, body.class_id)
        if body.message.strip():
            content = body.message.strip()
            result = await push_service.deliver_notification(
                db,
                title=f"{day.strftime('%Y-%m-%d')} 填报通知（测试）",
                content=content,
                scene="test",
                group_openid=",".join(notify_service.class_targets(db, cid, body.group_id)),
            )
            return {**result, "content": content}
        result = await notify_service.send_group_report(db, day, trigger="manual", class_id=cid)
        return result
    raise AppError("未知的测试类型")


@router.get("/push/status")
async def push_channel_status(
    db: Session = Depends(get_db),
    class_id: int = 0,
    _: Account = Depends(require_admin),
):
    """推送通道状态：只反映 QQ 官方机器人；发送目标按当前班级解析。"""
    from ..services import qqbot_gateway

    task = qqbot_gateway.GATEWAY_TASK
    running = bool(task is not None and not task.done())
    enabled = ss.get_bool(db, "qqbot_enabled", False)
    groups = (ss.get_setting(db, "qqbot_groups") or "").strip()
    cid = class_service.resolve_class_id(db, class_id)
    targets = notify_service.class_targets(db, cid) if enabled else []
    cls = class_service.get_class(db, cid)

    if not enabled:
        message = "QQ 官方机器人推送还没开启（去「系统配置 → QQ 官方机器人」打开）"
    elif not targets:
        message = "这个班级还没绑定群（去「班级管理」下方把机器人所在的群绑定到该班级）"
    elif running:
        message = "长连接在线，可以发群消息"
    else:
        message = "长连接未运行，正在自动重连（看服务日志）"

    return {
        "ok": bool(enabled and targets and running),
        "message": message,
        "channel": "QQ 官方机器人",
        "enabled": enabled,
        "class_id": cid,
        "class_name": cls.name if cls else "",
        "targets": targets,
        "gateway_running": running,
        "qqbot": {"enabled": enabled, "gateway_running": running, "groups": groups},
    }


# --------------------------------------------------------------------------
# 定时提醒（多条，可自由增删改；预设模板一键选用）
# --------------------------------------------------------------------------
class RemindersBody(BaseModel):
    items: list[dict[str, Any]] = []
    class_id: int = 0


class ReminderRenderBody(BaseModel):
    content: str = ""
    mention_all: bool = False
    class_id: int = 0


@router.get("/reminders")
def list_reminders(
    db: Session = Depends(get_db),
    class_id: int = 0,
    _: dict = Depends(require_admin),
):
    """定时提醒列表 + 可选预设模板 + 定时任务状态（按班级独立）。"""
    cid = class_service.resolve_class_id(db, class_id)
    return {
        "ok": True,
        "class_id": cid,
        "items": ss.get_reminders(db, class_id=cid),
        "presets": ss.reminder_presets(),
        "jobs": sched.job_status(),
    }


@router.put("/reminders")
def save_reminders(
    body: RemindersBody,
    request: Request,
    db: Session = Depends(get_db),
    account: Account = Depends(require_admin),
):
    """整体保存提醒列表（增/删/改都走这里），保存后立即重排定时任务。"""
    cid = class_service.resolve_class_id(db, body.class_id)
    text = ss.normalize_reminders(body.items)
    ss.set_setting(db, ss.class_key(cid, "reminders"), text)
    ss.write_audit(
        db,
        actor=account.display_name or account.username,
        role="admin",
        action="保存定时提醒",
        detail=f"共 {len(body.items)} 条",
        ip=client_ip(request),
    )
    db.commit()
    try:
        sched.reload_schedule()
    except Exception:  # noqa: BLE001
        pass
    return {
        "ok": True,
        "message": "提醒已保存，定时任务已更新",
        "items": ss.get_reminders(db, class_id=cid),
        "jobs": sched.job_status(),
    }


@router.post("/reminders/{reminder_id}/send")
async def send_reminder_now(
    reminder_id: str,
    request: Request,
    db: Session = Depends(get_db),
    account: Account = Depends(require_admin),
    class_id: int = 0,
):
    """立即发送某一条提醒（手动触发，不受「今日已发」限制）。"""
    cid = class_service.resolve_class_id(db, class_id)
    reminder = next(
        (item for item in ss.get_reminders(db, class_id=cid) if str(item.get("id")) == reminder_id),
        None,
    )
    if reminder is None:
        raise AppError("这条提醒不存在（可能已被删除）", 404)
    result = await notify_service.send_custom_reminder(db, reminder, trigger="manual", class_id=cid)
    ss.write_audit(
        db,
        actor=account.display_name or account.username,
        role="admin",
        action="手动发送定时提醒",
        target=str(reminder.get("name") or ""),
        detail=str(result.get("message") or result.get("ok")),
        ip=client_ip(request),
    )
    db.commit()
    return result


@router.post("/reminders/render")
def render_reminder(
    body: ReminderRenderBody,
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    """预览一段提醒内容渲染后的效果（不发送）。"""
    cid = class_service.resolve_class_id(db, body.class_id)
    rendered = notify_service.build_custom_reminder(
        db,
        {"name": "预览", "content": body.content, "mention_all": body.mention_all},
        class_id=cid,
    )
    return {"ok": True, "rendered": rendered}


@router.post("/jobs/{job_id}/run")
async def run_job(
    job_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    result = await sched.run_job_now(job_id)
    ss.write_audit(
        db,
        actor=client_context(request)["display_name"],
        role="public",
        action=f"立即执行任务 {job_id}",
        detail=str(result.get("message") or result.get("ok")),
        ip=client_ip(request),
    )
    db.commit()
    return result


@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db), _: dict = Depends(require_admin)):
    return {"ok": True, "jobs": sched.job_status(), "server_time": now_local().strftime("%Y-%m-%d %H:%M:%S")}


@router.get("/logs/push")
def push_logs(
    db: Session = Depends(get_db),
    limit: int = 40,
    channel: str | None = None,
    _: dict = Depends(require_admin),
):
    return {"ok": True, "items": notify_service.recent_logs(db, max(1, min(limit, 200)), channel)}


@router.get("/audit")
def audit_logs(
    request: Request,
    db: Session = Depends(get_db),
    limit: int = 100,
    _: dict = Depends(require_admin),
):
    """用户操作日志（谁、什么时候、在哪台设备、什么 IP 做了什么）。"""
    return {"ok": True, "items": audit_items(db, limit)}


def audit_items(db: Session, limit: int = 100) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from ..models import AuditLog
    from ..util import device_label

    rows = db.execute(
        select(AuditLog).order_by(AuditLog.id.desc()).limit(max(1, min(limit, 1000)))
    ).scalars()
    return [
        {
            "id": row.id,
            "actor": row.actor,
            "role": row.role,
            "action": row.action,
            "target": row.target,
            "detail": row.detail,
            "ip": row.ip,
            "user_agent": row.user_agent,
            "device": device_label(row.user_agent),
            "created_at": row.created_at.strftime("%Y-%m-%d %H:%M:%S") if row.created_at else "",
        }
        for row in rows
    ]


@router.get("/logs/audit")
def audit_logs_alias(
    request: Request,
    db: Session = Depends(get_db),
    limit: int = 200,
    _: dict = Depends(require_admin),
):
    return {"ok": True, "items": audit_items(db, limit)}


@router.get("/logs/submissions")
def submission_logs(
    request: Request,
    db: Session = Depends(get_db),
    limit: int = 200,
    class_id: int = 0,
    _: dict = Depends(require_admin),
):
    """用户填写日志：谁在什么时间、用什么设备、从哪个 IP 提交了填报。"""
    from sqlalchemy import select, or_

    from ..models import Report

    cid = class_service.resolve_class_id(db, class_id)
    # 只取“有填写来源信息”的记录：要么是老数据（没记 IP），要么按时间倒序取最近的
    rows = db.execute(
        select(Report)
        .order_by(Report.submitted_at.desc(), Report.id.desc())
        .limit(max(1, min(limit, 1000)))
    ).scalars()
    dorms = {
        dorm.id: dorm
        for dorm in report_service.list_dorms(db, active_only=False, class_id=cid)
    }
    items = []
    for row in rows:
        dorm = dorms.get(row.dorm_id)
        if dorm is None:
            continue  # 其他班级的记录
        serialized = report_service.serialize_report(row, dorm)
        items.append(
            {
                "id": row.id,
                "room_no": dorm.room_no if dorm else "",
                "room_label": dorm.room_label if dorm else "",
                "report_date": row.report_date.strftime("%Y-%m-%d"),
                "is_complete": row.is_complete,
                "absent_names": row.absent_names,
                "note": row.note,
                "submitter": row.submitter,
                "source_text": serialized["source_text"],
                "submitted_at": serialized["submitted_at"],
                "ip": row.ip,
                "device": serialized["device"],
                "device_raw": row.user_agent,
                "raw_message": row.raw_message,
            }
        )
    with_source = [item for item in items if item["ip"] or item["device"]]
    return {
        "ok": True,
        "items": items,
        "total": len(items),
        "with_source": len(with_source),
        "note": "" if with_source else "还没有记录到来源信息；之前的历史数据没有 IP/设备，新提交的都会记录",
    }
