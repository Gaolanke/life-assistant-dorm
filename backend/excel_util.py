"""Excel 导入/导出。"""
from __future__ import annotations

import io
import re
from datetime import date, datetime
from typing import Any, Iterable, Sequence

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .util import AppError, fmt_date, fmt_dt, parse_date

# 标准列头
COLUMNS = ["姓名", "学号", "电话号", "宿舍号"]
SUMMARY_COLUMNS = [
    "宿舍号",
    "楼栋",
    "宿舍长",
    "联系电话",
    "应到人数",
    "在寝人数",
    "缺席人数",
    "是否齐全",
    "不在人员",
    "备注",
    "填报人",
    "填报时间",
    "填报方式",
    "来源 IP",
    "填写设备",
]
DETAIL_COLUMNS = [
    "宿舍号",
    "姓名",
    "学号",
    "电话号",
    "是否在寝",
    "缺席原因",
    "备注",
]

# 列名别名，方便各种版本的表格直接导入
ALIASES: dict[str, set[str]] = {
    "name": {"姓名", "名字", "学生姓名", "成员姓名", "name", "姓 名", "人员姓名", "学生"},
    "student_no": {
        "学号",
        "学 号",
        "学生学号",
        "学籍号",
        "学工号",
        "工号",
        "编号",
        "student_no",
        "studentno",
        "no",
        "序号",
    },
    "phone": {
        "电话号",
        "电话",
        "电话号码",
        "手机号",
        "手机",
        "联系方式",
        "联系电话",
        "phone",
        "tel",
        "mobile",
    },
    "room_no": {
        "宿舍号",
        "宿舍",
        "房间号",
        "寝室号",
        "寝室",
        "宿舍编号",
        "房屋名称",
        "房屋",
        "公寓",
        "房间名称",
        "room",
        "roomno",
        "room_no",
        "房号",
    },
    "role": {"角色", "身份", "是否宿舍长", "职务", "备注（宿舍长）", "备注(宿舍长)", "备注"},
    "grade": {"年级", "班级", "学院", "年级班级", "专业"},
    "note": {"说明", "情况说明", "个人备注"},
}

# 出现这些词就标记为宿舍长
LEADER_WORDS = ("宿舍长", "舍长", "寝室长", "楼长", "负责人", "是")

ROOM_PREFIX = r"(?:新区校区|老区校区|新校区|老校区|东校区|西校区|南校区|北校区|本部|校区|大学|学院)*"

SOURCE_LABELS = {
    "web": "网页填报",
    "qq": "QQ 群填报",
    "qqbot": "机器人代填",
    "admin": "管理员代填",
    "import": "表格导入",
}

THIN = Side(style="thin", color="D0D7DE")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEADER_FILL = PatternFill("solid", fgColor="1F6FEB")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
TITLE_FONT = Font(bold=True, size=14)
WARN_FILL = PatternFill("solid", fgColor="FFF1F0")
OK_FILL = PatternFill("solid", fgColor="F0FFF4")


def _normalize(value: Any) -> str:
    text = str(value if value is not None else "").strip()
    return re.sub(r"[\s\u3000]+", "", text).lower()


def _guess_field(header: str) -> str | None:
    key = _normalize(header)
    if not key:
        return None
    for field, names in ALIASES.items():
        if key in {_normalize(n) for n in names}:
            return field
    # 模糊匹配：包含关键字
    for field, names in ALIASES.items():
        for name in names:
            norm = _normalize(name)
            if norm and (norm in key or key in norm) and len(norm) >= 2:
                return field
    return None


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value).strip()


_CN_DIGITS = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8", "九": "9", "十": "10"}


