"""每日填报表单、记录查询、统计与导出。"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Dorm, Report
from ..security import (
    require_admin,
    assert_dorm_access,
    can_write_dorm,
    client_context,
    is_admin_port,
    leader_dorm_from_request,
)
from ..services import (
    class_service,
    export_service,
    notify_service,
    report_service,
    settings_service as ss,
)
from ..util import AppError, client_device, client_ip, now_local, parse_date, today

router = APIRouter(prefix="/api/reports", tags=["reports"])


class CheckinBody(BaseModel):
    member_id: int = 0
    name: str = ""
    present: bool = True
    reason: str = ""


class SubmitBody(BaseModel):
    dorm_id: int
    report_date: str = ""
    is_complete: bool = True
    absent_names: str = ""
    note: str = ""
    checkins: list[CheckinBody] = []
    submitter: str = ""  # 填表人自己写的名字（可留空，留空则记为匿名填报）


class AdminReportBody(BaseModel):
    dorm_id: int
    report_date: str = ""
    is_complete: bool = True
    absent_names: str = ""
    note: str = ""
    submitter: str = ""


def _resolve_day(raw: str | None) -> date:
    if not raw:
        return today()
    return parse_date(raw)


@router.get("/today")
def report_today(
    db: Session = Depends(get_db),
    day: str | None = None,
    class_id: int = 0,
):
    target = _resolve_day(day)
    cid = class_service.resolve_class_id(db, class_id)
    rows = report_service.dorm_day_rows(db, target, class_id=cid)
    stats = report_service.day_stats(db, target, class_id=cid)
    return {
        "ok": True,
        "class_id": cid,
        "date": target.strftime("%Y-%m-%d"),
        "stats": stats,
        "items": rows,
        "server_time": now_local().strftime("%Y-%m-%d %H:%M:%S"),
        "notice": ss.get_setting(db, "site_notice"),
    }


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), class_id: int = 0):
    cid = class_service.resolve_class_id(db, class_id)
    target = today()
    stats = report_service.day_stats(db, target, class_id=cid)
    week_start = target - timedelta(days=target.weekday())
    month_start = target.replace(day=1)
    week = report_service.trend(db, "day", target, points=(target - week_start).days + 1, class_id=cid)["items"]
    month_rows = report_service.dorm_ranking(db, month_start, target, class_id=cid)
    return {
        "ok": True,
        "class_id": cid,
        "today": target.strftime("%Y-%m-%d"),
        "weekday": stats["weekday"],
        "stats": stats,
        "items": report_service.dorm_day_rows(db, target, class_id=cid),
        "week_avg_rate": round(sum(i["rate"] for i in week) / len(week), 1) if week else 0.0,
        "month_avg_rate": round(
            sum(r["rate"] for r in month_rows) / len(month_rows), 1
        )
        if month_rows
        else 0.0,
        "recent": report_service.recent_submissions(db, 12, class_id=cid),
        "worst_dorms": month_rows[:5],
        "server_time": now_local().strftime("%Y-%m-%d %H:%M:%S"),
        "notice": ss.get_setting(db, "site_notice"),
    }


@router.get("/status")
def poll_status(
    db: Session = Depends(get_db),
    day: str | None = None,
    class_id: int = 0,
):
    """前端轮询：实时展示最新填报。"""
    target = _resolve_day(day)
    cid = class_service.resolve_class_id(db, class_id)
    stats = report_service.day_stats(db, target, class_id=cid)
    return {
        "ok": True,
        "class_id": cid,
        "stats": stats,
        "recent": report_service.recent_submissions(db, 10, class_id=cid),
        "server_time": now_local().strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.get("/dorm/{dorm_id}")
def dorm_report(
    dorm_id: int,
    request: Request,
    db: Session = Depends(get_db),
    day: str | None = None,
):
    target = _resolve_day(day)
    dorm = db.get(Dorm, dorm_id)
    if dorm is None:
        raise AppError("宿舍不存在", 404)
    report = report_service.get_report(db, dorm_id, target)
    members = report_service.dorm_members(db, dorm_id)
    checks = {c.member_id: c for c in (report.checks if report else [])}
    return {
        "ok": True,
        "date": target.strftime("%Y-%m-%d"),
        "dorm": {
            "id": dorm.id,
            "room_no": dorm.room_no,
            "room_label": dorm.room_label,
            "building": dorm.building,
            "leader_name": dorm.leader_name,
            "leader_phone": dorm.leader_phone,
            "note": dorm.note,
        },
        "locked": bool(dorm.leader_password),
        "can_write": can_write_dorm(db, request, dorm),
        "members": [
            {
                "id": member.id,
                "name": member.name,
                "student_no": member.student_no,
                "phone": member.phone,
                "role": member.role,
                "present": checks[member.id].present if member.id in checks else True,
                "reason": checks[member.id].reason if member.id in checks else "",
            }
            for member in members
        ],
        "report": report_service.serialize_report(report, dorm) if report else None,
        "absence_reasons": [
            item.strip()
            for item in ss.get_setting(db, "absence_reasons").replace("，", ",").split(",")
            if item.strip()
        ],
    }


@router.post("/submit")
def submit_report(
    body: SubmitBody,
    request: Request,
    db: Session = Depends(get_db),
):
    dorm = db.get(Dorm, body.dorm_id)
    if dorm is None:
        raise AppError("宿舍不存在", 404)
    # 设了验证密码的寝室，必须先用该寝室的寝室长账户验证
    assert_dorm_access(db, request, dorm, what="填报")
    target = _resolve_day(body.report_date)
    if target > today():
        raise AppError("不能填报未来的日期")
    if (today() - target).days > 7:
        raise AppError("只能补填最近 7 天")

    submitter = body.submitter.strip() or client_context(request)["display_name"]
    report = report_service.apply_report(
        db,
        dorm,
        target,
        is_complete=body.is_complete,
        absent_names=body.absent_names,
        note=body.note,
        checkins=[item.model_dump() for item in body.checkins],
        source="web",
        submitter=submitter,
        ip=client_ip(request),
        user_agent=client_device(request),
    )
    leader = leader_dorm_from_request(db, request)
    ss.write_audit(
        db,
        actor=submitter,
        role="leader" if (leader and leader.id == dorm.id) else "public",
        action="提交填报",
        target=f"{dorm.room_no} {target.strftime('%Y-%m-%d')}",
        detail=f"{'齐全' if body.is_complete else '缺人'} {body.absent_names} {body.note}",
        ip=client_ip(request),
        user_agent=client_device(request),
    )
    db.commit()
    return {
        "ok": True,
        "message": f"{dorm.room_no} 的填报已提交"
        + ("（人员齐全）" if body.is_complete else f"（不在人员：{report.absent_names or '见备注'}）"),
        "report": report_service.serialize_report(report, dorm),
    }


@router.post("/admin")
def admin_submit(
    body: AdminReportBody,
    request: Request,
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    """补填 / 修改任意宿舍的填报（公开端口受寝室密码限制，管理端口始终可改）。"""
    dorm = db.get(Dorm, body.dorm_id)
    if dorm is None:
        raise AppError("宿舍不存在", 404)
    assert_dorm_access(db, request, dorm, what="补填")
    target = _resolve_day(body.report_date)
    submitter = body.submitter.strip() or client_context(request)["display_name"]
    report = report_service.apply_report(
        db,
        dorm,
        target,
        is_complete=body.is_complete,
        absent_names=body.absent_names,
        note=body.note,
        source="admin" if is_admin_port(request) else "web",
        submitter=submitter,
        ip=client_ip(request),
        user_agent=client_device(request),
    )
    ss.write_audit(
        db,
        actor=submitter,
        role="admin" if is_admin_port(request) else "public",
        action="代填/修改填报",
        target=f"{dorm.room_no} {target.strftime('%Y-%m-%d')}",
        ip=client_ip(request),
        user_agent=client_device(request),
    )
    db.commit()
    return {"ok": True, "message": f"已保存 {dorm.room_no} 的填报", "report": report_service.serialize_report(report, dorm)}


@router.delete("/{report_id}")
def delete_report(
    report_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    report = db.get(Report, report_id)
    if report is None:
        raise AppError("记录不存在", 404)
    label = f"{report.dorm_id} {report.report_date}"
    db.delete(report)
    db.commit()
    ss.write_audit(
        db,
        actor=client_context(request)["display_name"],
        role="public",
        action="删除填报",
        target=label,
        ip=client_ip(request),
    )
    db.commit()
    return {"ok": True, "message": "记录已删除"}


@router.get("/records")
def list_records(
    db: Session = Depends(get_db),
    start: str | None = None,
    end: str | None = None,
    dorm_id: int | None = None,
    only_incomplete: bool = False,
    keyword: str = "",
    class_id: int = 0,
):
    cid = class_service.resolve_class_id(db, class_id)
    end_day = _resolve_day(end)
    start_day = parse_date(start) if start else end_day - timedelta(days=6)
    if start_day > end_day:
        start_day, end_day = end_day, start_day
    items = report_service.reports_in_range(
        db,
        start_day,
        end_day,
        dorm_id=dorm_id,
        only_incomplete=only_incomplete,
        keyword=keyword.strip(),
        class_id=cid,
    )
    return {
        "ok": True,
        "class_id": cid,
        "start": start_day.strftime("%Y-%m-%d"),
        "end": end_day.strftime("%Y-%m-%d"),
        "items": items,
        "absents": report_service.absent_records(db, start_day, end_day, class_id=cid),
        "total": len(items),
    }


@router.get("/stats")
def stats(
    db: Session = Depends(get_db),
    granularity: str = "day",
    anchor: str | None = None,
    points: int = 14,
    day: str | None = None,
    class_id: int = 0,
):
    cid = class_service.resolve_class_id(db, class_id)
    points = max(3, min(int(points or 14), 60))
    anchor_day = _resolve_day(anchor)
    result = report_service.trend(db, granularity, anchor_day, points, class_id=cid)
    target = _resolve_day(day)
    week_start = target - timedelta(days=target.weekday())
    month_start = target.replace(day=1)
    return {
        "ok": True,
        "class_id": cid,
        **result,
        "today_stats": report_service.day_stats(db, target, class_id=cid),
        "hourly": report_service.hourly_distribution(db, month_start, target, class_id=cid),
        "ranking_week": report_service.dorm_ranking(db, week_start, target, class_id=cid),
        "ranking_month": report_service.dorm_ranking(db, month_start, target, class_id=cid),
        "dorm_rows": report_service.dorm_day_rows(db, target, class_id=cid),
    }


@router.get("/export")
def export_reports(
    db: Session = Depends(get_db),
    day: str | None = None,
    start: str | None = None,
    end: str | None = None,
    as_zip: bool = False,
    class_id: int = 0,
    _: dict = Depends(require_admin),
):
    cid = class_service.resolve_class_id(db, class_id)
    if start or end:
        start_day = parse_date(start) if start else _resolve_day(end)
        end_day = parse_date(end) if end else start_day
        if start_day > end_day:
            start_day, end_day = end_day, start_day
        if as_zip:
            content = export_service.export_range_zip(db, start_day, end_day, cid)
            filename = f"宿舍填报_{start_day.strftime('%Y%m%d')}-{end_day.strftime('%Y%m%d')}.zip"
            media = "application/zip"
        else:
            content = export_service.export_range_bytes(db, start_day, end_day, cid)
            filename = f"宿舍填报_{start_day.strftime('%Y%m%d')}-{end_day.strftime('%Y%m%d')}.xlsx"
            media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        target = _resolve_day(day)
        content = export_service.export_day_bytes(db, target, cid)
        filename = f"宿舍填报_{target.strftime('%Y-%m-%d')}.xlsx"
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    from urllib.parse import quote

    return Response(
        content=content,
        media_type=media,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "X-Filename": quote(filename),
        },
    )


@router.get("/export-files")
def export_files(db: Session = Depends(get_db), _: dict = Depends(require_admin)):
    return {"ok": True, "items": export_service.list_export_files()}


@router.get("/export-files/{name}")
def download_export_file(name: str, _: dict = Depends(require_admin)):
    path = export_service.find_file(name)
    return Response(
        content=path.read_bytes(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={path.name.encode('utf-8').decode('latin-1', 'ignore')}"},
    )


@router.post("/export-now")
def export_now(
    request: Request,
    db: Session = Depends(get_db),
    day: str | None = None,
    class_id: int = 0,
    _: dict = Depends(require_admin),
):
    cid = class_service.resolve_class_id(db, class_id)
    target = _resolve_day(day)
    path = export_service.export_day_file(db, target, class_id=cid)
    ss.write_audit(
        db,
        actor=client_context(request)["display_name"],
        role="public",
        action="手动导出 Excel",
        target=target.strftime("%Y-%m-%d"),
        detail=path.name,
        ip=client_ip(request),
    )
    db.commit()
    return {"ok": True, "message": f"已生成 {path.name}", "file": path.name}


@router.get("/preview")
def preview_group_report(
    db: Session = Depends(get_db),
    day: str | None = None,
    class_id: int = 0,
):
    """预览将要发到 QQ 群的内容（不真的发送）。"""
    cid = class_service.resolve_class_id(db, class_id)
    target = _resolve_day(day)
    return {
        "ok": True,
        "class_id": cid,
        "date": target.strftime("%Y-%m-%d"),
        "group_report": notify_service.build_group_report(db, target, class_id=cid),
        "reminder": notify_service.build_missing_reminder(db, target, class_id=cid),
        "fill_remind": notify_service.build_fill_reminder(db, target, class_id=cid),
        "fill_remind_site": notify_service.public_site_url(db),
        "fill_remind_time": ss.get_setting(db, "fill_remind_time"),
        "fill_remind_enabled": ss.get_bool(db, "fill_remind_enabled", True),
        "fill_remind_mention_all": ss.get_bool(db, "fill_remind_mention_all", True),
        "missing": [d.room_no for d in report_service.missing_dorms(db, target, class_id=cid)],
    }
