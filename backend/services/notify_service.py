"""消息推送：QQ 官方机器人（QQ 开放平台）。"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Dorm, PushLog
from ..util import now_local
from . import report_service, settings_service as ss


# --------------------------------------------------------------------------
# 文本生成
# --------------------------------------------------------------------------
def _truncate(text: str, limit: int = 1800) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n…（内容过长已省略）"


def dorm_lines(db: Session, day: date, max_rooms: int = 60, class_id: int = 0) -> str:
    """逐宿舍明细文本。"""
    tpl = ss.get_setting(db, "tpl_absent_dorm")
    rows = report_service.dorm_day_rows(db, day, class_id)
    lines: list[str] = []
    for row in rows:
        if not row["reported"]:
            lines.append(f"❓ {row['room_no']}：未填报")
            continue
        if row["absent_count"] <= 0:
            lines.append(f"✅ {row['room_no']}：齐全 {row['total_count']} 人")
            continue
        reason_text = f"（{row['note']}）" if row["note"] else ""
        lines.append(
            ss.render_template(
                tpl,
                {
                    "dorm": row["room_no"],
                    "absent_count": row["absent_count"],
                    "absent_names": row["absent_names"] or "未说明",
                    "reason_text": reason_text,
                    "note": row["note"],
                },
            )
        )
    if len(lines) > max_rooms:
        lines = lines[:max_rooms] + [f"…还有 {len(lines) - max_rooms} 间宿舍未展示"]
    return "\n".join(lines) if lines else "（没有宿舍数据）"


def build_group_report(db: Session, day: date | None = None, class_id: int = 0) -> str:
    """每晚 QQ 群汇报文本（class_id>0 时只汇总该班级）。"""
    day = day or now_local().date()
    stats = report_service.day_stats(db, day, class_id)
    variables = ss.base_vars(db, day, class_id)
    variables.update(
        {
            "dorm_total": stats["dorm_total"],
            "reported": stats["reported"],
            "unreported": stats["unreported"],
            "present": stats["present"],
            "total": stats["total"],
            "absent": stats["absent"],
            "dorm_lines": dorm_lines(db, day, class_id=class_id),
            "missing": "、".join(stats["missing_rooms"]) or "无",
            "time": now_local().strftime("%H:%M"),
        }
    )
    return _truncate(ss.render_template(ss.get_setting(db, "tpl_group_report"), variables), 2000)


def build_missing_reminder(db: Session, day: date | None = None, class_id: int = 0) -> str:
    """未填报宿舍提醒文本（QQ 官方机器人使用）。"""
    day = day or now_local().date()
    missing = report_service.missing_dorms(db, day, class_id)
    if missing:
        lines = "\n".join(
            f"{index + 1}. {d.room_no}" + (f"（宿舍长：{d.leader_name}）" if d.leader_name else "")
            for index, d in enumerate(missing)
        )
    else:
        lines = "（全部已填报，辛苦了）"
    return (
        f"【填报提醒】{day.strftime('%Y-%m-%d')}\n"
        f"还有 {len(missing)} 间宿舍未填报：\n"
        f"{lines}"
    )


def build_dorm_pending(db: Session, dorm: Dorm, day: date | None = None) -> str:
    day = day or now_local().date()
    variables = ss.base_vars(db, day, dorm.class_id)
    variables.update({"dorm": dorm.room_no, "dorm_name": dorm.room_no})
    return ss.render_template(ss.get_setting(db, "tpl_dorm_pending"), variables)


# --------------------------------------------------------------------------
# 日志
# --------------------------------------------------------------------------
def log_push(
    db: Session,
    *,
    channel: str,
    scene: str,
    target: str,
    title: str,
    content: str,
    status: str,
    detail: str = "",
    trigger: str = "auto",
    ip: str = "",
    user_agent: str = "",
    class_id: int = 0,
) -> PushLog:
    from ..security import current_device

    row = PushLog(
        class_id=int(class_id or 0),
        channel=channel,
        scene=scene,
        target=str(target)[:120],
        title=title[:200],
        content=content,
        status=status,
        detail=detail[:2000],
        trigger=trigger,
        ip=ip[:64],
        user_agent=(user_agent or current_device() or "")[:300],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def serialize_log(row: PushLog) -> dict[str, Any]:
    channel_text = {
        "qqbot": "QQ 官方机器人",
        "smtp": "邮件",
        "onebot": "QQ 群（OneBot）",
        "showdoc": "ShowDoc/Webhook",
        "none": "未发出",
    }.get(row.channel, row.channel or "未知")
    return {
        "id": row.id,
        "class_id": row.class_id or 0,
        "channel": row.channel,
        "channel_text": channel_text,
        "scene": row.scene,
        "scene_text": {
            "daily_report": "每晚汇报",
            "fill_remind": "填报提醒",
            "custom_remind": "定时提醒",
            "missing_reminder": "未填报提醒",
            "fund_report": "班费发群",
            "test": "测试推送",
            "dorm_pending": "单宿舍催填",
        }.get(row.scene, row.scene),
        "target": row.target,
        "title": row.title,
        "content": row.content,
        "status": row.status,
        "detail": row.detail,
        "trigger": "手动" if row.trigger == "manual" else "自动",
        "created_at": row.created_at.strftime("%Y-%m-%d %H:%M:%S") if row.created_at else "",
    }


def _auto_sent_today(db: Session, scene: str, title: str, class_id: int = 0) -> bool:
    """今天这个场景这条内容是不是已经成功发过了（自动任务防重复通报用）。

    只挡「自动」触发：手动点按钮永远允许重发。
    判断依据是推送日志——同一天、同班级、同场景、同标题、且成功，就视为已发过。
    """
    today_start = now_local().replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = (
        select(PushLog.id)
        .where(PushLog.scene == scene)
        .where(PushLog.title == title)
        .where(PushLog.status == "success")
        .where(PushLog.created_at >= today_start)
    )
    if class_id:
        stmt = stmt.where(PushLog.class_id == int(class_id))
    stmt = stmt.limit(1)
    return db.execute(stmt).first() is not None


def recent_logs(db: Session, limit: int = 40, channel: str | None = None) -> list[dict[str, Any]]:
    stmt = select(PushLog).order_by(PushLog.id.desc()).limit(limit)
    if channel:
        stmt = select(PushLog).where(PushLog.channel == channel).order_by(PushLog.id.desc()).limit(limit)
    return [serialize_log(row) for row in db.execute(stmt).scalars()]


# --------------------------------------------------------------------------
# 投递通道（QQ 官方机器人，推送目标按班级解析）
# --------------------------------------------------------------------------
def class_targets(db: Session, class_id: int = 0, explicit: str = "") -> list[str]:
    """一次推送要发到哪些群。

    优先级：显式指定 > 班级绑定的群（BotGroup.class_id）> 全局推送群（qqbot_groups）。

    防串班：只要有任何一个班级绑定了群，按班级的推送就不再回退全局群列表
    （否则没绑群的班级会把消息发进别班的群里）；没绑群的班级返回空，
    上层会优雅跳过并提示去「班级管理」绑定群。
    """
    parts = [p.strip() for p in str(explicit or "").replace("，", ",").split(",") if p.strip()]
    if parts:
        return parts
    if int(class_id or 0) > 0:
        from . import class_service

        bound = class_service.class_group_openids(db, int(class_id))
        if bound:
            return bound
        if class_service.any_class_has_bound_group(db):
            return []
    return _split_setting(ss.get_setting(db, "qqbot_groups"))


def _split_setting(value: str) -> list[str]:
    return [p.strip() for p in str(value or "").replace("，", ",").split(",") if p.strip()]


def _new_channel_ready(db: Session, class_id: int = 0) -> bool:
    """通道是否可用：QQ 官方机器人配好、且有可发的目标群。"""
    return bool(
        ss.get_bool(db, "qqbot_enabled", False)
        and class_targets(db, class_id)
    )


async def _deliver_via_new_channel(
    db: Session,
    *,
    title: str,
    content: str,
    scene: str,
    trigger: str = "auto",
    class_id: int = 0,
    group_openid: str = "",
) -> dict[str, Any]:
    """把消息投递到 QQ 官方机器人，并记一条推送日志。"""
    from . import push_service

    targets = class_targets(db, class_id, group_openid)
    result = await push_service.deliver_notification(
        db,
        title=title,
        content=content,
        scene=scene,
        group_openid=",".join(targets),
    )
    log_push(
        db,
        channel=result.get("channel", "none"),
        scene=scene,
        target=",".join(targets),
        title=title,
        content=content,
        status="success" if result.get("ok") else "failed",
        detail=result.get("message", ""),
        trigger=trigger,
        class_id=class_id,
    )
    return result



# --------------------------------------------------------------------------
# 群汇报 / 未填报提醒（统一走 QQ 官方机器人）
# --------------------------------------------------------------------------
async def send_group_report(
    db: Session,
    day: date | None = None,
    *,
    trigger: str = "auto",
    class_id: int = 0,
) -> dict[str, Any]:
    """向 QQ 群发送当晚汇报（QQ 官方机器人，按班级发到各自绑定的群）。

    只保留 QQ 官方机器人通道：没配好时优雅跳过并记一条日志，不抛异常。
    """
    day = day or now_local().date()
    title = f"{day.strftime('%Y-%m-%d')} 填报汇总"

    if not _new_channel_ready(db, class_id):
        message = "QQ 官方机器人未配置好（去「系统配置 → QQ 官方机器人」填好开关和群 openid，或在「班级管理」里给班级绑定群）"
        if trigger != "manual":
            return {"ok": False, "skipped": True, "message": message}
        log_push(
            db,
            channel="none",
            scene="daily_report",
            target="",
            title=title,
            content="",
            status="failed",
            detail=message,
            trigger=trigger,
            class_id=class_id,
        )
        return {"ok": False, "channel": "none", "message": message}

    # 防重复通报：今天自动汇报已经成功发过一次就直接跳过
    # （任务 misfire 补跑、服务重启补跑等都不会再发第二遍；手动发送不受限）
    if trigger == "auto" and _auto_sent_today(db, "daily_report", title, class_id):
        return {"ok": True, "skipped": True, "message": "今天的汇报已成功发送过，自动任务跳过重复发送"}
    content = build_group_report(db, day, class_id)
    result = await _deliver_via_new_channel(
        db,
        title=title,
        content=content,
        scene="daily_report",
        trigger=trigger,
        class_id=class_id,
    )
    result["content"] = content
    return result



def build_fill_reminder(db: Session, day: date | None = None, class_id: int = 0) -> str:
    """拼出「填报提醒」的正文（不发送），供预览和发送共用。"""
    day = day or now_local().date()
    site = public_site_url(db)
    mention = "@everyone\n" if ss.get_bool(db, "fill_remind_mention_all", True) else ""

    template = ss.get_setting(db, "tpl_fill_remind").strip()
    if not template:
        template = "{mention}【寝室情况填报提醒】{date}\n请尽快到 {site} 填报寝室情况。"
    return (
        template.replace("{mention}", mention)
        .replace("{site}", site)
        .replace("{deadline}", "")
        .replace("{date}", day.strftime("%Y-%m-%d"))
    )


async def send_fill_reminder(
    db: Session,
    *,
    trigger: str = "auto",
    class_id: int = 0,
) -> dict[str, Any]:
    """每晚定时提醒各寝室长填报「寝室情况」，消息里带填报网址，可选 @所有人。

    和 send_missing_reminder 的区别：
      - 这个是在**截止前**发的「请大家来填」的提醒，内容固定（网址 + 要求）
      - missing_reminder 是**截止后**针对没填的宿舍逐一催填
    """
    if trigger == "auto" and not ss.get_bool(db, "fill_remind_enabled", True):
        return {"ok": False, "skipped": True, "message": "填报提醒定时任务未启用"}

    day = now_local().date()
    content = build_fill_reminder(db, day, class_id)

    title = f"{day.strftime('%Y-%m-%d')} 寝室情况填报提醒"
    result = await _deliver_via_new_channel(
        db,
        title=title,
        content=content,
        scene="fill_remind",
        trigger=trigger,
        class_id=class_id,
    )
    result["content"] = content
    result["site"] = public_site_url(db)
    result["mention_all"] = ss.get_bool(db, "fill_remind_mention_all", True)
    return result


def public_site_url(db: Session) -> str:
    """公开端网址：优先用设置里的，留空则退回内置域名。"""
    url = ss.get_setting(db, "site_public_url").strip().rstrip("/")
    if not url:
        url = "https://xiaoaiyun.top"
    return url


# --------------------------------------------------------------------------
# 定时提醒（多条，用户在「提醒推送」页自由增删改，模板可一键选用预设）
# --------------------------------------------------------------------------
def build_custom_reminder(
    db: Session,
    reminder: dict[str, Any],
    day: date | None = None,
    class_id: int = 0,
) -> str:
    """渲染一条定时提醒的正文（class_id>0 时统计数据只看该班级）。

    可用变量：{date} {time} {weekday} {school} {class_name} {commissary}
              {site} 公开端网址、{mention} @所有人（这条提醒开了才有）
              {missing} {missing_list} {missing_count} {dorm_total} {reported} {unreported}
    """
    day = day or now_local().date()
    missing = report_service.missing_dorms(db, day, class_id)
    variables = ss.base_vars(db, day, class_id)
    variables.update(
        {
            "site": public_site_url(db),
            "mention": "@everyone\n" if reminder.get("mention_all") else "",
            "missing_count": len(missing),
            "missing_list": "\n".join(
                f"{index + 1}. {d.room_no}" + (f"（宿舍长：{d.leader_name}）" if d.leader_name else "")
                for index, d in enumerate(missing)
            )
            or "（全部已填报，辛苦了）",
            "missing": "、".join(d.room_no for d in missing) or "无",
            "dorm_total": len(report_service.list_dorms(db, class_id=class_id)),
            "reported": len(report_service.list_dorms(db, class_id=class_id)) - len(missing),
            "unreported": len(missing),
        }
    )
    return _truncate(ss.render_template(str(reminder.get("content") or ""), variables))


async def send_custom_reminder(
    db: Session,
    reminder: dict[str, Any],
    *,
    trigger: str = "auto",
    class_id: int = 0,
) -> dict[str, Any]:
    """发送一条定时提醒（QQ 官方机器人），记推送日志。"""
    name = str(reminder.get("name") or "定时提醒")
    if trigger == "auto" and not reminder.get("enabled", True):
        return {"ok": False, "skipped": True, "message": f"提醒「{name}」已停用"}

    day = now_local().date()
    title = f"{day.strftime('%Y-%m-%d')} {name}"
    # 自动触发防重：今天这条提醒发成功过就不再发第二遍（按班级区分）
    if trigger == "auto" and _auto_sent_today(db, "custom_remind", title, class_id):
        return {"ok": True, "skipped": True, "message": f"提醒「{name}」今天已发送过，自动任务跳过重复发送"}

    content = build_custom_reminder(db, reminder, day, class_id)
    result = await _deliver_via_new_channel(
        db,
        title=title,
        content=content,
        scene="custom_remind",
        trigger=trigger,
        class_id=class_id,
    )
    result["content"] = content
    result["reminder_id"] = reminder.get("id", "")
    result["name"] = name
    return result


async def send_missing_reminder(
    db: Session,
    day: date | None = None,
    *,
    trigger: str = "auto",
    class_id: int = 0,
) -> dict[str, Any]:
    """提醒还没填报的宿舍长（QQ 官方机器人）。

    没配好时优雅跳过并记一条日志，不抛异常。
    """
    day = day or now_local().date()
    if trigger == "auto" and not _new_channel_ready(db, class_id):
        return {"ok": False, "skipped": True, "message": "定时提醒未启用"}

    content = build_missing_reminder(db, day, class_id)
    result = await _deliver_via_new_channel(
        db,
        title=f"{day.strftime('%Y-%m-%d')} 未填报提醒",
        content=content,
        scene="missing_reminder",
        trigger=trigger,
        class_id=class_id,
    )
    result["content"] = content
    result["missing"] = [d.room_no for d in report_service.missing_dorms(db, day, class_id)]
    return result
