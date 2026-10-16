"""宿舍与人员管理、Excel 批量导入。"""
from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import excel_util
from ..database import get_db
from ..models import Dorm, Member, Report
from ..security import (
    assert_dorm_access,
    client_context,
    is_admin_port,
    require_admin,
)
from ..services import class_service, report_service, settings_service as ss
from ..util import AppError, client_device, client_ip, now_local

router = APIRouter(prefix="/api", tags=["dorms"])

# 导入预览缓存：token -> 解析结果
_IMPORT_CACHE: dict[str, dict[str, Any]] = {}


class DormBody(BaseModel):
    room_no: str = ""
    room_label: str = ""
    building: str = ""
    leader_name: str = ""
    leader_phone: str = ""
    qq_group_id: str = ""
    note: str = ""
    sort_order: int = 0
    active: bool = True
    class_id: int = 0  # 属于哪个班级（0 = 默认班级）


class MemberBody(BaseModel):
    name: str = ""
    student_no: str = ""
    phone: str = ""
    room_no: str = ""
    role: str = "成员"
    note: str = ""
    active: bool = True


class ImportCommitBody(BaseModel):
    token: str
    strategy: str = "merge"  # merge 追加 / overwrite 覆盖这些宿舍的名单
    update_member: bool = True


def dorm_to_dict(db: Session, dorm: Dorm, with_members: bool = True) -> dict[str, Any]:
    members = report_service.dorm_members(db, dorm.id, active_only=False)
    cls = class_service.get_class(db, dorm.class_id or 0)
    data: dict[str, Any] = {
        "id": dorm.id,
        "class_id": int(dorm.class_id or 0),
        "class_name": cls.name if cls else "",
        "room_no": dorm.room_no,
        "room_label": dorm.room_label,
        "building": dorm.building,
        "leader_name": dorm.leader_name,
        "leader_phone": dorm.leader_phone,
        "qq_group_id": dorm.qq_group_id,
        "note": dorm.note,
        "sort_order": dorm.sort_order,
        "active": dorm.active,
        "member_count": len([m for m in members if m.active]),
        "label": dorm.label,
        "locked": bool(dorm.leader_password),  # 设了验证密码 → 操作需要寝室长账户
        "created_at": dorm.created_at.strftime("%Y-%m-%d %H:%M:%S") if dorm.created_at else "",
    }
    if with_members:
        data["members"] = [member_to_dict(m) for m in members]
    return data


def member_to_dict(member: Member) -> dict[str, Any]:
    return {
        "id": member.id,
        "dorm_id": member.dorm_id,
        "name": member.name,
        "student_no": member.student_no,
        "phone": member.phone,
        "room_no": member.room_no,
        "role": member.role,
        "note": member.note,
        "active": member.active,
    }


# --------------------------------------------------------------------------
# 宿舍
# --------------------------------------------------------------------------
@router.get("/dorms")
def list_dorms(
    db: Session = Depends(get_db),
    with_members: bool = True,
    active_only: bool = False,
    class_id: int = 0,
):
    """宿舍列表。class_id=0（不传）时返回默认班级的宿舍；传 -1 返回全部班级。"""
    if class_id == -1:
        cid = -1
    else:
        cid = class_service.resolve_class_id(db, class_id)
    dorms = report_service.list_dorms(db, active_only=active_only, class_id=cid)
    items = [dorm_to_dict(db, dorm, with_members) for dorm in dorms]
    return {
        "ok": True,
        "class_id": cid,
        "items": items,
        "total": len(items),
        "member_total": len(list(db.execute(select(Member.id)).scalars())),
    }


