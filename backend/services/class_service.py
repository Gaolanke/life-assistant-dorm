"""班级管理：多班级数据隔离的根服务。

- 启动时把没有班级的老数据归入「默认班级」（名称取自原「班级名称」配置）
- 宿舍 / 班费 / 定时提醒 / QQ 群绑定都挂在班级下
- 班级级配置（定时提醒、汇报时间）存成 class:<id>:<key> 配置键，见 settings_service
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import BotGroup, Dorm, FundEntry, FundSetting, Member, SchoolClass
from ..util import AppError


# --------------------------------------------------------------------------
# 默认班级 / 读取
# --------------------------------------------------------------------------
def ensure_default_class(db: Session) -> SchoolClass:
    """确保至少有一个班级；老数据（class_id=0）全部归入它。幂等。"""
    first = db.execute(select(SchoolClass).order_by(SchoolClass.sort_order, SchoolClass.id)).scalars().first()
    if first is not None:
        _adopt_orphans(db, first.id)
        return first

    from . import settings_service as ss

    name = (ss.get_setting(db, "class_name") or "").strip() or "默认班级"
    row = SchoolClass(name=name[:80], note="升级时自动创建", sort_order=0)
    db.add(row)
    db.commit()
    db.refresh(row)
    _adopt_orphans(db, row.id)
    return row


def _adopt_orphans(db: Session, class_id: int) -> None:
    """把 class_id=0 的老数据挂到默认班级下。"""
    changed = False
    for model in (Dorm, FundSetting, FundEntry):
        rows = db.execute(select(model).where(model.class_id == 0)).scalars()
        for row in rows:
            row.class_id = class_id
            changed = True
    if changed:
        db.commit()


def default_class_id(db: Session) -> int:
    row = db.execute(select(SchoolClass).order_by(SchoolClass.sort_order, SchoolClass.id)).scalars().first()
    return row.id if row else 0


def resolve_class_id(db: Session, raw: Any) -> int:
    """把请求里的 class_id 参数落成有效班级 id：0/缺失 → 默认班级。"""
    try:
        value = int(raw or 0)
    except (TypeError, ValueError):
        value = 0
    if value > 0 and db.get(SchoolClass, value) is not None:
        return value
    return default_class_id(db)


def get_class(db: Session, class_id: int) -> SchoolClass | None:
    return db.get(SchoolClass, int(class_id)) if class_id else None


def list_classes(db: Session, active_only: bool = True) -> list[SchoolClass]:
    stmt = select(SchoolClass).order_by(SchoolClass.sort_order, SchoolClass.id)
    if active_only:
        stmt = stmt.where(SchoolClass.active.is_(True))
    return list(db.execute(stmt).scalars())


# --------------------------------------------------------------------------
# QQ 群绑定
# --------------------------------------------------------------------------
def class_group_openids(db: Session, class_id: int) -> list[str]:
    """绑定到这个班级的群 openid（推送目标按班级取）。"""
    rows = db.execute(
        select(BotGroup).where(BotGroup.class_id == class_id, BotGroup.group_openid != "")
    ).scalars()
    result: list[str] = []
    for row in rows:
        if row.group_openid not in result:
            result.append(row.group_openid)
    return result


def any_class_has_bound_group(db: Session) -> bool:
    """是否有任何一个班级绑定了 QQ 群。

    一旦进入「按班绑群」的用法，班级推送就不再回退全局群列表，
    避免 A 班的汇报因为没绑群而被发进 B 班的群里。
    """
    row = db.execute(select(BotGroup.id).where(BotGroup.class_id > 0).limit(1)).first()
    return row is not None


def class_by_group(db: Session, group_openid: str) -> SchoolClass | None:
    """根据群 openid 反查绑定的班级（机器人收到群消息时用）。"""
    if not group_openid:
        return None
    row = db.execute(
        select(BotGroup).where(BotGroup.group_openid == group_openid, BotGroup.class_id > 0)
    ).scalars().first()
    return db.get(SchoolClass, row.class_id) if row else None


# --------------------------------------------------------------------------
# 统计
# --------------------------------------------------------------------------
def class_stats(db: Session, class_id: int) -> dict[str, Any]:
    dorm_count = db.execute(
        select(func.count(Dorm.id)).where(Dorm.class_id == class_id, Dorm.active.is_(True))
    ).scalar() or 0
    member_count = db.execute(
        select(func.count(Member.id))
        .join(Dorm, Member.dorm_id == Dorm.id)
        .where(Dorm.class_id == class_id, Member.active.is_(True))
    ).scalar() or 0
    fund_entries = db.execute(
        select(func.count(FundEntry.id)).where(FundEntry.class_id == class_id)
    ).scalar() or 0
    groups = class_group_openids(db, class_id)
    return {
        "dorm_count": int(dorm_count),
        "member_count": int(member_count),
        "fund_entry_count": int(fund_entries),
        "group_count": len(groups),
        "group_openids": groups,
    }


def serialize_class(db: Session, row: SchoolClass) -> dict[str, Any]:
    from . import settings_service as ss

    data = {
        "id": row.id,
        "name": row.name,
        "note": row.note,
        "sort_order": row.sort_order,
        "active": row.active,
        "created_at": row.created_at.strftime("%Y-%m-%d %H:%M:%S") if row.created_at else "",
    }
    data.update(class_stats(db, row.id))
    # 生效中的班级级时间（班级没单独设就回退全局值）
    data["qq_report_time"] = ss.get_setting(db, "qq_report_time", class_id=row.id)
    return data


# --------------------------------------------------------------------------
# 增删改
# --------------------------------------------------------------------------
def create_class(db: Session, payload: dict[str, Any]) -> SchoolClass:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise AppError("班级名称不能为空")
    if len(name) > 80:
        raise AppError("班级名称太长了（最多 80 字）")
    dup = db.execute(select(SchoolClass).where(SchoolClass.name == name)).scalar_one_or_none()
    if dup:
        raise AppError(f"已有同名班级「{name}」")
    row = SchoolClass(
        name=name,
        note=str(payload.get("note") or "").strip()[:300],
        sort_order=int(payload.get("sort_order") or 0),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


CLASS_EDITABLE_FIELDS = {"name", "note", "sort_order", "active"}


def update_class(db: Session, class_id: int, payload: dict[str, Any]) -> SchoolClass:
    row = get_class(db, class_id)
    if row is None:
        raise AppError("班级不存在", 404)
    if "name" in payload and payload["name"] is not None:
        name = str(payload["name"]).strip()
        if not name:
            raise AppError("班级名称不能为空")
        dup = db.execute(
            select(SchoolClass).where(SchoolClass.name == name, SchoolClass.id != row.id)
        ).scalar_one_or_none()
        if dup:
            raise AppError(f"已有同名班级「{name}」")
        row.name = name[:80]
    if "note" in payload and payload["note"] is not None:
        row.note = str(payload["note"]).strip()[:300]
    if "sort_order" in payload and payload["sort_order"] is not None:
        row.sort_order = int(payload["sort_order"] or 0)
    if "active" in payload and payload["active"] is not None:
        row.active = bool(payload["active"])
    db.commit()
    db.refresh(row)
    return row


def delete_class(db: Session, class_id: int) -> dict[str, Any]:
    """删除班级。里面还有宿舍或班费明细时不允许删（先搬走或删掉）。"""
    row = get_class(db, class_id)
    if row is None:
        raise AppError("班级不存在", 404)
    total = db.execute(select(func.count(SchoolClass.id))).scalar() or 0
    if total <= 1:
        raise AppError("至少要保留一个班级（可以把宿舍搬到别的班级后再删）")
    dorm_count = db.execute(select(func.count(Dorm.id)).where(Dorm.class_id == class_id)).scalar() or 0
    entry_count = db.execute(
        select(func.count(FundEntry.id)).where(FundEntry.class_id == class_id)
    ).scalar() or 0
    if dorm_count or entry_count:
        raise AppError(
            f"班级「{row.name}」里还有 {dorm_count} 间宿舍、{entry_count} 条班费明细，"
            "先把它们搬到其他班级（或删掉）再删除班级"
        )
    fund_row = db.execute(
        select(FundSetting).where(FundSetting.class_id == class_id)
    ).scalars().first()
    if fund_row is not None:
        db.delete(fund_row)
    # 群绑定解除（群记录保留，只是不再属于这个班）
    for group in db.execute(select(BotGroup).where(BotGroup.class_id == class_id)).scalars():
        group.class_id = 0
    # 清掉班级级配置键（class:<id>:*）
    _delete_class_settings(db, class_id)
    name = row.name
    db.delete(row)
    db.commit()
    return {"name": name, "dorm_count": int(dorm_count), "entry_count": int(entry_count)}


def _delete_class_settings(db: Session, class_id: int) -> None:
    from ..models import Setting

    prefix = f"class:{class_id}:"
    for row in db.execute(select(Setting)).scalars():
        if str(row.key).startswith(prefix):
            db.delete(row)
