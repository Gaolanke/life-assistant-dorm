"""为当前已有的宿舍生成历史填报数据，并批量设置寝室长验证密码。

说明：
  * 只会为“现有宿舍”补历史记录，不会新建或删除宿舍。
  * 今天的数据只填一部分宿舍，方便演示“未填报提醒”。
  * 加了 --password 时，同时把「宿舍号 + 密码」这条路也设好（账号登录之外的寝室长入口）。
  * 这个脚本直接改数据库，不需要管理员登录。

用法：
    .venv\\Scripts\\python.exe scripts\\make_history.py --days 14 --fresh
    .venv\\Scripts\\python.exe scripts\\make_history.py --days 14 --password dorm123
    .venv\\Scripts\\python.exe scripts\\make_history.py --list-passwords
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 自动对齐服务的数据目录（服务的 DORM_DATA_DIR 写在 systemd 单元里）
sys.path.insert(0, str(Path(__file__).resolve().parent))
import server_env  # noqa: E402

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

print(f"数据目录：{server_env.DATA_DIR}")

from sqlalchemy import delete, select  # noqa: E402

from backend.database import SessionLocal, init_db  # noqa: E402
from backend.models import AuditLog, Dorm, PushLog, Report, ReportCheckin  # noqa: E402
from backend.services import report_service, settings_service as ss  # noqa: E402
from backend.security import hash_password  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

REASONS = ["回家", "病假", "事假", "外出", "实习", "参加比赛"]

# 演示用的常见设备（让「填写日志」里的设备列看起来真实）
DEMO_AGENTS = [
    "Mozilla/5.0 (Linux; Android 14; PGT-AN10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36 MicroMessenger/8.0.49",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1 MicroMessenger/8.0.48",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0",
    "Mozilla/5.0 (Linux; Android 13; V2218A) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 QQ/8.9.88",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14, help="生成最近多少天的历史填报")
    parser.add_argument("--password", default="", help="给所有宿舍长账号设置这个初始密码")
    parser.add_argument("--fresh", action="store_true", help="先清空已有填报记录")
    parser.add_argument("--list-passwords", action="store_true", help="只打印宿舍长账号密码清单")
    parser.add_argument("--seed", type=int, default=20240501)
    args = parser.parse_args()

    random.seed(args.seed)
    init_db()
    db = SessionLocal()
    ss.ensure_settings(db)

    dorms = report_service.list_dorms(db)
    if not dorms:
        print("还没有宿舍，请先用「宿舍与人员 · 导入人员信息」导入名单。")
        return 1

    if args.list_passwords:
        return print_passwords(db)

    if args.fresh:
        db.execute(delete(ReportCheckin))
        db.execute(delete(Report))
        db.commit()
        print("已清空历史填报记录")

    if args.password:
        for dorm in dorms:
            dorm.leader_password = hash_password(args.password)
        db.commit()
        print(f"已把 {len(dorms)} 间寝室的验证密码设为：{args.password}")

    today = date.today()
    created = 0
    for offset in range(args.days - 1, -1, -1):
        day = today - timedelta(days=offset)
        for dorm in dorms:
            members = report_service.dorm_members(db, dorm.id)
            if not members:
                continue
            if offset == 0 and random.random() < 0.25:
                continue  # 今天留几间没填，方便演示催填
            if offset != 0 and random.random() < 0.1:
                continue  # 历史里也偶尔漏填
            absent = random.sample(members, 1) if members and random.random() < 0.2 else []
            checkins = [
                {
                    "member_id": m.id,
                    "name": m.name,
                    "present": m not in absent,
                    "reason": random.choice(REASONS) if m in absent else "",
                }
                for m in members
            ]
            note = ""
            if absent:
                reason = next((c["reason"] for c in checkins if c["member_id"] == absent[0].id), "外出")
                note = f"{absent[0].name}：{reason}，已向辅导员报备"
            report = report_service.apply_report(
                db,
                dorm,
                day,
                is_complete=not absent,
                absent_names="、".join(m.name for m in absent),
                note=note,
                checkins=checkins,
                source=random.choice(["web", "web", "web", "qq"]),
                submitter=dorm.leader_name or dorm.room_no,
                raw_message="" if random.random() > 0.15 else f"{dorm.room_no} 人齐",
                ip=f"10.24.{random.randint(1, 60)}.{random.randint(2, 250)}",
                user_agent=random.choice(DEMO_AGENTS),
            )
            report.submitted_at = report.submitted_at.replace(
                hour=random.choice([20, 21, 21, 22, 22, 22, 23]), minute=random.randint(0, 59)
            )
            created += 1
        db.commit()

    stats = report_service.day_stats(db, today)
    print(f"已生成 {created} 条历史填报（最近 {args.days} 天，{len(dorms)} 间宿舍）")
    print(f"今日：应查 {stats['dorm_total']} 间，已填 {stats['reported']} 间，未填 {stats['unreported']} 间")
    db.close()

    checks = [
        ("宿舍数量不为零", len(dorms) >= 1),
        ("历史填报已生成", created > 0),
        ("今日统计可用", stats["dorm_total"] == len(dorms)),
    ]
    passed = sum(1 for _name, ok in checks if ok)
    for name, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {name}")
    print(f"\n通过 {passed} 项，失败 {len(checks) - passed} 项")
    return 1 if passed != len(checks) else 0


def print_passwords(db) -> int:
    dorms = report_service.list_dorms(db)
    print(f"共 {len(dorms)} 间宿舍，宿舍长登录名 = 宿舍号：")
    for dorm in dorms:
        state = "已设验证密码" if dorm.leader_password else "未设密码（谁都能直接填报）"
        print(f"  {dorm.room_no:>8}  寝室长 {dorm.leader_name or '未指定':<8} 登录名 {dorm.room_no:<8} {state}")
    passed = 1 if dorms else 0
    print(f"\n通过 {passed} 项，失败 {0 if dorms else 1} 项")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
