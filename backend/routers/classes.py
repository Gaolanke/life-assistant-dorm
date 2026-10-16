"""班级管理：多班级的增删改查、QQ 群绑定、每班数据概览。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Account
from ..security import client_context, require_admin
from ..services import class_service, settings_service as ss
from ..util import AppError, client_ip

router = APIRouter(prefix="/api/classes", tags=["classes"])


class ClassBody(BaseModel):
    name: str | None = None
    note: str | None = None
    sort_order: int | None = None
    active: bool | None = None
    settings: dict[str, Any] = {}  # 班级级配置：qq_report_time 等


@router.get("")
def list_classes(
    db: Session = Depends(get_db),
    _: Account = Depends(require_admin),
):
    """全部班级 + 每个班的数据统计。"""
    items = [class_service.serialize_class(db, row) for row in class_service.list_classes(db, active_only=False)]
    return {"ok": True, "items": items, "total": len(items)}


@router.post("")
def create_class(
    body: ClassBody,
    request: Request,
    db: Session = Depends(get_db),
    _: Account = Depends(require_admin),
):
    row = class_service.create_class(db, body.model_dump(exclude_none=True))
    _save_class_settings(db, row.id, body.settings)
    ss.write_audit(
        db,
        actor=client_context(request)["display_name"],
        role="admin",
        action="新增班级",
        target=row.name,
        ip=client_ip(request),
    )
    db.commit()
    return {"ok": True, "item": class_service.serialize_class(db, row), "message": f"已创建班级「{row.name}」"}


@router.get("/{class_id}")
def get_class_detail(
    class_id: int,
    db: Session = Depends(get_db),
    _: Account = Depends(require_admin),
):
    """单个班级详情（含统计和生效中的班级级配置）。"""
    row = class_service.get_class(db, class_id)
    if row is None:
        raise AppError("班级不存在", 404)
    data = class_service.serialize_class(db, row)
    data["settings"] = {
        "qq_report_time": ss.get_setting(db, "qq_report_time", class_id=row.id),
    }
    return {"ok": True, "item": data}


@router.put("/{class_id}")
def update_class(
    class_id: int,
    body: ClassBody,
    request: Request,
    db: Session = Depends(get_db),
    _: Account = Depends(require_admin),
):
    payload = body.model_dump(exclude_none=True)
    settings = payload.pop("settings", {})
    row = class_service.update_class(db, class_id, payload)
    _save_class_settings(db, row.id, settings)
    ss.write_audit(
        db,
        actor=client_context(request)["display_name"],
        role="admin",
        action="修改班级",
        target=row.name,
        ip=client_ip(request),
    )
    db.commit()
    return {"ok": True, "item": class_service.serialize_class(db, row), "message": "班级信息已保存"}


@router.delete("/{class_id}")
def delete_class(
    class_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: Account = Depends(require_admin),
):
    result = class_service.delete_class(db, class_id)
    ss.write_audit(
        db,
        actor=client_context(request)["display_name"],
        role="admin",
        action="删除班级",
        target=result.get("name", ""),
        detail=f"宿舍 {result.get('dorm_count')}、班费明细 {result.get('entry_count')}",
        ip=client_ip(request),
    )
    db.commit()
    return {"ok": True, "message": f"已删除班级「{result.get('name')}」"}


def _save_class_settings(db: Session, class_id: int, settings: dict[str, Any]) -> None:
    """保存班级级配置（目前只有汇报时间 qq_report_time；保存后重排定时任务）。"""
    if not settings:
        return
    if "qq_report_time" in settings and settings["qq_report_time"]:
        value = ss.normalize_time(settings["qq_report_time"], "群汇报时间")
        ss.set_setting(db, ss.class_key(class_id, "qq_report_time"), value)
    try:
        from .. import scheduler as sched

        sched.reload_schedule()
    except Exception:  # noqa: BLE001
        pass
