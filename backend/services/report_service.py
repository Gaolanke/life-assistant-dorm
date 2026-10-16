"""填报数据服务：写入、查询、统计、群消息解析。"""
from __future__ import annotations

import html
import re
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Dorm, Member, Report, ReportCheckin
from ..util import TZ, AppError, now_local, parse_date, today

SOURCE_LABELS = {
    "web": "网页填报",
    "qq": "QQ 群填报",
    "qqbot": "机器人代填",
    "admin": "管理员代填",
    "import": "表格导入",
}


# --------------------------------------------------------------------------
# 读取
# --------------------------------------------------------------------------
def list_dorms(db: Session, active_only: bool = True, class_id: int = 0) -> list[Dorm]:
    """宿舍列表。class_id>0 时只返回该班级的宿舍。"""
    stmt = select(Dorm).order_by(Dorm.sort_order, Dorm.room_no)
    if int(class_id or 0) > 0:
        stmt = stmt.where(Dorm.class_id == int(class_id))
    if active_only:
        stmt = stmt.where(Dorm.active.is_(True))
    return list(db.execute(stmt).scalars())


def dorm_members(db: Session, dorm_id: int, active_only: bool = True) -> list[Member]:
    stmt = select(Member).where(Member.dorm_id == dorm_id).order_by(Member.id)
    if active_only:
        stmt = stmt.where(Member.active.is_(True))
    return list(db.execute(stmt).scalars())


def find_member(db: Session, member_id: int) -> Member | None:
    return db.get(Member, member_id)


def get_dorm_by_room(db: Session, room_no: str, class_id: int = 0) -> Dorm | None:
    room_no = (room_no or "").strip()
    if not room_no:
        return None
    scope = select(Dorm)
    if int(class_id or 0) > 0:
        scope = scope.where(Dorm.class_id == int(class_id))
    dorm = db.execute(scope.where(Dorm.room_no == room_no)).scalar_one_or_none()
    if dorm:
        return dorm
    # 容错：忽略楼栋前缀 / 连字符，例如 3-201 与 201
    tail = re.split(r"[-—－#号楼栋\s]+", room_no)
    tail = [t for t in tail if t]
    if not tail:
        return None
    candidates = list(db.execute(scope).scalars())
    for item in candidates:
        if item.room_no in (tail[-1], room_no):
            return item
        if item.room_no.replace("-", "").replace("号楼", "") == room_no.replace("-", ""):
            return item
    return None


def get_report(db: Session, dorm_id: int, day: date) -> Report | None:
    return db.execute(
        select(Report).where(Report.dorm_id == dorm_id, Report.report_date == day)
    ).scalar_one_or_none()


def reported_dorm_ids(db: Session, day: date) -> set[int]:
    rows = db.execute(select(Report.dorm_id).where(Report.report_date == day)).scalars()
    return set(rows)


def missing_dorms(db: Session, day: date, class_id: int = 0) -> list[Dorm]:
    reported = reported_dorm_ids(db, day)
    return [dorm for dorm in list_dorms(db, class_id=class_id) if dorm.id not in reported]


def serialize_checkin(row: ReportCheckin) -> dict[str, Any]:
    return {
        "id": row.id,
        "member_id": row.member_id,
        "name": row.member_name,
        "student_no": row.student_no,
        "present": row.present,
        "reason": row.reason,
    }


def serialize_report(report: Report, dorm: Dorm | None = None) -> dict[str, Any]:
    return {
        "id": report.id,
        "dorm_id": report.dorm_id,
        "room_no": dorm.room_no if dorm else "",
        "building": dorm.building if dorm else "",
        "leader_name": dorm.leader_name if dorm else "",
        "report_date": report.report_date.strftime("%Y-%m-%d"),
        "is_complete": report.is_complete,
        "absent_names": report.absent_names,
        "note": report.note,
        "total_count": report.total_count,
        "present_count": report.present_count,
        "absent_count": report.absent_count,
        "source": report.source,
        "source_text": SOURCE_LABELS.get(report.source, report.source),
        "submitter": report.submitter,
        "raw_message": report.raw_message,
        "submitted_at": report.submitted_at.strftime("%Y-%m-%d %H:%M:%S") if report.submitted_at else "",
        "updated_at": report.updated_at.strftime("%Y-%m-%d %H:%M:%S") if report.updated_at else "",
        "ip": report.ip,
        "user_agent": report.user_agent,
        "device": _device_label(report.user_agent),
        "checks": [serialize_checkin(c) for c in report.checks],
    }


