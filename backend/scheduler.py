"""定时任务：每晚汇报、未填报提醒、自动导出（全部按班级独立排程）。"""
from __future__ import annotations

import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .database import session_scope
from .services import backup_service, class_service, export_service, notify_service, settings_service as ss
from .util import TZ

log = logging.getLogger("dorm.scheduler")

_scheduler: AsyncIOScheduler | None = None

JOB_GROUP_REPORT = "group_report"          # 老版单班级任务 id（启动时清理）
JOB_GROUP_REPORT_PREFIX = "group_report_c"  # 新版：group_report_c<班级id>
JOB_REMINDER = "missing_reminder"
JOB_REMINDER_PREFIX = "reminder_"           # 新版：reminder_c<班级id>_<提醒id>
JOB_EXPORT = "auto_export"
JOB_BACKUP = "db_backup"


async def job_group_report(class_id: int, trigger: str = "auto") -> None:
    """每天按班级配置的时间，把当天汇报发到该班级绑定的 QQ 群。"""
    with session_scope() as db:
        try:
            result = await notify_service.send_group_report(db, trigger=trigger, class_id=class_id)
            log.info(
                "群汇报完成（班级 %s，%s）：%s",
                class_id,
                result.get("channel") or "auto",
                result.get("message") or result.get("ok"),
            )
        except Exception:  # noqa: BLE001
            log.exception("群汇报失败（班级 %s）", class_id)


async def job_custom_reminder(class_id: int, reminder_id: str, trigger: str = "auto") -> None:
    """执行一条「定时提醒」（提醒推送页里配置的那些，按班级各自的时间发送）。"""
    with session_scope() as db:
        try:
            reminder = next(
                (item for item in ss.get_reminders(db, class_id=class_id) if str(item.get("id")) == reminder_id),
                None,
            )
            if reminder is None:
                log.warning("定时提醒 %s 不存在（可能已被删除）", reminder_id)
                return
            result = await notify_service.send_custom_reminder(db, reminder, trigger=trigger, class_id=class_id)
            log.info(
                "定时提醒「%s」完成（班级 %s）：%s",
                reminder.get("name"),
                class_id,
                result.get("message") or result.get("ok"),
            )
        except Exception:  # noqa: BLE001
            log.exception("定时提醒 %s 发送失败", reminder_id)


async def job_db_backup(trigger: str = "auto") -> None:
    """每天备份一次数据库（用 SQLite 官方备份接口，WAL 数据不会丢）。"""
    keep = 30
    try:
        with session_scope() as db:
            keep = int(ss.get_setting(db, "backup_keep") or "30")
    except (TypeError, ValueError):
        keep = 30
    except Exception:  # noqa: BLE001
        keep = 30
    result = backup_service.create_backup(keep=keep)
    if result.get("ok"):
        log.info("定时备份完成：%s", result.get("message"))
    else:
        log.warning("定时备份失败：%s", result.get("message"))


def job_auto_export() -> None:
    with session_scope() as db:
        try:
            if not ss.get_bool(db, "auto_export", True):
                log.info("自动导出已关闭，跳过")
                return
            path = export_service.export_auto_day(db)
            log.info("已自动导出：%s", path.name)
        except Exception:  # noqa: BLE001
            log.exception("自动导出失败")


def _cron(hour: int, minute: int) -> CronTrigger:
    return CronTrigger(hour=hour, minute=minute, timezone=TZ)


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=TZ)
    with session_scope() as db:
        _schedule_jobs(scheduler, db)
    return scheduler


def _schedule_jobs(scheduler: AsyncIOScheduler, db) -> None:
    export_hour, export_minute = ss.parse_time_of_day(ss.get_setting(db, "auto_export_time"), "23:30")
    backup_hour, backup_minute = ss.parse_time_of_day(ss.get_setting(db, "auto_backup_time"), "03:00")

    # 每个班级独立一套任务：群汇报 1 个 + 定时提醒 N 个，时间按班级级配置（回退全局值）。
    active_ids: set[str] = set()
    for cls in class_service.list_classes(db):
        cid = cls.id
        report_hour, report_minute = ss.parse_time_of_day(
            ss.get_setting(db, "qq_report_time", class_id=cid), "22:40"
        )
        report_job_id = f"{JOB_GROUP_REPORT_PREFIX}{cid}"
        active_ids.add(report_job_id)
        scheduler.add_job(
            job_group_report,
            _cron(report_hour, report_minute),
            id=report_job_id,
            replace_existing=True,
            misfire_grace_time=900,
            max_instances=1,
            kwargs={"class_id": cid, "trigger": "auto"},
        )
        for item in ss.get_reminders(db, class_id=cid):
            rid = str(item.get("id") or "").strip()
            if not rid or not item.get("enabled", True):
                continue
            reminder_job_id = f"{JOB_REMINDER_PREFIX}c{cid}_{rid}"
            active_ids.add(reminder_job_id)
            hour, minute = ss.parse_time_of_day(str(item.get("time") or ""), "22:00")
            scheduler.add_job(
                job_custom_reminder,
                _cron(hour, minute),
                id=reminder_job_id,
                replace_existing=True,
                misfire_grace_time=900,
                max_instances=1,
                kwargs={"class_id": cid, "reminder_id": rid, "trigger": "auto"},
            )
    # 清掉已删除班级/已删除停用提醒的任务，以及老版单班级任务 id
    for job in list(scheduler.get_jobs()):
        if job.id in (JOB_GROUP_REPORT, JOB_REMINDER):
            scheduler.remove_job(job.id)
        elif (
            job.id.startswith(JOB_GROUP_REPORT_PREFIX) or job.id.startswith(JOB_REMINDER_PREFIX)
        ) and job.id not in active_ids:
            scheduler.remove_job(job.id)
    # 说明：「未填报提醒」的定时任务已按要求删除，不再自动执行。
    # 需要时仍可在「提醒推送」页面手动点「推送提醒」发送一次
    # （手动入口走 notify_service.send_missing_reminder，不依赖这里的定时任务）。
    scheduler.add_job(
        job_db_backup,
        _cron(backup_hour, backup_minute),
        id=JOB_BACKUP,
        replace_existing=True,
        misfire_grace_time=3600,
        max_instances=1,
    )
    scheduler.add_job(
        job_auto_export,
        _cron(export_hour, export_minute),
        id=JOB_EXPORT,
        replace_existing=True,
        misfire_grace_time=1800,
        max_instances=1,
    )


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return _scheduler
    _scheduler = build_scheduler()
    _scheduler.start()
    log.info("定时任务已启动")
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("定时任务已停止")
    _scheduler = None


