"""班费：设置、明细、统计、导入、生成群消息文案。

数据基准是班主任/生活委员手里的 Excel（班费收支明细表），
表头给出「每人班费 / 人数 / 班费合计 / 已使用 / 班费余额」，下面每行是一条支出。
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FundEntry, FundSetting
from ..util import now_local

HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "seq": ("序号", "编号", "no"),
    "date": ("日期", "时间", "发生日期"),
    "item": ("支出项目", "项目", "用途", "事由", "内容", "摘要"),
    "unit_price": ("单价", "价格", "金额单价"),
    "quantity": ("数量", "份数"),
    "amount": ("金额", "花费", "支出金额", "合计"),
    "handler": ("经手人", "经办人", "购买人"),
    "checker": ("核对人", "审核人", "复核人"),
    "note": ("备注", "说明"),
}

HEADER_WORDS = ("序号", "支出项目", "经手人", "金额", "日期", "核对人", "备注")

SUMMARY_ALIASES: dict[str, tuple[str, ...]] = {
    "per_person": ("班费每人", "每人班费", "人均", "每人"),
    "headcount": ("人数", "班级人数", "总人数"),
    "total_fund": ("班费合计", "班费总额", "总收入", "收缴合计", "总额"),
    "spent": ("已使用", "已支出", "总支出", "使用合计"),
    "balance": ("班费余额", "余额", "剩余", "结余"),
}

SOURCES = {"manual": "手动添加", "import": "表格导入"}


# --------------------------------------------------------------------------
# 设置
# --------------------------------------------------------------------------
def get_settings(db: Session, class_id: int = 0) -> FundSetting:
    """按班级取班费设置；没有就给这个班级建一份。class_id<=0 表示老的全局记录。"""
    query = select(FundSetting).order_by(FundSetting.id)
    if class_id > 0:
        query = query.where(FundSetting.class_id == class_id)
    else:
        query = query.where(FundSetting.class_id <= 0)
    row = db.execute(query).scalars().first()
    if row is None:
        default_name = ""
        if class_id > 0:
            from . import class_service

            cls = class_service.get_class(db, class_id)
            default_name = cls.name if cls else ""
        row = FundSetting(
            per_person=50.0, headcount=0, total_fund=0.0, class_name=default_name,
            class_id=max(0, class_id),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def update_settings(db: Session, payload: dict[str, Any], class_id: int = 0) -> FundSetting:
    row = get_settings(db, class_id)
    for field in ("per_person", "headcount", "total_fund", "extra_in", "class_name", "note",
                  "qq_group_id", "template"):
        if field not in payload or payload[field] is None:
            continue
        value = payload[field]
        if field in ("per_person", "total_fund", "extra_in"):
            row.__setattr__(field, float(value or 0))
        elif field == "headcount":
            row.__setattr__(field, int(value or 0))
        else:
            row.__setattr__(field, str(value).strip())
    db.commit()
    db.refresh(row)
    return row


def effective_total_fund(row: FundSetting) -> float:
    """班费合计：填了就用填的，没填就按 每人 × 人数 算。"""
    if row.total_fund:
        return float(row.total_fund)
    return float(row.per_person or 0) * int(row.headcount or 0)


# --------------------------------------------------------------------------
# 明细
# --------------------------------------------------------------------------
def list_entries(db: Session, *, keyword: str = "", direction: str = "", class_id: int = 0) -> list[FundEntry]:
    query = select(FundEntry).order_by(FundEntry.entry_date.is_(None), FundEntry.entry_date, FundEntry.seq, FundEntry.id)
    if class_id > 0:
        query = query.where(FundEntry.class_id == class_id)
    if direction in ("expense", "income"):
        query = query.where(FundEntry.direction == direction)
    rows = list(db.execute(query).scalars())
    key = (keyword or "").strip().lower()
    if key:
        rows = [
            row
            for row in rows
            if key
            in f"{row.item}{row.handler}{row.checker}{row.note}{row.date_text}{row.amount}".lower()
        ]
    return rows


def serialize_entry(row: FundEntry) -> dict[str, Any]:
    return {
        "id": row.id,
        "class_id": int(row.class_id or 0),
        "seq": row.seq,
        "date": row.entry_date.strftime("%Y-%m-%d") if row.entry_date else "",
        "date_text": row.date_text,
        "item": row.item,
        "unit_price": row.unit_price,
        "quantity": row.quantity,
        "amount": round(float(row.amount or 0), 2),
        "direction": row.direction,
        "direction_text": "支出" if row.direction == "expense" else "收入",
        "handler": row.handler,
        "checker": row.checker,
        "note": row.note,
        "source": row.source,
        "source_text": SOURCES.get(row.source, row.source),
        "pushed_at": row.pushed_at.strftime("%Y-%m-%d %H:%M") if row.pushed_at else "",
    }


def summary(db: Session, class_id: int = 0) -> dict[str, Any]:
    row = get_settings(db, class_id)
    entries = list_entries(db, class_id=class_id)
    spent = round(sum(float(e.amount or 0) for e in entries if e.direction == "expense"), 2)
    income_extra = round(sum(float(e.amount or 0) for e in entries if e.direction == "income"), 2)
    total = round(effective_total_fund(row) + float(row.extra_in or 0) + income_extra, 2)
    balance = round(total - spent, 2)
    return {
        "per_person": float(row.per_person or 0),
        "headcount": int(row.headcount or 0),
        "total_fund": total,
        "base_fund": effective_total_fund(row),
        "extra_in": round(float(row.extra_in or 0), 2),
        "income_extra": income_extra,
        "spent": spent,
        "balance": balance,
        "entry_count": len(entries),
        "expense_count": sum(1 for e in entries if e.direction == "expense"),
        "class_name": row.class_name,
        "note": row.note,
        "qq_group_id": row.qq_group_id,
        "avg_per_person": round(spent / row.headcount, 2) if row.headcount else 0,
    }


def next_seq(db: Session, class_id: int = 0) -> int:
    query = select(FundEntry.seq)
    if class_id > 0:
        query = query.where(FundEntry.class_id == class_id)
    rows = list(db.execute(query).scalars())
    return (max(rows) if rows else 0) + 1


def create_entry(db: Session, payload: dict[str, Any], class_id: int = 0) -> FundEntry:
    row = FundEntry(
        seq=int(payload.get("seq") or 0) or next_seq(db, class_id),
        entry_date=_parse_date(payload.get("date") or payload.get("date_text") or ""),
        date_text=str(payload.get("date_text") or payload.get("date") or "").strip()[:40],
        item=str(payload.get("item") or "").strip()[:200],
        unit_price=_to_float(payload.get("unit_price")),
        quantity=_to_float(payload.get("quantity")),
        amount=_to_float(payload.get("amount")) or 0.0,
        direction="income" if str(payload.get("direction") or "") == "income" else "expense",
        handler=str(payload.get("handler") or "").strip()[:80],
        checker=str(payload.get("checker") or "").strip()[:80],
        note=str(payload.get("note") or "").strip()[:300],
        source="manual",
        class_id=max(0, int(class_id or 0)),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_entry(db: Session, entry_id: int, payload: dict[str, Any]) -> FundEntry | None:
    row = db.get(FundEntry, entry_id)
    if row is None:
        return None
    if "seq" in payload and payload["seq"] not in (None, ""):
        row.seq = int(payload["seq"])
    if "date" in payload or "date_text" in payload:
        raw = payload.get("date") or payload.get("date_text") or ""
        row.entry_date = _parse_date(raw)
        row.date_text = str(raw).strip()[:40]
    for field in ("item", "handler", "checker", "note"):
        if field in payload and payload[field] is not None:
            row.__setattr__(field, str(payload[field]).strip()[: (200 if field == "item" else 300)])
    for field in ("unit_price", "quantity"):
        if field in payload:
            row.__setattr__(field, _to_float(payload[field]))
    if "amount" in payload:
        row.amount = _to_float(payload["amount"]) or 0.0
    if "direction" in payload and payload["direction"]:
        row.direction = "income" if payload["direction"] == "income" else "expense"
    db.commit()
    db.refresh(row)
    return row


def delete_entries(db: Session, ids: Iterable[int]) -> int:
    count = 0
    for entry_id in ids:
        row = db.get(FundEntry, int(entry_id))
        if row is not None:
            db.delete(row)
            count += 1
    db.commit()
    return count


# --------------------------------------------------------------------------
# 群消息文案
# --------------------------------------------------------------------------
DEFAULT_TEMPLATE = (
    "【班费公示】{class_name}\n"
    "班费每人 {per_person} 元 × {headcount} 人 = {total_fund} 元\n"
    "已使用 {spent} 元，剩余 {balance} 元\n"
    "{lines}"
)

DEFAULT_LINE = "· {date} {item} {amount} 元（经手人：{handler}）"


def build_message(
    db: Session,
    *,
    scope: str = "latest",
    ids: Iterable[int] | None = None,
    limit: int = 10,
    title: str = "",
    class_id: int = 0,
) -> dict[str, Any]:
    """把班费情况组织成可以发到群里的文字。"""
    row = get_settings(db, class_id)
    stats = summary(db, class_id)
    entries = list_entries(db, class_id=class_id)
    id_set = {int(i) for i in (ids or [])}

    if scope == "all":
        chosen = [e for e in entries if e.direction == "expense"]
    elif scope == "selected":
        chosen = [e for e in entries if e.id in id_set]
    elif scope == "recent":
        expenses = [e for e in entries if e.direction == "expense"]
        chosen = expenses[-max(1, limit):]
        chosen.reverse()
    else:  # latest
        expenses = [e for e in entries if e.direction == "expense"]
        chosen = expenses[-1:] if expenses else []

    lines = []
    for entry in chosen:
        when = entry.date_text or (entry.entry_date.strftime("%Y.%m.%d") if entry.entry_date else "")
        used = _entry_date(entry)
        lines.append(
            DEFAULT_LINE.format(
                date=(when + " ") if when else "",
                item=entry.item or "（未填写项目）",
                amount=_money(entry.amount),
                handler=entry.handler or "—",
            )
        )
        _ = used
    body_lines = "\n".join(lines) if lines else "（没有可展示的明细）"

    template = (row.template or "").strip() or DEFAULT_TEMPLATE
    head = title.strip()
    class_label = (row.class_name or "").strip()
    if not class_label and class_id > 0:
        from . import class_service

        cls = class_service.get_class(db, class_id)
        class_label = cls.name if cls else ""
    text = template.format(
        class_name=class_label or "本班",
        per_person=_money(row.per_person),
        headcount=row.headcount,
        total_fund=_money(stats["total_fund"]),
        spent=_money(stats["spent"]),
        balance=_money(stats["balance"]),
        count=len(chosen),
        lines=body_lines,
    )
    if head:
        text = f"{head}\n{text}"

    scope_text = {
        "latest": "最新一笔",
        "recent": f"最近 {len(chosen)} 笔",
        "selected": f"选定的 {len(chosen)} 笔",
        "all": f"全部 {len(chosen)} 笔",
    }.get(scope, "班费公示")

    return {
        "scope": scope,
        "scope_text": scope_text,
        "count": len(chosen),
        "text": text.strip(),
        "entry_ids": [e.id for e in chosen],
        "amount": round(sum(float(e.amount or 0) for e in chosen), 2),
        "summary": stats,
    }


def render_preview(db: Session, scope: str, ids: Iterable[int] | None, limit: int = 10,
                   class_id: int = 0) -> dict[str, Any]:
    if scope == "selected" and not ids:
        return {
            "scope": scope,
            "scope_text": "选定的 0 笔",
            "count": 0,
            "text": "请先勾选要发送的明细",
            "entry_ids": [],
            "amount": 0.0,
            "summary": summary(db, class_id),
        }
    return build_message(db, scope=scope, ids=ids, limit=limit, class_id=class_id)


# --------------------------------------------------------------------------
# 解析 Excel（班费收支明细表）
# --------------------------------------------------------------------------
def _read_summary(rows: list[tuple]) -> dict[str, Any]:
    """从表头区域读「每人 / 人数 / 班费合计 / 已使用 / 余额」。

    表头长这样：  班费每人 | 人数 | 班费合计 | 已使用 | 班费余额
                  50      | 48   | 2400    | 497.85 | 1902.15
    注意：表头区域往往已经把明细表头行（序号/日期/支出项目…）也包含进来了，
    所以按「列」去重会把数字行挡掉，这里改成按「值 + 列」收集。
    """
    labels: list[tuple[int, int, str]] = []
    numbers: list[tuple[int, int, float]] = []
    seen_labels: set[tuple[int, int, str]] = set()
    seen_numbers: set[tuple[int, int]] = set()
    for row_index, row in enumerate(rows):
        for index, cell in enumerate(row):
            if isinstance(cell, str):
                text = cell.strip().replace(" ", "")
                key = (row_index, index, text)
                if text and key not in seen_labels:
                    seen_labels.add(key)
                    labels.append(key)
            elif isinstance(cell, (int, float)) and not isinstance(cell, bool):
                key = (row_index, index)
                if key not in seen_numbers:
                    seen_numbers.add(key)
                    numbers.append((row_index, index, float(cell)))

    result: dict[str, float] = {}
    for field, aliases in SUMMARY_ALIASES.items():
        for row_index, index, text in labels:
            if not any(alias in text for alias in aliases):
                continue
            # 取同一行、靠右（或紧随其后的下一行）最近的数字
            candidates = [
                item for item in numbers
                if (item[0] == row_index and item[1] > index)
                or (item[0] > row_index and item[1] >= index)
            ]
            if not candidates:
                continue
            best = min(candidates, key=lambda item: (item[0] - row_index, abs(item[1] - index)))
            result[field] = best[2]
            break
    return result


def parse_workbook(data: bytes) -> dict[str, Any]:
    """解析上传的班费表格，返回表头统计 + 明细行。"""
    from openpyxl import load_workbook

    import io

    wb = load_workbook(io.BytesIO(data), data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))

    header_row = -1
    for index, row in enumerate(rows[:12]):
        text = " ".join(str(cell) for cell in row if cell is not None)
        hits = sum(1 for word in HEADER_WORDS if word in text)
        if hits >= 3:
            header_row = index
            break
    if header_row < 0:
        raise ValueError("没有找到表头行（应包含「序号 / 日期 / 支出项目 / 金额」等列）")

    header = rows[header_row]
    mapping = _match_columns(header)
    if "item" not in mapping and "amount" not in mapping:
        raise ValueError("表头里没有识别到「支出项目」或「金额」列")

    summary_values = _read_summary(rows[: header_row + 1])

    entries: list[dict[str, Any]] = []
    for row in rows[header_row + 1:]:
        if row is None or all(cell in (None, "") for cell in row):
            continue
        item = _pick(row, mapping.get("item"))
        amount = _to_float(_pick(row, mapping.get("amount")))
        if (item is None or str(item).strip() == "") and not amount:
            continue
        if isinstance(item, str) and item.strip() in HEADER_WORDS:
            continue
        date_raw = _pick(row, mapping.get("date"))
        seq = _pick(row, mapping.get("seq"))
        entries.append(
            {
                "seq": int(seq) if isinstance(seq, (int, float)) else 0,
                "date": _date_text(date_raw),
                "date_text": _date_text(date_raw),
                "item": str(item or "").strip(),
                "unit_price": _to_float(_pick(row, mapping.get("unit_price"))),
                "quantity": _to_float(_pick(row, mapping.get("quantity"))),
                "amount": amount or 0.0,
                "handler": str(_pick(row, mapping.get("handler")) or "").strip(),
                "checker": str(_pick(row, mapping.get("checker")) or "").strip(),
                "note": str(_pick(row, mapping.get("note")) or "").strip(),
                "direction": "expense",
            }
        )

    if not entries:
        raise ValueError("表格里没有读到有效的明细行")

    spent_in_sheet = _to_float(summary_values.get("spent"))
    spent_parsed = round(sum(float(e["amount"] or 0) for e in entries), 2)
    return {
        "summary": summary_values,
        "entries": entries,
        "spent_parsed": spent_parsed,
        "spent_in_sheet": spent_in_sheet,
        "spent_match": bool(spent_in_sheet) and abs(spent_in_sheet - spent_parsed) < 0.01,
        "header_row": header_row + 1,
        "columns": mapping,
        "sheet_name": ws.title,
    }


def import_entries(db: Session, parsed: dict[str, Any], *, replace: bool = True,
                   apply_summary: bool = True, class_id: int = 0) -> dict[str, Any]:
    """把解析结果写进数据库。replace 只清空当前班级的明细。"""
    if replace:
        clear_query = select(FundEntry)
        if class_id > 0:
            clear_query = clear_query.where(FundEntry.class_id == class_id)
        for row in list(db.execute(clear_query).scalars()):
            db.delete(row)
        db.commit()

    created = 0
    for item in parsed.get("entries", []):
        db.add(
            FundEntry(
                seq=int(item.get("seq") or 0) or (created + 1),
                entry_date=_parse_date(item.get("date_text") or ""),
                date_text=str(item.get("date_text") or "")[:40],
                item=str(item.get("item") or "")[:200],
                unit_price=_to_float(item.get("unit_price")),
                quantity=_to_float(item.get("quantity")),
                amount=_to_float(item.get("amount")) or 0.0,
                direction="expense",
                handler=str(item.get("handler") or "")[:80],
                checker=str(item.get("checker") or "")[:80],
                note=str(item.get("note") or "")[:300],
                source="import",
                class_id=max(0, int(class_id or 0)),
            )
        )
        created += 1
    db.commit()

    if apply_summary:
        values = parsed.get("summary") or {}
        payload: dict[str, Any] = {}
        if values.get("per_person") is not None:
            payload["per_person"] = values["per_person"]
        if values.get("headcount") is not None:
            payload["headcount"] = values["headcount"]
        if values.get("total_fund") is not None:
            payload["total_fund"] = values["total_fund"]
        if payload:
            update_settings(db, payload, class_id)

    return {"created": created, "replaced": replace, "summary": summary(db, class_id)}


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------
def _pick(row: tuple, index: int | None) -> Any:
    if index is None or index >= len(row):
        return None
    return row[index]


def _match_columns(header: tuple) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for index, cell in enumerate(header):
        if cell is None:
            continue
        name = str(cell).strip().replace(" ", "")
        for field, aliases in HEADER_ALIASES.items():
            if field in mapping:
                continue
            if any(alias in name for alias in aliases):
                mapping[field] = index
                break
    return mapping


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("元", "").replace("¥", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _date_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, date):
        return value.strftime("%Y.%m.%d")
    text = str(value).strip()
    match = re.match(r"^(\d{4})[-./年](\d{1,2})[-./月](\d{1,2})", text)
    if match:
        return f"{match.group(1)}.{int(match.group(2))}.{int(match.group(3))}"
    return text[:40]


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    match = re.match(r"^(\d{4})[-./年](\d{1,2})[-./月](\d{1,2})", text)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _entry_date(entry: FundEntry) -> date | None:
    return entry.entry_date


def _money(value: Any) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return str(value)
    if abs(number - round(number)) < 0.005:
        return str(int(round(number)))
    return f"{number:.2f}"


def stamp_pushed(db: Session, ids: Iterable[int]) -> None:
    now = now_local()
    for entry_id in ids:
        row = db.get(FundEntry, int(entry_id))
        if row is not None:
            row.pushed_at = now
    db.commit()