def _device_label(user_agent: str) -> str:
    """把 User-Agent 简化成“系统 · 浏览器”（见 util.device_label）。"""
    from ..util import device_label

    return device_label(user_agent)


def dorm_day_rows(db: Session, day: date, class_id: int = 0) -> list[dict[str, Any]]:
    """当天所有宿舍的汇总行（未填报的也在里面）。class_id>0 时只看该班级。"""
    dorms = list_dorms(db, class_id=class_id)
    reports = {
        row.dorm_id: row
        for row in db.execute(select(Report).where(Report.report_date == day)).scalars()
    }
    rows: list[dict[str, Any]] = []
    for dorm in dorms:
        report = reports.get(dorm.id)
        if report is None:
            rows.append(
                {
                    "dorm_id": dorm.id,
                    "room_no": dorm.room_no,
                    "building": dorm.building,
                    "leader_name": dorm.leader_name,
                    "leader_phone": dorm.leader_phone,
                    "reported": False,
                    "status_text": "未填报",
                    "is_complete": None,
                    "total_count": len(dorm_members(db, dorm.id)),
                    "present_count": 0,
                    "absent_count": 0,
                    "absent_names": "",
                    "note": "",
                    "submitter": "",
                    "submitted_at": "",
                    "submitted_time": "",
                    "source": "",
                    "source_text": "",
                    "ip": "",
                    "device": "",
                }
            )
            continue
        rows.append(
            {
                "dorm_id": dorm.id,
                "room_no": dorm.room_no,
                "building": dorm.building,
                "leader_name": dorm.leader_name,
                "leader_phone": dorm.leader_phone,
                "reported": True,
                "status_text": "齐全" if report.is_complete else "缺人",
                "is_complete": report.is_complete,
                "total_count": report.total_count,
                "present_count": report.present_count,
                "absent_count": report.absent_count,
                "absent_names": report.absent_names,
                "note": report.note,
                "submitter": report.submitter,
                "submitted_at": report.submitted_at.strftime("%Y-%m-%d %H:%M:%S")
                if report.submitted_at
                else "",
                "submitted_time": report.submitted_at.strftime("%H:%M") if report.submitted_at else "",
                "source": report.source,
                "source_text": SOURCE_LABELS.get(report.source, report.source),
                "ip": report.ip,
                "device": _device_label(report.user_agent),
            }
        )
    return rows


def day_stats(db: Session, day: date, class_id: int = 0) -> dict[str, Any]:
    rows = dorm_day_rows(db, day, class_id)
    reported = [r for r in rows if r["reported"]]
    return {
        "date": day.strftime("%Y-%m-%d"),
        "weekday": "星期" + "一二三四五六日"[day.weekday()],
        "dorm_total": len(rows),
        "reported": len(reported),
        "unreported": len(rows) - len(reported),
        "complete": sum(1 for r in reported if r["is_complete"]),
        "incomplete": sum(1 for r in reported if not r["is_complete"]),
        "total": sum(r["total_count"] for r in reported),
        "present": sum(r["present_count"] for r in reported),
        "absent": sum(r["absent_count"] for r in reported),
        "rate": round(len(reported) / len(rows) * 100, 1) if rows else 0.0,
        "missing_rooms": [r["room_no"] for r in rows if not r["reported"]],
        "absent_rooms": [
            {
                "room_no": r["room_no"],
                "absent_count": r["absent_count"],
                "absent_names": r["absent_names"],
                "note": r["note"],
            }
            for r in reported
            if r["absent_count"] > 0
        ],
    }


# --------------------------------------------------------------------------
# 写入
# --------------------------------------------------------------------------
def _split_names(text: str) -> list[str]:
    return [n.strip() for n in re.split(r"[、,，;；/|\s]+", text or "") if n.strip()]


def resolve_absent_members(db: Session, dorm: Dorm, names: Sequence[str]) -> list[Member]:
    """把“不在人员”的文字匹配到成员记录。"""
    members = dorm_members(db, dorm.id, active_only=False)
    found: list[Member] = []
    for name in names:
        key = name.strip()
        if not key:
            continue
        match = None
        for member in members:
            if member.student_no and member.student_no == key:
                match = member
                break
            if member.name == key:
                match = member
                break
        if match is None:
            for member in members:
                if key and (key in member.name or member.name in key):
                    match = member
                    break
        if match is not None and match not in found:
            found.append(match)
    return found