def reload_schedule() -> None:
    """配置改了以后重新装载任务时间。"""
    global _scheduler
    if _scheduler is None or not _scheduler.running:
        return
    with session_scope() as db:
        _schedule_jobs(_scheduler, db)
    log.info("定时任务时间已刷新")


def job_status() -> list[dict[str, Any]]:
    if _scheduler is None or not _scheduler.running:
        return []
    result: list[dict[str, Any]] = []
    static_labels = {
        JOB_EXPORT: "自动导出 Excel",
        JOB_BACKUP: "数据库备份",
    }
    # 按班级任务 id 反查显示名：group_report_c<id> / reminder_c<id>_<rid>
    class_names: dict[int, str] = {}
    reminder_names: dict[str, str] = {}
    try:
        with session_scope() as db:
            for cls in class_service.list_classes(db, active_only=False):
                class_names[cls.id] = cls.name
                for item in ss.get_reminders(db, class_id=cls.id):
                    key = f"{JOB_REMINDER_PREFIX}c{cls.id}_{item.get('id')}"
                    reminder_names[key] = f"定时提醒：{item.get('name', '')}（{cls.name}）"
    except Exception:  # noqa: BLE001
        pass
    for job in _scheduler.get_jobs():
        name = static_labels.get(job.id) or reminder_names.get(job.id)
        if name is None and job.id.startswith(JOB_GROUP_REPORT_PREFIX):
            suffix = job.id[len(JOB_GROUP_REPORT_PREFIX):]
            cname = class_names.get(int(suffix) if suffix.isdigit() else 0, f"班级 {suffix}")
            name = f"QQ 群汇报（{cname}）"
        result.append(
            {
                "id": job.id,
                "name": name or job.id,
                "next_run": job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
                if job.next_run_time
                else "",
            }
        )
    return result


async def run_job_now(job_id: str) -> dict[str, Any]:
    """管理界面上的“立即执行”。"""
    if job_id.startswith(JOB_GROUP_REPORT_PREFIX):
        suffix = job_id[len(JOB_GROUP_REPORT_PREFIX):]
        if suffix.isdigit():
            with session_scope() as db:
                return await notify_service.send_group_report(
                    db, trigger="manual", class_id=int(suffix)
                )
    if job_id.startswith(JOB_REMINDER_PREFIX):
        rest = job_id[len(JOB_REMINDER_PREFIX):]
        class_id = 0
        rid = rest
        if rest.startswith("c"):
            head, _, tail = rest.partition("_")
            if head[1:].isdigit() and tail:
                class_id = int(head[1:])
                rid = tail
        with session_scope() as db:
            reminder = next(
                (
                    item
                    for item in ss.get_reminders(db, class_id=class_id)
                    if str(item.get("id")) == rid
                ),
                None,
            )
            if reminder is None:
                return {"ok": False, "message": "这条提醒不存在（可能已被删除）"}
            return await notify_service.send_custom_reminder(
                db, reminder, trigger="manual", class_id=class_id
            )
    if job_id == JOB_BACKUP:
        result = backup_service.create_backup(keep=30)
        return {"ok": bool(result.get("ok")), "message": result.get("message", "")}
    if job_id == JOB_EXPORT:
        with session_scope() as db:
            path = export_service.export_auto_day(db)
            return {"ok": True, "message": f"已导出 {path.name}"}
    # 手动「推送提醒」（未填报名单）：missing_reminder 或 missing_reminder_c<班级id>
    if job_id == JOB_REMINDER or job_id.startswith(f"{JOB_REMINDER}_c"):
        class_id = 0
        suffix = job_id[len(JOB_REMINDER):]
        if suffix.startswith("_c") and suffix[2:].isdigit():
            class_id = int(suffix[2:])
        with session_scope() as db:
            if class_id <= 0:
                class_id = class_service.resolve_class_id(db, 0)
            return await notify_service.send_missing_reminder(db, trigger="manual", class_id=class_id)
    return {"ok": False, "message": "未知任务"}