def parse_room_label(raw: str) -> tuple[str, str, str]:
    """把“新区校区6号学生公寓207”这类写法拆成 (宿舍号, 楼栋, 原始名称)。

    返回的宿舍号带楼栋前缀，例如 6-207，避免不同楼栋出现相同房间号时混淆。
    """
    text = _cell_text(raw)
    if not text:
        return "", "", ""
    text = text.replace("\u3000", " ").strip()
    # 去掉“（1人）”“(4人间)”这类备注，它们不是房间号的一部分
    text = re.sub(r"[（(][^）)]*[）)]", "", text).strip()
    building_no = ""
    building = ""
    building_match = re.search(r"([0-9]{1,2}|[一二三四五六七八九十]{1,2})\s*[号栋]", text)
    if building_match:
        number = building_match.group(1)
        building_no = _CN_DIGITS.get(number, number)
        building = f"{building_no}号楼"
    elif "公寓" in text:
        part = text.split("公寓")[0]
        tail = re.search(r"([0-9]{1,2})\s*$", part)
        if tail:
            building_no = tail.group(1)
            building = f"{building_no}号楼"

    tail = text.split("公寓")[-1] if "公寓" in text else text
    tail = re.sub(r"^[0-9一二三四五六七八九十]{1,2}\s*[号栋]", "", tail)
    room_match = re.search(r"([A-Za-z]?\d{1,2}\s*[-#－]?\s*\d{2,4})\s*$", tail)
    if room_match:
        room = re.sub(r"\s+", "", room_match.group(1)).replace("－", "-").replace("#", "-")
    else:
        room_match = re.search(r"([A-Za-z]?\d{2,4})\s*$", text)
        room = room_match.group(1) if room_match else text
    if building_no and room.isdigit():
        room = room[-3:] if len(room) == 4 and room.startswith("1") else room
        room = f"{building_no}-{room}"
    return room, building, text


def is_leader(role_text: str) -> bool:
    text = _normalize(role_text)
    if not text:
        return False
    if "非" in text or "不是" in text:
        return False
    return any(word in text for word in LEADER_WORDS)


def read_table(content: bytes, filename: str = "") -> tuple[list[str], list[dict[str, Any]], str]:
    """解析上传的 xlsx / csv，返回 (列头, 行字典列表, sheet 名)。"""
    if filename.lower().endswith(".csv"):
        rows = _read_csv(content)
        headers = rows[0] if rows else []
        data = [dict(zip(headers, row)) for row in rows[1:] if any(str(c).strip() for c in row)]
        return headers, data, "csv"
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise AppError(f"无法读取表格文件：{exc}") from exc
    best: tuple[list[str], list[dict[str, Any]], str] | None = None
    for ws in wb.worksheets:
        headers, data = _read_sheet(ws)
        if not headers:
            continue
        if best is None or len(data) > len(best[1]):
            best = (headers, data, ws.title)
    if best is None:
        raise AppError("表格里没有找到有效数据")
    return best


def _read_csv(content: bytes) -> list[list[str]]:
    text = None
    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise AppError("CSV 编码无法识别，请另存为 UTF-8 或直接用 xlsx")
    import csv

    reader = csv.reader(io.StringIO(text))
    return [row for row in reader]


def _read_sheet(ws: Worksheet) -> tuple[list[str], list[dict[str, Any]]]:
    rows = list(ws.iter_rows(values_only=True))
    header_index = -1
    for index, row in enumerate(rows[:12]):
        cells = [_cell_text(c) for c in row]
        if sum(1 for c in cells if _guess_field(c)) >= 2:
            header_index = index
            break
    if header_index < 0:
        # 退化成第一行作表头
        if not rows:
            return [], []
        header_index = 0
    headers = [_cell_text(c) for c in rows[header_index]]
    data: list[dict[str, Any]] = []
    for row in rows[header_index + 1 :]:
        if not any(_cell_text(c) for c in row):
            continue
        item: dict[str, Any] = {}
        for idx, header in enumerate(headers):
            value = row[idx] if idx < len(row) else None
            item[header or f"列{idx + 1}"] = value
        data.append(item)
    return [h for h in headers if h], data


def map_rows(
    headers: Sequence[str], rows: Sequence[dict[str, Any]]
) -> tuple[dict[str, str], list[dict[str, str]]]:
    """把原始表格映射成标准字段。

    兼容合并单元格：宿舍号/楼栋等列只在第一行出现时，会自动向下填充（前向填充）。
    """
    mapping: dict[str, str] = {}
    for header in headers:
        field = _guess_field(header)
        if field and field not in mapping:
            mapping[field] = header
    result: list[dict[str, str]] = []
    carry: dict[str, str] = {}
    for raw in rows:
        item: dict[str, str] = {}
        for field, header in mapping.items():
            value = _cell_text(raw.get(header))
            if value:
                carry[field] = value
            elif field in carry and field in {"room_no", "grade"}:
                # 这两列常见合并单元格，沿用上一行的值（角色列不沿用）
                value = carry[field]
            item[field] = value
        if not any(item.values()):
            continue
        if not (item.get("name") or "").strip():
            continue
        # 角色：备注列写着“宿舍长”就标记
        role = item.get("role", "")
        item["role"] = "宿舍长" if is_leader(role) else "成员"
        result.append(item)
    return mapping, result