def apply_report(
    db: Session,
    dorm: Dorm,
    day: date,
    *,
    is_complete: bool | None = None,
    absent_names: str = "",
    note: str = "",
    checkins: Sequence[dict[str, Any]] | None = None,
    source: str = "web",
    submitter: str = "",
    raw_message: str = "",
    ip: str = "",
    user_agent: str = "",
    commit: bool = True,
) -> Report:
    """写入/覆盖某宿舍某天的填报记录。"""
    members = dorm_members(db, dorm.id, active_only=False)
    active_members = [m for m in members if m.active]

    present_flags: dict[int, tuple[bool, str]] = {}
    if checkins is not None:
        by_id = {m.id: m for m in members}
        by_name = {m.name: m for m in members}
        for item in checkins:
            member = None
            if item.get("member_id"):
                member = by_id.get(int(item["member_id"]))
            if member is None and item.get("name"):
                member = by_name.get(str(item["name"]).strip())
            if member is None:
                continue
            present_flags[member.id] = (
                bool(item.get("present", True)),
                str(item.get("reason") or "")[:200],
            )

    if present_flags:
        absent_members = [m for m in active_members if not present_flags.get(m.id, (True, ""))[0]]
    else:
        name_list = _split_names(absent_names)
        absent_members = resolve_absent_members(db, dorm, name_list)

    if is_complete is None:
        is_complete = len(absent_members) == 0

    if is_complete and not absent_members:
        absent_text = ""
    else:
        absent_text = absent_names.strip() or "、".join(m.name for m in absent_members)

    total = len(active_members)
    absent_count = len(absent_members) if absent_members else len(_split_names(absent_text))
    absent_count = min(absent_count, total) if total else absent_count
    present_count = max(total - absent_count, 0) if is_complete is False or absent_count else total

    # 同宿舍同一天只允许一条记录（表上有 uq_report_dorm_date 唯一约束）。
    # 两人同时提交（或同一人连点两次）时，用 SAVEPOINT 兜住并发插入冲突：
    # 插不进去就回退成"更新已有记录"，不报错、也不会多出人数。
    report = get_report(db, dorm.id, day)
    if report is None:
        try:
            with db.begin_nested():
                fresh = Report(dorm_id=dorm.id, report_date=day)
                db.add(fresh)
                db.flush()
            report = fresh
        except IntegrityError:
            # 并发：别人已经插入了同宿舍同一天的记录。
            # 结束当前事务拿一个最新快照，再读出来改成更新。
            db.rollback()
            report = get_report(db, dorm.id, day)
            if report is None:
                raise
            for old in list(report.checks):
                db.delete(old)
            db.flush()
    else:
        # 已有记录：清掉旧的勾选明细，下面按本次内容重建
        for old in list(report.checks):
            db.delete(old)
        db.flush()

    report.is_complete = bool(is_complete)
    report.absent_names = absent_text[:300]
    report.note = (note or "").strip()
    report.total_count = total
    report.present_count = present_count
    report.absent_count = absent_count
    report.source = source
    report.submitter = submitter[:60]
    report.raw_message = raw_message[:1000]
    report.ip = (ip or "")[:64]
    report.user_agent = (user_agent or "")[:300]
    report.submitted_at = now_local()
    report.updated_at = now_local()

    absent_ids = {m.id for m in absent_members}
    if checkins is None:
        member_list = active_members
    else:
        member_list = active_members
    for member in member_list:
        present, reason = present_flags.get(member.id, (member.id not in absent_ids, ""))
        report.checks.append(
            ReportCheckin(
                member_id=member.id,
                member_name=member.name,
                student_no=member.student_no,
                present=present,
                reason=reason,
            )
        )
    db.flush()
    if commit:
        db.commit()
        db.refresh(report)
    return report


def delete_report(db: Session, dorm_id: int, day: date) -> bool:
    report = get_report(db, dorm_id, day)
    if report is None:
        return False
    db.delete(report)
    db.commit()
    return True


# --------------------------------------------------------------------------
# 群消息解析
# --------------------------------------------------------------------------
COMPLETE_WORDS = ["人齐", "都齐", "全齐", "齐全", "全在", "都在", "没人缺", "无缺", "正常", "齐"]
ABSENT_WORDS = ["缺", "不在", "没回", "未归", "请假", "外出", "未到", "少"]


