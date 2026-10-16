"""配置读写与模板渲染。"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..defaults import DEFAULTS, REMINDER_PRESETS, TEMPLATE_VARS
from ..models import AuditLog, Setting
from ..util import TZ, AppError, client_ip, now_local, parse_date


def ensure_settings(db: Session) -> None:
    """补齐缺失的配置项，并做轻量升级（新版本新增配置/模板自动跟上）。"""
    existing = {row.key for row in db.execute(select(Setting)).scalars()}
    changed = False
    for key, (value, group, description) in DEFAULTS.items():
        if key not in existing:
            db.add(Setting(key=key, value=value, group=group, description=description))
            changed = True
    if changed:
        db.commit()
    _migrate(db)


def _migrate(db: Session) -> None:
    """老版本升级：只在用户没改过模板时补上新字段，避免覆盖自定义内容。"""
    row = db.get(Setting, "tpl_group_report")
    if row is not None and row.value and "{school}" not in row.value:
        marker = "【{date} 宿舍晚归情况汇报】\n"
        if marker in row.value:
            row.value = row.value.replace(marker, marker + "{school} {class_name}\n", 1)
            db.commit()


def all_settings(db: Session, group: str | None = None) -> dict[str, str]:
    stmt = select(Setting)
    if group:
        stmt = stmt.where(Setting.group == group)
    return {row.key: row.value for row in db.execute(stmt).scalars()}


def setting_rows(db: Session) -> list[Setting]:
    return list(db.execute(select(Setting).order_by(Setting.group, Setting.key)).scalars())


def class_key(class_id: int, key: str) -> str:
    """班级级配置键：class:<id>:<key>（class_id<=0 时返回原键）。"""
    class_id = int(class_id or 0)
    return f"class:{class_id}:{key}" if class_id > 0 else key


def get_setting(db: Session, key: str, default: str = "", class_id: int = 0) -> str:
    """读配置。class_id>0 时先读班级级键（class:<id>:<key>），没有则回退全局。"""
    class_id = int(class_id or 0)
    if class_id > 0:
        row = db.get(Setting, class_key(class_id, key))
        if row is not None:
            return row.value
    row = db.get(Setting, key)
    if row is None:
        return DEFAULTS.get(key, (default, "", ""))[0]
    return row.value


def get_bool(db: Session, key: str, default: bool = False, class_id: int = 0) -> bool:
    raw = str(get_setting(db, key, "1" if default else "0", class_id=class_id)).strip().lower()
    return raw in {"1", "true", "yes", "on", "是"}


def get_int(db: Session, key: str, default: int = 0, class_id: int = 0) -> int:
    try:
        return int(float(get_setting(db, key, str(default), class_id=class_id)))
    except (TypeError, ValueError):
        return default


def set_setting(db: Session, key: str, value: Any) -> None:
    row = db.get(Setting, key)
    text = "" if value is None else str(value)
    if row is None:
        meta = DEFAULTS.get(key, ("", "custom", ""))
        db.add(Setting(key=key, value=text, group=meta[1], description=meta[2]))
    else:
        row.value = text


# 这几个键存的是时间：保存时统一校验并规范成 HH:MM
TIME_KEYS = {
    "qq_report_time": "每晚 QQ 群汇报时间",
    "auto_export_time": "自动导出 Excel 时间",
    "auto_backup_time": "自动备份数据库时间",
}


def normalize_time(raw: Any, label: str) -> str:
    """把用户填的时间统一成 HH:MM。

    接受：22:40、22：40（全角）、22.40、22点40、22时40、2240、22
    格式不对或超范围直接报错，**不再静默存进去**（以前写坏过 14.06 / 22:39）。
    """
    text = str(raw or "").strip()
    if not text:
        return ""
    text = text.replace("：", ":").replace("。", ".").replace("·", ":")
    if re.fullmatch(r"\d{1,2}\.\d{2}", text):
        text = text.replace(".", ":")
    if re.fullmatch(r"\d{4}", text):  # 2240
        text = f"{text[:2]}:{text[2:]}"
    full = re.fullmatch(r"(\d{1,2})\s*[:时点]\s*(\d{0,2})", text)
    hour_only = re.fullmatch(r"(\d{1,2})", text)
    if full:
        hour = int(full.group(1))
        minute = int(full.group(2) or 0)
    elif hour_only:
        hour = int(hour_only.group(1))
        minute = 0
    else:
        raise AppError(f"「{label}」的时间格式不对：{raw}。请按 22:40 这种格式填写。")
    if not (0 <= hour <= 23) or not (0 <= minute <= 59):
        raise AppError(f"「{label}」的时间超出范围：{raw}（小时 0-23，分钟 0-59）")
    return f"{hour:02d}:{minute:02d}"


def update_settings(db: Session, values: Mapping[str, Any]) -> dict[str, str]:
    cleaned: dict[str, Any] = dict(values)
    # 时间类字段统一校验 + 规范化，避免被写坏
    for key, label in TIME_KEYS.items():
        if key in cleaned:
            cleaned[key] = normalize_time(cleaned[key], label)
    if "reminders" in cleaned:
        cleaned["reminders"] = normalize_reminders(cleaned["reminders"])
    for key, value in cleaned.items():
        set_setting(db, key, value)
    db.commit()
    return all_settings(db)


# --------------------------------------------------------------------------
# 定时提醒（多条，存在 reminders 这一个配置键里，JSON 格式）
# --------------------------------------------------------------------------
def normalize_reminders(raw: Any) -> str:
    """把前端传过来的提醒列表校验、清洗后序列化成 JSON 字符串。

    每条：{"id","name","time","enabled","mention_all","content"}
    时间统一过 normalize_time，格式不对直接报错，不写坏数据。
    """
    import json as _json

    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            items: list[Any] = []
        else:
            items = safe_json_loads(text, None)
            if items is None:
                raise AppError("提醒列表不是合法的 JSON，请刷新页面后重试")
    else:
        items = raw
    if not isinstance(items, list):
        raise AppError("提醒列表格式不对（应为数组）")
    if len(items) > 20:
        raise AppError("提醒最多 20 条，太多了反而打扰大家")

    seen_ids: set[str] = set()
    cleaned: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise AppError(f"第 {index + 1} 条提醒格式不对")
        rid = str(item.get("id") or "").strip()[:40]
        if not rid:
            rid = f"r{index + 1}"
        if rid in seen_ids:
            raise AppError(f"提醒 id 重复：{rid}")
        seen_ids.add(rid)
        name = str(item.get("name") or "").strip()[:30] or f"提醒 {index + 1}"
        time_text = normalize_time(item.get("time"), f"提醒「{name}」的时间")
        if not time_text:
            raise AppError(f"提醒「{name}」还没填时间")
        content = str(item.get("content") or "").strip()
        if not content:
            raise AppError(f"提醒「{name}」的内容不能为空")
        cleaned.append(
            {
                "id": rid,
                "name": name,
                "time": time_text,
                "enabled": bool(item.get("enabled", True)),
                "mention_all": bool(item.get("mention_all", False)),
                "content": content[:1500],
            }
        )
    return _json.dumps(cleaned, ensure_ascii=False)


def get_reminders(db: Session, class_id: int = 0) -> list[dict[str, Any]]:
    """读定时提醒列表（按班级独立：每个班级有自己的提醒清单）。

    - class_id>0：读 class:<id>:reminders；第一次用（键不存在）时自动把
      全局提醒复制一份过来，之后各班各自增删改互不影响。
    - class_id=0：全局提醒（老逻辑，含老数据迁移）。
    """
    class_id = int(class_id or 0)
    key = class_key(class_id, "reminders")
    row = db.get(Setting, key)
    raw = (row.value if row is not None else "").strip()

    if class_id > 0 and row is None:
        # 班级第一次用提醒：把当前全局提醒复制成本班的初始清单
        global_items = get_reminders(db, 0)
        db.add(Setting(key=key, value=json.dumps(global_items, ensure_ascii=False), group="remind", description="班级定时提醒"))
        db.commit()
        return [item for item in global_items if isinstance(item, dict)]

    items = safe_json_loads(raw, None) if raw else None
    if isinstance(items, list) and items:
        return [item for item in items if isinstance(item, dict)]
    if class_id > 0:
        return []

    # 迁移老的单条填报提醒（仅全局）
    template = get_setting(db, "tpl_fill_remind").strip()
    if not template:
        template = str(REMINDER_PRESETS[0]["content"])
    seeded = [
        {
            "id": "fill",
            "name": "填报提醒",
            "time": normalize_time(get_setting(db, "fill_remind_time") or "22:00", "填报提醒时间"),
            "enabled": get_bool(db, "fill_remind_enabled", True),
            "mention_all": get_bool(db, "fill_remind_mention_all", True),
            "content": template,
        }
    ]
    set_setting(db, "reminders", json.dumps(seeded, ensure_ascii=False))
    db.commit()
    return seeded


def reminder_presets() -> list[dict[str, Any]]:
    return [dict(item) for item in REMINDER_PRESETS]


# --------------------------------------------------------------------------
# 模板渲染
# --------------------------------------------------------------------------
_VAR_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def render_template(text: str, variables: Mapping[str, Any]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key == "deadline":
            # 兼容历史内容里残留的 {deadline}（填报截止时间概念已移除），渲染为空
            return ""
        if key not in variables:
            return match.group(0)
        value = variables[key]
        if value is None:
            return ""
        if isinstance(value, (date, datetime)):
            return value.strftime("%Y-%m-%d")
        return str(value)

    return _VAR_RE.sub(repl, text or "")


def base_vars(db: Session, day: date | None = None, class_id: int = 0) -> dict[str, Any]:
    """模板基础变量。class_id>0 时 class_name 用班级实体里的名字。"""
    day = day or now_local().date()
    settings = all_settings(db)
    week = "一二三四五六日"[day.weekday()]
    class_name = settings.get("class_name", "")
    if class_id:
        from ..models import SchoolClass

        row = db.get(SchoolClass, int(class_id))
        if row is not None and row.name:
            class_name = row.name
    return {
        "date": day.strftime("%Y-%m-%d"),
        "weekday": f"星期{week}",
        "time": now_local().strftime("%H:%M"),
        "school": settings.get("school_name", ""),
        "class_name": class_name,
        "commissary": settings.get("commissary_name", ""),
        "teacher": settings.get("teacher_name", ""),
    }


def template_vars_doc() -> dict[str, str]:
    return dict(TEMPLATE_VARS)


def parse_time_of_day(raw: str, fallback: str = "22:00") -> tuple[int, int]:
    """把 22:40 / 22:40:00 解析成 (22, 40)。"""
    text = str(raw or "").strip() or fallback
    match = re.match(r"^(\d{1,2})\s*[:：时点]\s*(\d{1,2})?", text)
    if not match:
        match = re.match(r"^(\d{1,2})$", text)
        if match:
            return int(match.group(1)) % 24, 0
        raise AppError(f"时间格式不正确：{raw}（应为 22:40 这种格式）")
    hour = int(match.group(1)) % 24
    minute = int(match.group(2) or 0) % 60
    return hour, minute


def now_str() -> str:
    return now_local().strftime("%Y-%m-%d %H:%M:%S")


def parse_date_arg(raw: str | None, fallback: date | None = None) -> date:
    if not raw:
        return fallback or now_local().date()
    return parse_date(raw)


# --------------------------------------------------------------------------
# 审计
# --------------------------------------------------------------------------
def write_audit(
    db: Session,
    *,
    actor: str,
    role: str,
    action: str,
    target: str = "",
    detail: str = "",
    ip: str = "",
    user_agent: str = "",
) -> None:
    if not user_agent:
        try:
            from ..security import current_device

            user_agent = current_device()
        except Exception:  # noqa: BLE001
            user_agent = ""
    db.add(
        AuditLog(
            actor=actor,
            role=role,
            action=action,
            target=target,
            detail=detail[:2000],
            ip=ip,
            user_agent=user_agent[:300],
        )
    )


def safe_json_loads(text: str, fallback: Any = None) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return fallback
