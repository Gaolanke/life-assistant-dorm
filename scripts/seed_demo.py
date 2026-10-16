"""生成本地演示数据：宿舍、人员、历史填报记录。

用法： .venv\\Scripts\\python.exe scripts\\seed_demo.py [--reset]

--reset  先清空所有业务数据（人员/填报/推送日志），配置和账户保留
"""
from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 自动对齐服务的数据目录（服务的 DORM_DATA_DIR 写在 systemd 单元里）
sys.path.insert(0, str(Path(__file__).resolve().parent))
import server_env  # noqa: E402

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

print(f"数据目录：{server_env.DATA_DIR}")

from sqlalchemy import delete, select  # noqa: E402

from backend.database import SessionLocal, init_db  # noqa: E402
from backend.models import (  # noqa: E402
    Account,
    AuditLog,
    Dorm,
    Member,
    PushLog,
    Report,
    ReportCheckin,
)
from backend.security import ensure_owner_account, hash_password  # noqa: E402
from backend.services import report_service, settings_service as ss  # noqa: E402
from backend.util import now_local  # noqa: E402

random.seed(20240501)

DORM_DATA = [
    ("3-201", "3号楼", "张伟", "13800000101", ["张伟", "李强", "王磊", "赵鹏"]),
    ("3-202", "3号楼", "刘洋", "13800000102", ["刘洋", "陈晨", "杨帆", "周涛"]),
    ("3-203", "3号楼", "吴迪", "13800000103", ["吴迪", "郑浩", "孙宇", "马超"]),
    ("3-204", "3号楼", "朱琳", "13800000104", ["朱琳", "胡敏", "林小雨", "何静"]),
    ("4-101", "4号楼", "徐磊", "13800000105", ["徐磊", "高翔", "邓超", "曹阳"]),
    ("4-102", "4号楼", "谢婷", "13800000106", ["谢婷", "罗素", "唐糖", "冯雪"]),
]

SURNAMES = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张"


def student_no(index: int) -> str:
    return f"2023{index:06d}"


def clear_business(db) -> None:
    for model in (ReportCheckin, Report, Member, Dorm, PushLog, AuditLog):
        db.execute(delete(model))
    db.commit()
    print("已清空人员 / 填报 / 日志数据")


def main() -> None:
    reset = "--reset" in sys.argv
    init_db()
    db = SessionLocal()
    ss.ensure_settings(db)
    # 保证有一个可登录的超级管理员账号（首次安装时初始密码 = settings.admin_code）
    owner, initial_password = ensure_owner_account(db)
    print(f"超级管理员账号：{owner.username}")
    if initial_password:
        print(f"初始密码：{initial_password}")
    if reset:
        clear_business(db)

    created_dorms = 0
    created_members = 0
    counter = 1
    for room_no, building, leader, phone, names in DORM_DATA:
        dorm = db.execute(select(Dorm).where(Dorm.room_no == room_no)).scalar_one_or_none()
        if dorm is None:
            dorm = Dorm(
                room_no=room_no,
                building=building,
                leader_name=leader,
                leader_phone=phone,
                qq_group_id="",  # 演示：不绑定群，用系统默认群
                note="演示数据",
                active=True,
            )
            db.add(dorm)
            db.commit()
            db.refresh(dorm)
            created_dorms += 1
        existing = {m.name for m in report_service.dorm_members(db, dorm.id, active_only=False)}
        for index, name in enumerate(names):
            if name in existing:
                continue
            db.add(
                Member(
                    dorm_id=dorm.id,
                    name=name,
                    student_no=student_no(counter * 7 + index),
                    phone=f"138{random.randint(10000000, 99999999)}",
                    room_no=room_no,
                    role="宿舍长" if index == 0 else "成员",
                )
            )
            created_members += 1
        db.commit()
        # 寝室长登录：密码可选。这里把演示寝室的验证密码设成 dorm123，
        # 并同步建一个「用户名 = 宿舍号」的寝室长账号，两条路都能登。
        raw_password = "dorm123"
        dorm.leader_password = hash_password(raw_password)
        account = db.execute(
            select(Account).where(Account.username == dorm.room_no)
        ).scalar_one_or_none()
        if account is None:
            db.add(
                Account(
                    username=dorm.room_no,
                    display_name=dorm.leader_name or dorm.room_no,
                    password_hash=hash_password(raw_password),
                    role="leader",
                    dorm_id=dorm.id,
                    note="演示数据",
                )
            )
        else:
            account.password_hash = hash_password(raw_password)
            account.role = "leader"
            account.dorm_id = dorm.id
            account.active = True
        db.commit()

    dorms = report_service.list_dorms(db)
    print(f"宿舍 {len(dorms)} 间，新增 {created_dorms} 间 / 人员 {created_members} 人")

    # 历史填报：最近 21 天
    today = date.today()
    created_reports = 0
    for offset in range(20, -1, -1):
        day = today - timedelta(days=offset)
        for dorm in dorms:
            members = report_service.dorm_members(db, dorm.id)
            # 今天：只让一部分宿舍填报，方便演示“未填报提醒”
            if offset == 0 and dorm.room_no in {"3-203", "4-102"}:
                continue
            if offset != 0 and random.random() < 0.12:
                continue  # 模拟偶尔忘记填报
            absent = []
            if random.random() < 0.22:
                absent = random.sample(members, 1) if len(members) > 1 else members[:1]
            checkins = [
                {
                    "member_id": m.id,
                    "name": m.name,
                    "present": m not in absent,
                    "reason": random.choice(["回家", "病假", "事假", "外出", "实习"]) if m in absent else "",
                }
                for m in members
            ]
            note = ""
            if absent:
                note = f"{absent[0].name}：{checkins[0]['reason'] or '外出'}，家长已知晓"
            hour = random.choice([20, 21, 21, 22, 22, 22, 23])
            minute = random.randint(0, 59)
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
                raw_message="" if random.random() > 0.2 else f"{dorm.room_no} 人齐",
            )
            report.submitted_at = report.submitted_at.replace(hour=hour, minute=minute)
            created_reports += 1
        db.commit()
    print(f"填报记录 {created_reports} 条")

    ss.update_settings(
        db,
        {
            "school_name": "示例大学",
            "class_name": "计算机学院 2023 级 1 班",
            "commissary_name": "李生活",
            "teacher_name": "王老师",
            "qqbot_enabled": "0",
        },
    )
    print("演示配置已写入（QQ 官方机器人保持关闭，避免误发消息）")

    stats = report_service.day_stats(db, today)
    print(f"今日：应查 {stats['dorm_total']} 间，已填 {stats['reported']} 间，未填 {stats['unreported']} 间")
    final_dorms = report_service.list_dorms(db, active_only=False)
    leader_accounts = list(
        db.execute(select(Account).where(Account.role == "leader")).scalars()
    )
    db.close()
    print("\n演示数据准备完成。寝室长账号：宿舍号 / 密码 dorm123（例如 3-201 / dorm123）")
    print("管理员账号：admin，密码就是「初始密码」那一行（settings.admin_code）。")
    print("忘了密码就执行： .venv\\Scripts\\python.exe scripts\\admin_account.py --reset --password 新密码")

    checks = [
        ("演示宿舍已写入", len(final_dorms) >= len(DORM_DATA)),
        ("每个演示宿舍都有寝室长账号", len(leader_accounts) >= len(DORM_DATA)),
        ("历史填报已生成", created_reports > 0),
    ]
    passed = sum(1 for _name, ok in checks if ok)
    for name, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {name}")
    print(f"\n通过 {passed} 项，失败 {len(checks) - passed} 项")


if __name__ == "__main__":
    main()
