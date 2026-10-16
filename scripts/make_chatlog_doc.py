#!/usr/bin/env python3
"""把导出的聊天记录 JSON 生成 Markdown + Word 文档。

输入：build/chatlog/chatlog.json（由 scripts/export_chatlog.js 生成）
输出：
  聊天记录/聊天记录-生活助手宿舍管理系统.md
  聊天记录/聊天记录-生活助手宿舍管理系统.docx
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "build" / "chatlog" / "chatlog.json"
OUTDIR = ROOT / "聊天记录"
OUT_MD = OUTDIR / "聊天记录-生活助手宿舍管理系统.md"
OUT_DOCX = OUTDIR / "聊天记录-生活助手宿舍管理系统.docx"

TITLE = "生活助手宿舍管理系统"
SUBTITLE = "开发全过程聊天记录"

# 工具名中文说明
TOOL_LABEL = {
    "pwsh": "执行命令",
    "read": "读文件",
    "write": "写文件",
    "edit": "改文件",
    "grep": "搜索内容",
    "glob": "找文件",
    "web_search": "联网搜索",
    "web_fetch": "抓取网页",
    "todo_write": "更新待办",
    "present": "交付文件",
    "skill": "加载技能",
    "load_workspace_dependencies": "读取运行环境",
    "ask_user_question": "询问用户",
    "job_output": "读取后台任务",
    "job_kill": "结束后台任务",
    "job_list": "列出后台任务",
    "spawn_teammate": "创建协作者",
    "send_message": "给协作者发消息",
    "subagent": "派发子任务",
    "subagent_fork": "派发子任务",
    "workflow": "运行工作流",
    "schedule_create": "创建定时提醒",
    "image_to_editable_ppt": "图片转 PPT",
}


def load() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def strip_md(text: str) -> str:
    """给 Word 用时做轻量清理（保留可读性，去掉过重的标记）。"""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text


# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------
def build_markdown(d: dict) -> str:
    out: list[str] = []
    # 把图片拷到 md 同级目录，用相对路径引用（方便整体拷贝/打包）
    imgdir = OUTDIR / "images"
    imgdir.mkdir(parents=True, exist_ok=True)
    copied: dict[str, str] = {}
    idx = 0
    for t in d["turns"]:
        for u in t["user"]:
            for b in u["blocks"]:
                if b["type"] != "image" or not b.get("path"):
                    continue
                src = Path(b["path"])
                if not src.exists():
                    continue
                idx += 1
                suffix = src.suffix or ".png"
                name = f"截图{idx:02d}-第{t['turn']}轮{suffix}"
                dst = imgdir / name
                if not dst.exists():
                    shutil.copyfile(src, dst)
                copied[b["path"]] = f"images/{name}"

    out.append(f"# {SUBTITLE}")
    out.append("")
    out.append(f"**软件名称**：{TITLE}（V1.0）  ")
    out.append(f"**会话 ID**：`{d['sessionId']}`  ")
    out.append(f"**工作时间**：{d['createdAt']} ~ {d['exportedAt']}  ")
    out.append(f"**工作目录**：`{d['cwd']}`  ")
    total_text = sum(len(a["text"]) for t in d["turns"] for a in t["assistant"])
    n_img = sum(1 for t in d["turns"] for u in t["user"] for b in u["blocks"] if b["type"] == "image")
    out.append(
        f"**规模**：共 {len(d['turns'])} 轮对话 · {total_text:,} 字回复 · "
        f"{d['toolCallTotal']} 次工具调用 · {n_img} 张截图"
    )
    out.append("")
    out.append("---")
    out.append("")

    for t in d["turns"]:
        if not t["user"] and not t["assistant"]:
            continue
        out.append(f"## 第 {t['turn']} 轮　`{t['time']}`")
        out.append("")

        for u in t["user"]:
            for b in u["blocks"]:
                if b["type"] == "text":
                    out.append("### 👤 我")
                    out.append("")
                    out.append(b["text"])
                    out.append("")
                else:
                    out.append("### 👤 我（截图）")
                    out.append("")
                    rel = copied.get(b["path"])
                    if rel:
                        out.append(f"![{b['name']}]({rel})")
                    else:
                        out.append(f"（图片 {b['name']}，未找到原文件）")
                    out.append("")

        for a in t["assistant"]:
            out.append("### 🤖 助手")
            out.append("")
            out.append(a["text"])
            out.append("")

        if t["tools"]:
            out.append("<details><summary>🔧 本轮工具调用（%d 次）</summary>" % len(t["tools"]))
            out.append("")
            for c in t["tools"]:
                label = TOOL_LABEL.get(c["name"], c["name"])
                s = c["summary"].replace("\n", " ")
                out.append(f"- `{c['time']}` **{label}** `{c['name']}` — {s}")
            out.append("")
            out.append("</details>")
            out.append("")

    return "\n".join(out)


# --------------------------------------------------------------------------
# Word
# --------------------------------------------------------------------------
def set_cjk(run, font: str = "微软雅黑") -> None:
    run.font.name = font
    run._element.rPr.rFonts.set(qn("w:eastAsia"), font)


def add_body(doc: Document, text: str, *, color: RGBColor | None = None, size: float = 10.5) -> None:
    for para_text in text.split("\n"):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.line_spacing = 1.25
        run = p.add_run(para_text if para_text else "")
        set_cjk(run, "微软雅黑")
        run.font.size = Pt(size)
        if color is not None:
            run.font.color.rgb = color
        # 极简 markdown 处理：表格行、标题行粗体
        if re.match(r"^\s*\|", para_text):
            run.font.name = "Consolas"
            run._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
            run.font.size = Pt(9)


def prepare_image(src: Path, cache: dict[Path, Path], workdir: Path) -> Path | None:
    """把图片转成 python-docx 能嵌入的格式（webp 不支持），并适度缩小。

    返回可用于 add_picture 的路径；失败返回 None。
    """
    if src in cache:
        return cache[src]
    try:
        from PIL import Image

        workdir.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as im:
            im = im.convert("RGB")
            # 太宽的图缩小到 1600px，控制文档体积
            if im.width > 1600:
                ratio = 1600 / im.width
                im = im.resize((1600, max(1, int(im.height * ratio))), Image.LANCZOS)
            dst = workdir / (src.stem[:24] + ".png")
            im.save(dst, "PNG", optimize=True)
        cache[src] = dst
        return dst
    except Exception as exc:  # noqa: BLE001
        print(f"    ! 图片处理失败 {src.name}: {exc}")
        return None


def build_docx(d: dict) -> None:
    doc = Document()
    workdir = ROOT / "build" / "chatlog" / "img"
    img_cache: dict[Path, Path] = {}
    embedded = 0
    failed = 0

    # 页边距
    for section in doc.sections:
        section.left_margin = Inches(0.85)
        section.right_margin = Inches(0.85)
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)

    # 封面
    h = doc.add_heading("", level=0)
    r = h.add_run(TITLE)
    set_cjk(r, "微软雅黑")
    r.font.size = Pt(26)

    h2 = doc.add_heading("", level=1)
    r2 = h2.add_run(SUBTITLE)
    set_cjk(r2, "微软雅黑")
    r2.font.size = Pt(16)

    total_text = sum(len(a["text"]) for t in d["turns"] for a in t["assistant"])
    n_img = sum(1 for t in d["turns"] for u in t["user"] for b in u["blocks"] if b["type"] == "image")
    lines = [
        f"软件名称：{TITLE}（V1.0）",
        f"会话 ID：{d['sessionId']}",
        f"工作时间：{d['createdAt']} ~ {d['exportedAt']}",
        f"工作目录：{d['cwd']}",
        f"规　　模：{len(d['turns'])} 轮对话 · {total_text:,} 字回复 · {d['toolCallTotal']} 次工具调用 · {n_img} 张截图",
    ]
    for line in lines:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        run = p.add_run(line)
        set_cjk(run, "微软雅黑")
        run.font.size = Pt(11)

    doc.add_page_break()

    for t in d["turns"]:
        if not t["user"] and not t["assistant"]:
            continue

        head = doc.add_heading("", level=1)
        r = head.add_run(f"第 {t['turn']} 轮　{t['time']}")
        set_cjk(r, "微软雅黑")
        r.font.size = Pt(15)
        r.font.color.rgb = RGBColor(0x1F, 0x3A, 0x8A)

        # 同一轮里同角色只出现一次标题；每条消息用小字灰时间分隔，更易读
        if t["user"]:
            p = doc.add_paragraph()
            r = p.add_run("👤 我")
            set_cjk(r, "微软雅黑")
            r.bold = True
            r.font.size = Pt(11.5)
            r.font.color.rgb = RGBColor(0x0B, 0x6E, 0x4F)
            for u in t["user"]:
                for b in u["blocks"]:
                    if b["type"] == "text":
                        add_body(doc, b["text"], size=10.5)
                    else:
                        tp = doc.add_paragraph()
                        tp.paragraph_format.space_before = Pt(6)
                        tp.paragraph_format.space_after = Pt(2)
                        tr = tp.add_run(
                            f"截图 {b['name']}　{b.get('width')}×{b.get('height')}　{u['time']}"
                        )
                        set_cjk(tr, "微软雅黑")
                        tr.font.size = Pt(9)
                        tr.font.color.rgb = RGBColor(0x0B, 0x6E, 0x4F)
                        if b.get("path") and Path(b["path"]).exists():
                            ready = prepare_image(Path(b["path"]), img_cache, workdir)
                            if ready is not None:
                                try:
                                    doc.add_picture(str(ready), width=Inches(5.6))
                                    embedded += 1
                                except Exception as exc:  # noqa: BLE001
                                    failed += 1
                                    add_body(
                                        doc,
                                        f"（图片嵌入失败：{b['name']} — {exc}）",
                                        color=RGBColor(0x99, 0x00, 0x00),
                                    )
                            else:
                                failed += 1
                                add_body(
                                    doc,
                                    f"（图片无法转换，原文件：{b['path']}）",
                                    color=RGBColor(0x99, 0x00, 0x00),
                                )
                        else:
                            failed += 1
                            add_body(doc, f"（图片缺失：{b['name']}）", color=RGBColor(0x99, 0x00, 0x00))

        if t["assistant"]:
            p = doc.add_paragraph()
            r = p.add_run("🤖 助手")
            set_cjk(r, "微软雅黑")
            r.bold = True
            r.font.size = Pt(11.5)
            r.font.color.rgb = RGBColor(0x1F, 0x3A, 0x8A)
            for a in t["assistant"]:
                tp = doc.add_paragraph()
                tp.paragraph_format.space_before = Pt(7)
                tp.paragraph_format.space_after = Pt(1)
                tr = tp.add_run(f"— {a['time']} —")
                set_cjk(tr, "微软雅黑")
                tr.font.size = Pt(8)
                tr.font.color.rgb = RGBColor(0xAA, 0xAA, 0xAA)
                add_body(doc, strip_md(a["text"]), size=10.5)

        if t["tools"]:
            p = doc.add_paragraph()
            r = p.add_run(f"🔧 本轮工具调用（{len(t['tools'])} 次）")
            set_cjk(r, "微软雅黑")
            r.bold = True
            r.font.size = Pt(10)
            r.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
            for c in t["tools"]:
                label = TOOL_LABEL.get(c["name"], c["name"])
                s = c["summary"].replace("\n", " ")[:200]
                pp = doc.add_paragraph()
                pp.paragraph_format.space_after = Pt(1)
                pp.paragraph_format.left_indent = Inches(0.25)
                rr = pp.add_run(f"· [{c['time']}] {label}（{c['name']}）：{s}")
                set_cjk(rr, "微软雅黑")
                rr.font.size = Pt(8.5)
                rr.font.color.rgb = RGBColor(0x88, 0x88, 0x88)

    OUTDIR.mkdir(parents=True, exist_ok=True)
    doc.save(OUT_DOCX)
    print(f"    内嵌图片 {embedded} 张，失败 {failed} 张")


def main() -> None:
    d = load()
    OUTDIR.mkdir(parents=True, exist_ok=True)

    md = build_markdown(d)
    OUT_MD.write_text(md, encoding="utf-8")
    print(f"  Markdown: {OUT_MD.name}  {OUT_MD.stat().st_size / 1024:,.0f} KB")

    build_docx(d)
    print(f"  Word:     {OUT_DOCX.name}  {OUT_DOCX.stat().st_size / 1024 / 1024:,.2f} MB")


if __name__ == "__main__":
    main()