@router.post("/dorms")
def create_dorm(
    body: DormBody,
    request: Request,
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    room_no = body.room_no.strip()
    if not room_no:
        raise AppError("宿舍号不能为空")
    cid = class_service.resolve_class_id(db, body.class_id)
    if db.execute(
        select(Dorm).where(Dorm.room_no == room_no, Dorm.class_id == cid)
    ).scalar_one_or_none():
        raise AppError(f"当前班级里已有宿舍 {room_no}")
    dorm = Dorm(
        room_no=room_no,
        room_label=body.room_label.strip(),
        building=body.building.strip(),
        leader_name=body.leader_name.strip(),
        leader_phone=body.leader_phone.strip(),
        qq_group_id=body.qq_group_id.strip(),
        note=body.note.strip(),
        sort_order=body.sort_order,
        active=body.active,
        class_id=cid,
    )
    db.add(dorm)
    db.commit()
    db.refresh(dorm)
    ss.write_audit(
        db,
        actor=client_context(request)["display_name"],
        role="public",
        action="新增宿舍",
        target=room_no,
        ip=client_ip(request),
    )
    db.commit()
    return {"ok": True, "item": dorm_to_dict(db, dorm), "message": f"已新增宿舍 {room_no}"}


@router.put("/dorms/{dorm_id}")
def update_dorm(
    dorm_id: int,
    body: DormBody,
    request: Request,
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    dorm = db.get(Dorm, dorm_id)
    if dorm is None:
        raise AppError("宿舍不存在", 404)
    room_no = body.room_no.strip() or dorm.room_no
    conflict = db.execute(
        select(Dorm).where(
            Dorm.room_no == room_no,
            Dorm.id != dorm_id,
            Dorm.class_id == (dorm.class_id or 0),
        )
    ).scalar_one_or_none()
    if conflict:
        raise AppError(f"同一班级里已有宿舍号 {room_no}")
    old_room_no = dorm.room_no
    dorm.room_no = room_no
    dorm.room_label = body.room_label.strip()
    dorm.building = body.building.strip()
    dorm.leader_name = body.leader_name.strip()
    dorm.leader_phone = body.leader_phone.strip()
    dorm.qq_group_id = body.qq_group_id.strip()
    dorm.note = body.note.strip()
    dorm.sort_order = body.sort_order
    dorm.active = body.active
    # 同步成员表里冗余的宿舍号
    for member in report_service.dorm_members(db, dorm.id, active_only=False):
        member.room_no = room_no
    db.commit()
    ss.write_audit(
        db,
        actor=client_context(request)["display_name"],
        role="public",
        action="修改宿舍",
        target=room_no,
        ip=client_ip(request),
    )
    db.commit()
    return {"ok": True, "item": dorm_to_dict(db, dorm), "message": "已保存"}


@router.delete("/dorms/{dorm_id}")
def delete_dorm(
    dorm_id: int,
    request: Request,
    db: Session = Depends(get_db),
    purge_reports: bool = False,
    _: dict = Depends(require_admin),
):
    dorm = db.get(Dorm, dorm_id)
    if dorm is None:
        raise AppError("宿舍不存在", 404)
    room_no = dorm.room_no
    if purge_reports:
        for member in report_service.dorm_members(db, dorm.id, active_only=False):
            db.delete(member)
        task = db.execute(select(Report).where(Report.dorm_id == dorm.id)).scalars()
        for report in task:
            db.delete(report)
    else:
        # 保留历史填报，只把宿舍停用
        dorm.active = False
        db.commit()
        ss.write_audit(
            db,
            actor=client_context(request)["display_name"],
            role="public",
            action="停用宿舍（保留历史填报）",
            target=room_no,
            ip=client_ip(request),
        )
        db.commit()
        return {"ok": True, "message": f"宿舍 {room_no} 已停用，历史填报数据保留"}
    db.delete(dorm)
    db.commit()
    ss.write_audit(
        db,
        actor=client_context(request)["display_name"],
        role="public",
        action="彻底删除宿舍",
        target=room_no,
        ip=client_ip(request),
    )
    db.commit()
    return {"ok": True, "message": f"宿舍 {room_no} 及其人员、填报记录已删除"}


@router.post("/dorms/{dorm_id}/leader")
def set_dorm_leader(
    dorm_id: int,
    member_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    """把某个成员标记为该宿舍的宿舍长（不需要账号，只用于汇报和催填联系人）。"""
    dorm = db.get(Dorm, dorm_id)
    if dorm is None:
        raise AppError("宿舍不存在", 404)
    members = report_service.dorm_members(db, dorm.id, active_only=False)
    target = next((m for m in members if m.id == member_id), None)
    if target is None:
        raise AppError("成员不存在或不属于这个宿舍", 404)
    for member in members:
        member.role = "成员"
    target.role = "宿舍长"
    dorm.leader_name = target.name
    dorm.leader_phone = target.phone or dorm.leader_phone
    db.commit()
    ss.write_audit(
        db,
        actor=client_context(request)["display_name"],
        role="public",
        action="指定宿舍长",
        target=f"{dorm.room_no} {target.name}",
        ip=client_ip(request),
    )
    db.commit()
    return {
        "ok": True,
        "item": dorm_to_dict(db, dorm),
        "message": f"已把 {target.name} 设为 {dorm.room_no} 的宿舍长",
    }


# --------------------------------------------------------------------------
# 成员
# --------------------------------------------------------------------------
@router.post("/dorms/{dorm_id}/members")
def add_member(
    dorm_id: int,
    body: MemberBody,
    request: Request,
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    dorm = db.get(Dorm, dorm_id)
    if dorm is None:
        raise AppError("宿舍不存在", 404)
    if not body.name.strip():
        raise AppError("姓名不能为空")
    member = Member(
        dorm_id=dorm.id,
        name=body.name.strip(),
        student_no=body.student_no.strip(),
        phone=body.phone.strip(),
        room_no=body.room_no.strip() or dorm.room_no,
        role=body.role.strip() or "成员",
        note=body.note.strip(),
        active=body.active,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    ss.write_audit(
        db,
        actor=client_context(request)["display_name"],
        role="public",
        action="新增成员",
        target=f"{dorm.room_no} {member.name}",
        ip=client_ip(request),
    )
    db.commit()
    return {"ok": True, "item": member_to_dict(member), "message": f"已添加 {member.name}"}


@router.put("/members/{member_id}")
def update_member(
    member_id: int,
    body: MemberBody,
    request: Request,
    db: Session = Depends(get_db),
):
    member = db.get(Member, member_id)
    if member is None:
        raise AppError("成员不存在", 404)
    # 管理端口始终可改；公开端口下，设了验证密码的寝室需要寝室长账户，没设密码的谁都能改
    if not is_admin_port(request):
        dorm = db.get(Dorm, member.dorm_id)
        if dorm is None:
            raise AppError("寝室不存在", 404)
        assert_dorm_access(db, request, dorm, what="修改成员")
    if not body.name.strip():
        raise AppError("姓名不能为空")
    member.name = body.name.strip()
    member.student_no = body.student_no.strip()
    member.phone = body.phone.strip()
    member.room_no = body.room_no.strip() or member.room_no
    member.role = body.role.strip() or "成员"
    member.note = body.note.strip()
    member.active = body.active
    db.commit()
    ss.write_audit(
        db,
        actor=client_context(request)["display_name"],
        role="public",
        action="修改成员",
        target=member.name,
        ip=client_ip(request),
    )
    db.commit()
    return {"ok": True, "item": member_to_dict(member), "message": "已保存"}


@router.delete("/members/{member_id}")
def delete_member(
    member_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    member = db.get(Member, member_id)
    if member is None:
        raise AppError("成员不存在", 404)
    name = member.name
    dorm_id = member.dorm_id
    db.delete(member)
    db.commit()
    ss.write_audit(
        db,
        actor=client_context(request)["display_name"],
        role="public",
        action="删除成员",
        target=name,
        ip=client_ip(request),
        detail=f"dorm_id={dorm_id}",
    )
    db.commit()
    return {"ok": True, "message": f"已删除 {name}"}


@router.post("/dorms/{dorm_id}/members/batch-delete")
def batch_delete_members(
    dorm_id: int,
    ids: list[int],
    request: Request,
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    count = 0
    for member_id in ids:
        member = db.get(Member, member_id)
        if member and member.dorm_id == dorm_id:
            db.delete(member)
            count += 1
    db.commit()
    ss.write_audit(
        db,
        actor=client_context(request)["display_name"],
        role="public",
        action="批量删除成员",
        target=f"dorm_id={dorm_id}",
        detail=f"删除 {count} 人",
        ip=client_ip(request),
    )
    db.commit()
    return {"ok": True, "message": f"已删除 {count} 人"}


# --------------------------------------------------------------------------
# Excel 导入 / 导出
# --------------------------------------------------------------------------
@router.get("/members/template")
def download_template(_: dict = Depends(require_admin)):
    content = excel_util.build_template()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=member_template.xlsx"},
    )


@router.get("/members/export")
def export_members(
    db: Session = Depends(get_db),
    class_id: int = 0,
    _: dict = Depends(require_admin),
):
    cid = class_service.resolve_class_id(db, class_id)
    dorms = [
        dorm_to_dict(db, dorm, True)
        for dorm in report_service.list_dorms(db, active_only=False, class_id=cid)
    ]
    content = excel_util.export_members(dorms)
    stamp = now_local().strftime("%Y%m%d_%H%M")
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=members_{stamp}.xlsx",
        },
    )


@router.post("/members/import/preview")
async def import_preview(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    class_id: int = 0,
    _: dict = Depends(require_admin),
):
    content = await file.read()
    if len(content) > 12 * 1024 * 1024:
        raise AppError("文件太大了（超过 12MB）")
    cid = class_service.resolve_class_id(db, class_id)
    headers, rows, sheet = excel_util.read_table(content, file.filename or "")
    mapping, mapped = excel_util.map_rows(headers, rows)
    if not mapping.get("name") or not mapping.get("room_no"):
        raise AppError(
            f"没找到必需的列。识别到的列头：{'、'.join(headers[:10])}；"
            "请确保有“姓名”和“宿舍号”两列，或先下载模板。"
        )

    groups: dict[str, list[dict[str, Any]]] = {}
    labels: dict[str, str] = {}
    buildings: dict[str, str] = {}
    skipped: list[str] = []
    for index, item in enumerate(mapped, start=2):
        name = (item.get("name") or "").strip()
        raw_room = (item.get("room_no") or "").strip()
        if not name or not raw_room:
            skipped.append(f"第{index}行：姓名或宿舍号为空（已跳过）")
            continue
        room_no, building, room_label = excel_util.parse_room_label(raw_room)
        room_no = room_no.strip()
        if not room_no:
            skipped.append(f"第{index}行：宿舍号“{raw_room}”无法识别")
            continue
        labels.setdefault(room_no, room_label or raw_room)
        if building:
            buildings.setdefault(room_no, building)
        groups.setdefault(room_no, []).append(
            {
                "name": name,
                "student_no": (item.get("student_no") or "").strip(),
                "phone": (item.get("phone") or "").strip(),
                "role": (item.get("role") or "成员").strip() or "成员",
                "class_name": (item.get("grade") or "").strip(),
            }
        )
    if not groups:
        raise AppError("没有解析出任何有效数据行")

    existing_map = {
        dorm.room_no: dorm
        for dorm in db.execute(select(Dorm).where(Dorm.class_id == cid)).scalars()
    }
    preview_groups = []
    for room_no, members in groups.items():
        dorm = existing_map.get(room_no)
        current = (
            [m.name for m in report_service.dorm_members(db, dorm.id, active_only=False)]
            if dorm
            else []
        )
        incoming = [m["name"] for m in members]
        leaders = [m["name"] for m in members if m["role"] == "宿舍长"]
        preview_groups.append(
            {
                "room_no": room_no,
                "room_label": labels.get(room_no, ""),
                "building": buildings.get(room_no, ""),
                "exists": bool(dorm),
                "dorm_id": dorm.id if dorm else 0,
                "leader_name": (dorm.leader_name if dorm else "") or (leaders[0] if leaders else ""),
                "incoming_count": len(members),
                "incoming": incoming,
                "current": current,
                "new_members": [n for n in incoming if n not in current],
                "duplicate": [n for n in incoming if n in current],
                "leaders": leaders,
                "members": members,
            }
        )

    token = secrets.token_urlsafe(16)
    _IMPORT_CACHE[token] = {
        "groups": groups,
        "labels": labels,
        "buildings": buildings,
        "class_id": cid,
        "created_at": now_local(),
        "filename": file.filename,
    }
    # 只保留最近 10 次解析结果
    if len(_IMPORT_CACHE) > 10:
        oldest = sorted(_IMPORT_CACHE.items(), key=lambda kv: kv[1]["created_at"])[0][0]
        _IMPORT_CACHE.pop(oldest, None)

    return {
        "ok": True,
        "token": token,
        "sheet": sheet,
        "headers": headers,
        "mapping": mapping,
        "total_rows": len(mapped),
        "total_dorms": len(groups),
        "total_members": sum(len(v) for v in groups.values()),
        "skipped": skipped[:30],
        "groups": preview_groups,
    }


@router.post("/members/import/commit")
def import_commit(
    body: ImportCommitBody,
    request: Request,
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    cached = _IMPORT_CACHE.get(body.token)
    if not cached:
        raise AppError("导入会话已过期，请重新上传文件")
    strategy = body.strategy if body.strategy in {"merge", "overwrite"} else "merge"
    cid = class_service.resolve_class_id(db, cached.get("class_id") or 0)
    created_dorms = 0
    created_members = 0
    updated_members = 0
    labels = cached.get("labels", {})
    buildings = cached.get("buildings", {})
    for room_no, members in cached["groups"].items():
        dorm = db.execute(
            select(Dorm).where(Dorm.room_no == room_no, Dorm.class_id == cid)
        ).scalar_one_or_none()
        if dorm is None:
            dorm = Dorm(
                room_no=room_no,
                room_label=labels.get(room_no, ""),
                building=buildings.get(room_no, ""),
                class_id=cid,
            )
            db.add(dorm)
            db.commit()
            db.refresh(dorm)
            created_dorms += 1
        else:
            if labels.get(room_no) and not dorm.room_label:
                dorm.room_label = labels[room_no]
            if buildings.get(room_no) and not dorm.building:
                dorm.building = buildings[room_no]
            db.commit()
        existing = report_service.dorm_members(db, dorm.id, active_only=False)
        if strategy == "overwrite":
            for member in existing:
                db.delete(member)
            db.commit()
            existing = []
        by_name = {m.name: m for m in existing}
        by_no = {m.student_no: m for m in existing if m.student_no}
        leaders = [m for m in members if m["role"] == "宿舍长"]
        if leaders and not dorm.leader_name:
            dorm.leader_name = leaders[0]["name"]
            first = next((m for m in members if m["name"] == leaders[0]["name"]), None)
            if first and first.get("phone"):
                dorm.leader_phone = first["phone"]
        for item in members:
            match = by_name.get(item["name"]) or (by_no.get(item["student_no"]) if item["student_no"] else None)
            if match and body.update_member:
                match.student_no = item["student_no"] or match.student_no
                match.phone = item["phone"] or match.phone
                match.room_no = room_no
                match.role = item["role"] or match.role
                updated_members += 1
            elif match:
                continue
            else:
                db.add(
                    Member(
                        dorm_id=dorm.id,
                        name=item["name"],
                        student_no=item["student_no"],
                        phone=item["phone"],
                        room_no=room_no,
                        role=item["role"] or "成员",
                    )
                )
                created_members += 1
        db.commit()
    _IMPORT_CACHE.pop(body.token, None)
    ss.write_audit(
        db,
        actor=client_context(request)["display_name"],
        role="public",
        action="导入人员信息",
        target=cached.get("filename", ""),
        detail=f"新增宿舍 {created_dorms}，新增人员 {created_members}，更新 {updated_members}，策略 {strategy}",
        ip=client_ip(request),
    )
    db.commit()
    return {
        "ok": True,
        "message": f"导入完成：新增宿舍 {created_dorms} 间，新增人员 {created_members} 人，更新 {updated_members} 人",
        "created_dorms": created_dorms,
        "created_members": created_members,
        "updated_members": updated_members,
    }