def build_template() -> bytes:
    """生成导入模板。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "人员信息"
    ws.append(COLUMNS)
    ws.append(["张三", "2023010101", "13800000001", "3-201"])
    ws.append(["李四", "2023010102", "13800000002", "3-201"])
    ws.append(["王五", "2023010103", "13800000003", "3-202"])
    _style_header(ws, len(COLUMNS))
    widths = [14, 18, 18, 16]
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width

    tips = wb.create_sheet("填写说明")
    lines = [
        "人员信息导入模板说明",
        "",
        "1. 必填列：姓名、宿舍号。学号和电话号可以留空后补。",
        "2. 同一个宿舍号的行会自动归为一组（一个宿舍一个组）。",
        "3. 宿舍号建议统一格式，例如 3-201 或 201，系统按文本精确匹配分组。",
        "4. 表头名称可识别：姓名/学生姓名、学号/学籍号、电话号/手机号、宿舍号/寝室号。",
        "5. 导入时可以选择“覆盖这些宿舍的原有名单”或“追加到现有名单”。",
        "6. 如果表格里带有“宿舍长”列或“角色”列，会自动标记宿舍长。",
    ]
    for line in lines:
        tips.append([line])
    tips.column_dimensions["A"].width = 80
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _style_header(ws: Worksheet, count: int) -> None:
    for col in range(1, count + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 22


def export_reports(
    days: Iterable[date],
    summaries: dict[date, list[dict[str, Any]]],
    details: dict[date, list[dict[str, Any]]],
    meta: dict[str, Any] | None = None,
) -> bytes:
    """导出填报数据：每个日期一张“汇总”表 + 一张“明细”表。"""
    meta = meta or {}
    wb = Workbook()
    wb.remove(wb.active)
    day_list = list(days)
    if not day_list:
        raise AppError("没有可导出的数据")

    for day in day_list:
        room_rows = summaries.get(day, [])
        title = f"{fmt_date(day)} 宿舍人员情况"
        sheet_name = fmt_date(day)
        ws = _write_summary_sheet(wb, sheet_name, title, room_rows, meta)
        _write_detail_sheet(wb, f"{fmt_date(day)} 明细"[:31], room_rows, details.get(day, []))
        del ws

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _write_summary_sheet(
    wb: Workbook,
    sheet_name: str,
    title: str,
    rows: list[dict[str, Any]],
    meta: dict[str, Any],
) -> Worksheet:
    ws = wb.create_sheet(sheet_name[:31])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(SUMMARY_COLUMNS))
    title_cell = ws.cell(row=1, column=1, value=title)
    title_cell.font = TITLE_FONT
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 26

    info = (
        f"{meta.get('school_name', '')}  {meta.get('class_name', '')}   "
        f"应查 {meta.get('dorm_total', 0)} 间 / 已报 {meta.get('reported', 0)} 间 / "
        f"未报 {meta.get('unreported', 0)} 间   在寝 {meta.get('present', 0)} 人 / "
        f"应到 {meta.get('total', 0)} 人   导出时间 {meta.get('exported_at', '')}"
    )
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(SUMMARY_COLUMNS))
    info_cell = ws.cell(row=2, column=1, value=info)
    info_cell.alignment = Alignment(horizontal="center", vertical="center")

    ws.append([])
    ws.append(SUMMARY_COLUMNS)
    header_row = ws.max_row
    for col in range(1, len(SUMMARY_COLUMNS) + 1):
        cell = ws.cell(row=header_row, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER

    for row in rows:
        ws.append(
            [
                row.get("room_no", ""),
                row.get("building", ""),
                row.get("leader_name", ""),
                row.get("leader_phone", ""),
                row.get("total_count", 0),
                row.get("present_count", 0),
                row.get("absent_count", 0),
                row.get("status_text", ""),
                row.get("absent_names", ""),
                row.get("note", ""),
                row.get("submitter", ""),
                row.get("submitted_at", ""),
                row.get("source_text", ""),
                row.get("ip", ""),
                row.get("device", ""),
            ]
        )
        current = ws.max_row
        fill = OK_FILL if row.get("status_text") == "齐全" else WARN_FILL
        for col in range(1, len(SUMMARY_COLUMNS) + 1):
            cell = ws.cell(row=current, column=col)
            cell.border = BORDER
            cell.alignment = Alignment(vertical="center", wrap_text=col in (9, 10))
            cell.fill = fill

    widths = [12, 10, 12, 16, 10, 10, 10, 10, 24, 40, 12, 20, 12, 16, 22]
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width
    ws.freeze_panes = f"A{header_row + 1}"
    return ws


def _write_detail_sheet(
    wb: Workbook,
    sheet_name: str,
    summary_rows: list[dict[str, Any]],
    detail_rows: list[dict[str, Any]],
) -> Worksheet:
    ws = wb.create_sheet(sheet_name)
    ws.append(DETAIL_COLUMNS)
    for col in range(1, len(DETAIL_COLUMNS) + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER
    ws.freeze_panes = "A2"

    missing_rooms = {row.get("room_no") for row in summary_rows if not row.get("reported")}
    for row in detail_rows:
        ws.append(
            [
                row.get("room_no", ""),
                row.get("name", ""),
                row.get("student_no", ""),
                row.get("phone", ""),
                "在寝" if row.get("present", True) else "不在寝",
                row.get("reason", ""),
                row.get("note", ""),
            ]
        )
        current = ws.max_row
        fill = OK_FILL if row.get("present", True) else WARN_FILL
        if row.get("room_no") in missing_rooms:
            fill = PatternFill("solid", fgColor="F5F5F5")
        for col in range(1, len(DETAIL_COLUMNS) + 1):
            cell = ws.cell(row=current, column=col)
            cell.border = BORDER
            cell.fill = fill
            cell.alignment = Alignment(vertical="center")

    for row in summary_rows:
        if row.get("reported"):
            continue
        ws.append([row.get("room_no", ""), "—— 未填报 ——", "", "", "未知", "", ""])
        current = ws.max_row
        for col in range(1, len(DETAIL_COLUMNS) + 1):
            cell = ws.cell(row=current, column=col)
            cell.border = BORDER
            cell.font = Font(color="B42318")

    widths = [12, 12, 18, 16, 10, 16, 30]
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width
    return ws


def export_members(dorms: list[dict[str, Any]], filename_meta: str = "") -> bytes:
    """导出完整人员名单（一个总表）。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "人员名单"
    headers = ["宿舍号", "楼栋", "宿舍长", "宿舍长电话", "姓名", "学号", "电话号", "角色", "备注"]
    ws.append(headers)
    for dorm in dorms:
        for member in dorm.get("members", []):
            ws.append(
                [
                    dorm.get("room_no", ""),
                    dorm.get("building", ""),
                    dorm.get("leader_name", ""),
                    dorm.get("leader_phone", ""),
                    member.get("name", ""),
                    member.get("student_no", ""),
                    member.get("phone", ""),
                    member.get("role", ""),
                    member.get("note", ""),
                ]
            )
    _style_header(ws, len(headers))
    widths = [12, 10, 12, 16, 12, 18, 16, 10, 20]
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def export_text_report(text: str, sheet_name: str = "汇报") -> bytes:
    """把群汇报文本也存一份 Excel，方便留档。"""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31]
    for line in (text or "").splitlines():
        ws.append([line])
    ws.column_dimensions["A"].width = 80
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def read_first_sheet_rows(content: bytes) -> list[list[str]]:
    wb = load_workbook(io.BytesIO(content), data_only=True)
    ws = wb.worksheets[0]
    return [[_cell_text(c) for c in row] for row in ws.iter_rows(values_only=True)]


def guess_date_from_filename(filename: str) -> date | None:
    match = re.search(r"(20\d{2})[-_.年]?(\d{1,2})[-_.月]?(\d{1,2})", filename or "")
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None