def parse_group_message(text: str, dorms: Iterable[Dorm]) -> dict[str, Any] | None:
    """解析宿舍长在 QQ 群里的填报文本。

    支持：201 人齐 / 201 缺 张三、李四 / 3-201 齐全 / 201 张三不在
    """
    raw = (text or "").strip()
    if not raw or len(raw) > 300:
        return None
    room_no = _extract_room(raw, dorms)
    if not room_no:
        return None

    body = raw.replace(room_no, " ", 1)
    body = re.sub(r"^[\s,，:：、\-—]+", "", body)
    body = re.sub(r"(宿舍|寝室|人|情况|报告|汇报|已报|填报)$", "", body).strip()

    is_complete: bool | None = None
    if any(word in body for word in COMPLETE_WORDS) and not any(
        word in body for word in ["缺", "不在", "没回", "未归"]
    ):
        is_complete = True
    elif any(word in body for word in ABSENT_WORDS):
        is_complete = False
    else:
        names = _split_names(re.sub(r"^(人|都|全)", "", body))
        if names and len(names) <= 12 and all(len(n) <= 4 for n in names):
            is_complete = False
        elif not body:
            is_complete = True

    if is_complete is None:
        return None

    absent_names = ""
    if not is_complete:
        cleaned = re.sub(
            r"^(人|都|全)?(缺|不在|没回|未归|请假|外出|未到|少了?|有)\s*", "", body
        )
        cleaned = re.sub(r"(人|同学|未归|没回来|不在宿舍|不在寝)$", "", cleaned).strip()
        absent_names = "、".join(_split_names(cleaned))
    return {
        "room_no": room_no,
        "is_complete": is_complete,
        "absent_names": absent_names,
        "raw": raw,
    }


def _extract_room(text: str, dorms: Iterable[Dorm]) -> str | None:
    head = text.split()[0] if text.split() else text
    head = re.split(r"[:：,，。!！]", head)[0]
    for dorm in dorms:
        if dorm.room_no and dorm.room_no in text[:20]:
            return dorm.room_no
    match = re.match(r"^([A-Za-z]?\d{1,2}[-#－]?\d{2,4}|\d{1,2}号楼\d{2,4})", head)
    if match:
        candidate = match.group(1)
        for dorm in dorms:
            if dorm.room_no.replace("-", "").replace("号楼", "") == candidate.replace(
                "-", ""
            ).replace("号楼", ""):
                return dorm.room_no
        return candidate
    return None


# --------------------------------------------------------------------------
# 趋势统计（天 / 周 / 月）
# --------------------------------------------------------------------------
def _aggregate(db: Session, start: date, end: date, class_id: int = 0) -> dict[str, dict[str, int]]:
    stmt = (
        select(
            Report.report_date,
            func.count(Report.id),
            func.coalesce(func.sum(Report.total_count), 0),
            func.coalesce(func.sum(Report.present_count), 0),
            func.coalesce(func.sum(Report.absent_count), 0),
        )
        .where(Report.report_date >= start, Report.report_date <= end)
        .group_by(Report.report_date)
    )
    if int(class_id or 0) > 0:
        stmt = stmt.join(Dorm, Report.dorm_id == Dorm.id).where(Dorm.class_id == int(class_id))
    rows = db.execute(stmt).all()
    return {
        row[0].strftime("%Y-%m-%d"): {
            "reported": int(row[1] or 0),
            "total": int(row[2] or 0),
            "present": int(row[3] or 0),
            "absent": int(row[4] or 0),
        }
        for row in rows
    }


