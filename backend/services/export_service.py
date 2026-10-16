"""Excel 导出与文件管理：每天自动导出，也支持手动导出与打包下载。"""
from __future__ import annotations

import io
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from .. import config, excel_util
from ..util import AppError, date_range, from_timestamp, now_local, safe_filename
from . import class_service, report_service, settings_service as ss


def _class_display_name(db: Session, class_id: int) -> str:
    """导出表头里显示的班级名：优先用班级实体名，老数据回退全局配置。"""
    if class_id and class_id > 0:
        cls = class_service.get_class(db, int(class_id))
        if cls is not None:
            return cls.name
    return ss.get_setting(db, "class_name")


def day_export_data(
    db: Session, day: date, class_id: int = 0
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """组装某一天的汇总行、明细行和表头信息。class_id>0 时只导出该班级。"""
    rows = report_service.dorm_day_rows(db, day, class_id=class_id)
    stats = report_service.day_stats(db, day, class_id=class_id)
    detail: list[dict[str, Any]] = []
    for row in rows:
        if not row["reported"]:
            for member in report_service.dorm_members(db, row["dorm_id"]):
                detail.append(
                    {
                        "room_no": row["room_no"],
                        "name": member.name,
                        "student_no": member.student_no,
                        "phone": member.phone,
                        "present": True,
                        "reason": "",
                        "note": "未填报，状态未知",
                    }
                )
            continue
        report = report_service.get_report(db, row["dorm_id"], day)
        checks = {check.member_name: check for check in (report.checks if report else [])}
        for member in report_service.dorm_members(db, row["dorm_id"], active_only=False):
            check = checks.get(member.name)
            detail.append(
                {
                    "room_no": row["room_no"],
                    "name": member.name,
                    "student_no": member.student_no,
                    "phone": member.phone,
                    "present": check.present if check else True,
                    "reason": check.reason if check else "",
                    "note": row["note"] if check is None or not check.present else "",
                }
            )
    meta = {
        "school_name": ss.get_setting(db, "school_name"),
        "class_name": _class_display_name(db, class_id),
        "dorm_total": stats["dorm_total"],
        "reported": stats["reported"],
        "unreported": stats["unreported"],
        "present": stats["present"],
        "total": stats["total"],
        "absent": stats["absent"],
        "exported_at": now_local().strftime("%Y-%m-%d %H:%M:%S"),
    }
    return rows, detail, meta


def export_day_bytes(db: Session, day: date, class_id: int = 0) -> bytes:
    rows, detail, meta = day_export_data(db, day, class_id=class_id)
    return excel_util.export_reports([day], {day: rows}, {day: detail}, meta)


def export_range_bytes(db: Session, start: date, end: date, class_id: int = 0) -> bytes:
    days = list(date_range(start, end))
    if len(days) > 62:
        raise AppError("一次最多导出 62 天，请缩小范围")
    summaries: dict[date, list[dict[str, Any]]] = {}
    details: dict[date, list[dict[str, Any]]] = {}
    meta: dict[str, Any] = {}
    for day in days:
        rows, detail, day_meta = day_export_data(db, day, class_id=class_id)
        summaries[day] = rows
        details[day] = detail
        meta = day_meta
    meta["exported_at"] = now_local().strftime("%Y-%m-%d %H:%M:%S")
    return excel_util.export_reports(days, summaries, details, meta)


def export_day_file(db: Session, day: date, *, class_id: int = 0,
                    folder: Path | None = None) -> Path:
    folder = folder or config.EXPORT_DIR
    folder.mkdir(parents=True, exist_ok=True)
    name = f"宿舍填报_{day.strftime('%Y-%m-%d')}.xlsx"
    if class_id > 0:
        cname = safe_filename(_class_display_name(db, class_id), "")
        if cname:
            name = f"宿舍填报_{cname}_{day.strftime('%Y-%m-%d')}.xlsx"
    target = folder / name
    target.write_bytes(export_day_bytes(db, day, class_id=class_id))
    return target


def export_range_zip(db: Session, start: date, end: date, class_id: int = 0) -> bytes:
    """按天打包成一个 zip，每个日期一个 Excel。"""
    prefix = ""
    if class_id > 0:
        cname = safe_filename(_class_display_name(db, class_id), "")
        if cname:
            prefix = f"{cname}_"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for day in date_range(start, end):
            archive.writestr(
                f"宿舍填报_{prefix}{day.strftime('%Y-%m-%d')}.xlsx",
                export_day_bytes(db, day, class_id=class_id),
            )
    return buffer.getvalue()


def list_export_files(limit: int = 200) -> list[dict[str, Any]]:
    config.ensure_dirs()
    files = sorted(config.EXPORT_DIR.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
    result = []
    for path in files[:limit]:
        stat = path.stat()
        result.append(
            {
                "name": path.name,
                "size": stat.st_size,
                "size_text": _human_size(stat.st_size),
                "modified": from_timestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return result


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{value:.1f}GB"


def cleanup_exports(keep: int = 400) -> int:
    files = sorted(config.EXPORT_DIR.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
    removed = 0
    for path in files[keep:]:
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def export_auto_day(db: Session, day: date | None = None) -> Path:
    """定时任务调用：导出当天 Excel 并清理过期文件。"""
    day = day or now_local().date()
    path = export_day_file(db, day)
    cleanup_exports()
    return path


def find_file(name: str) -> Path:
    config.ensure_dirs()
    safe = safe_filename(name, "export.xlsx")
    candidate = (config.EXPORT_DIR / safe).resolve()
    if config.EXPORT_DIR.resolve() not in candidate.parents:
        raise AppError("非法文件名")
    if not candidate.exists():
        raise AppError("文件不存在或已被清理")
    return candidate