def trend(
    db: Session,
    granularity: str = "day",
    anchor: date | None = None,
    points: int = 14,
    class_id: int = 0,
) -> dict[str, Any]:
    """按天/周/月聚合趋势数据。class_id>0 时只统计该班级。"""
    anchor = anchor or today()
    granularity = granularity if granularity in {"day", "week", "month"} else "day"
    dorm_total = len(list_dorms(db, class_id=class_id))
    items: list[dict[str, Any]] = []

    if granularity == "day":
        start = anchor - timedelta(days=points - 1)
        data = _aggregate(db, start, anchor, class_id)
        cursor = start
        while cursor <= anchor:
            key = cursor.strftime("%Y-%m-%d")
            item = data.get(key, {"reported": 0, "total": 0, "present": 0, "absent": 0})
            items.append(
                {
                    "key": key,
                    "label": cursor.strftime("%m-%d"),
                    "full_label": key + " 星期" + "一二三四五六日"[cursor.weekday()],
                    **item,
                    "dorm_total": dorm_total,
                    "rate": round(item["reported"] / dorm_total * 100, 1) if dorm_total else 0.0,
                }
            )
            cursor += timedelta(days=1)
    elif granularity == "week":
        start_of_week = anchor - timedelta(days=anchor.weekday())
        for index in range(points - 1, -1, -1):
            week_start = start_of_week - timedelta(weeks=index)
            week_end = week_start + timedelta(days=6)
            data = _aggregate(db, week_start, week_end, class_id)
            reported = sum(v["reported"] for v in data.values())
            total = sum(v["total"] for v in data.values())
            present = sum(v["present"] for v in data.values())
            absent = sum(v["absent"] for v in data.values())
            expected = dorm_total * 7
            items.append(
                {
                    "key": week_start.strftime("%Y-%m-%d"),
                    "label": f"{week_start.strftime('%m-%d')}周",
                    "full_label": f"{week_start.strftime('%Y-%m-%d')} ~ {week_end.strftime('%m-%d')}",
                    "reported": reported,
                    "total": total,
                    "present": present,
                    "absent": absent,
                    "dorm_total": dorm_total,
                    "rate": round(reported / expected * 100, 1) if expected else 0.0,
                    "days": len(data),
                }
            )
    else:  # month
        year, month = anchor.year, anchor.month
        cursor_month = month - (points - 1)
        cursor_year = year
        while cursor_month <= 0:
            cursor_month += 12
            cursor_year -= 1
        for _ in range(points):
            month_start = date(cursor_year, cursor_month, 1)
            if cursor_month == 12:
                month_end = date(cursor_year, 12, 31)
            else:
                month_end = date(cursor_year, cursor_month + 1, 1) - timedelta(days=1)
            if month_end > anchor:
                month_end = anchor
            data = _aggregate(db, month_start, month_end, class_id)
            reported = sum(v["reported"] for v in data.values())
            total = sum(v["total"] for v in data.values())
            present = sum(v["present"] for v in data.values())
            absent = sum(v["absent"] for v in data.values())
            days = (month_end - month_start).days + 1
            expected = dorm_total * days
            items.append(
                {
                    "key": month_start.strftime("%Y-%m"),
                    "label": f"{cursor_month}月",
                    "full_label": f"{cursor_year}年{cursor_month}月",
                    "reported": reported,
                    "total": total,
                    "present": present,
                    "absent": absent,
                    "dorm_total": dorm_total,
                    "rate": round(reported / expected * 100, 1) if expected else 0.0,
                    "days": days,
                }
            )
            cursor_month += 1
            if cursor_month > 12:
                cursor_month = 1
                cursor_year += 1

    return {"granularity": granularity, "anchor": anchor.strftime("%Y-%m-%d"), "items": items}


def dorm_ranking(db: Session, start: date, end: date, class_id: int = 0) -> list[dict[str, Any]]:
    """区间内各宿舍填报情况排行（用于发现长期不填报的宿舍）。"""
    dorms = list_dorms(db, class_id=class_id)
    days = (end - start).days + 1
    stmt = (
        select(Report)
        .where(Report.report_date >= start, Report.report_date <= end)
        .order_by(Report.report_date)
    )
    if int(class_id or 0) > 0:
        stmt = stmt.join(Dorm, Report.dorm_id == Dorm.id).where(Dorm.class_id == int(class_id))
    rows = db.execute(stmt).scalars()
    agg: dict[int, dict[str, Any]] = {}
    for report in rows:
        item = agg.setdefault(
            report.dorm_id, {"reported": 0, "absent_days": 0, "absent_total": 0, "last": None}
        )
        item["reported"] += 1
        if report.absent_count:
            item["absent_days"] += 1
            item["absent_total"] += report.absent_count
        item["last"] = report.report_date
    result: list[dict[str, Any]] = []
    for dorm in dorms:
        item = agg.get(dorm.id, {"reported": 0, "absent_days": 0, "absent_total": 0, "last": None})
        result.append(
            {
                "dorm_id": dorm.id,
                "room_no": dorm.room_no,
                "leader_name": dorm.leader_name,
                "leader_phone": dorm.leader_phone,
                "days": days,
                "reported": item["reported"],
                "missing": days - item["reported"],
                "rate": round(item["reported"] / days * 100, 1) if days else 0.0,
                "absent_days": item["absent_days"],
                "absent_total": item["absent_total"],
                "last_report": item["last"].strftime("%Y-%m-%d") if item["last"] else "",
            }
        )
    result.sort(key=lambda x: (x["rate"], x["room_no"]))
    return result


def hourly_distribution(db: Session, start: date, end: date, class_id: int = 0) -> list[dict[str, Any]]:
    """填报时间分布（看宿舍长习惯几点填）。"""
    stmt = (
        select(Report.submitted_at)
        .where(Report.report_date >= start, Report.report_date <= end)
    )
    if int(class_id or 0) > 0:
        stmt = stmt.join(Dorm, Report.dorm_id == Dorm.id).where(Dorm.class_id == int(class_id))
    rows = db.execute(stmt).scalars()
    buckets = {"19点前": 0, "19-20点": 0, "20-21点": 0, "21-22点": 0, "22-23点": 0, "23点后": 0}
    for value in rows:
        if not value:
            continue
        hour = value.hour
        if hour < 19:
            buckets["19点前"] += 1
        elif hour < 20:
            buckets["19-20点"] += 1
        elif hour < 21:
            buckets["20-21点"] += 1
        elif hour < 22:
            buckets["21-22点"] += 1
        elif hour < 23:
            buckets["22-23点"] += 1
        else:
            buckets["23点后"] += 1
    return [{"label": key, "value": value} for key, value in buckets.items()]


def reports_in_range(
    db: Session,
    start: date,
    end: date,
    *,
    dorm_id: int | None = None,
    only_incomplete: bool = False,
    keyword: str = "",
    class_id: int = 0,
) -> list[dict[str, Any]]:
    stmt = (
        select(Report)
        .where(Report.report_date >= start, Report.report_date <= end)
        .order_by(Report.report_date.desc(), Report.id.desc())
    )
    if dorm_id:
        stmt = stmt.where(Report.dorm_id == dorm_id)
    if int(class_id or 0) > 0:
        stmt = stmt.join(Dorm, Report.dorm_id == Dorm.id).where(Dorm.class_id == int(class_id))
    if only_incomplete:
        stmt = stmt.where(Report.is_complete.is_(False))
    rows = list(db.execute(stmt).scalars())
    dorms = {d.id: d for d in list_dorms(db, active_only=False, class_id=class_id)}
    result = []
    for report in rows:
        item = serialize_report(report, dorms.get(report.dorm_id))
        if keyword:
            haystack = f"{item['room_no']}{item['absent_names']}{item['note']}{item['submitter']}"
            if keyword not in haystack:
                continue
        result.append(item)
    return result


def absent_records(db: Session, start: date, end: date, class_id: int = 0) -> list[dict[str, Any]]:
    """区间内所有缺席明细，用于统计经常不在的人。"""
    stmt = select(Report).where(
        Report.report_date >= start,
        Report.report_date <= end,
        Report.absent_count > 0,
    )
    if int(class_id or 0) > 0:
        stmt = stmt.join(Dorm, Report.dorm_id == Dorm.id).where(Dorm.class_id == int(class_id))
    rows = db.execute(stmt.order_by(Report.report_date)).scalars()
    dorms = {d.id: d for d in list_dorms(db, active_only=False, class_id=class_id)}
    result: list[dict[str, Any]] = []
    for report in rows:
        dorm = dorms.get(report.dorm_id)
        result.append(
            {
                "date": report.report_date.strftime("%Y-%m-%d"),
                "room_no": dorm.room_no if dorm else "",
                "absent_names": report.absent_names,
                "absent_count": report.absent_count,
                "note": html.escape(report.note or ""),
                "note_raw": report.note,
                "submitter": report.submitter,
            }
        )
    return result


def recent_submissions(db: Session, limit: int = 15, class_id: int = 0) -> list[dict[str, Any]]:
    dorms = {d.id: d for d in list_dorms(db, active_only=False, class_id=class_id)}
    stmt = select(Report).order_by(Report.submitted_at.desc(), Report.id.desc()).limit(limit)
    if int(class_id or 0) > 0:
        stmt = select(Report).join(Dorm, Report.dorm_id == Dorm.id).where(
            Dorm.class_id == int(class_id)
        ).order_by(Report.submitted_at.desc(), Report.id.desc()).limit(limit)
    rows = db.execute(stmt).scalars()
    return [serialize_report(row, dorms.get(row.dorm_id)) for row in rows]
