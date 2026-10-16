"""把服务器上的业务数据清空（宿舍、人员、填报、日志、已授权设备）。

用法（在服务器上，项目目录内执行）：
    .venv/bin/python scripts/reset_server_data.py          # 清空业务数据（保留配置与访问码）
    .venv/bin/python scripts/reset_server_data.py --all    # 连配置和访问码一起重置
    .venv/bin/python scripts/reset_server_data.py --status # 只看当前有多少数据

注意：清空后需要重启服务（systemctl restart dorm），让服务重新建表。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 自动对齐服务的数据目录（服务的 DORM_DATA_DIR 写在 systemd 单元里）
sys.path.insert(0, str(Path(__file__).resolve().parent))
import server_env  # noqa: E402

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

print(f"数据目录：{server_env.DATA_DIR}")

from sqlalchemy import delete, func, select  # noqa: E402

from backend.database import SessionLocal, init_db  # noqa: E402
from backend.models import (  # noqa: E402
    Account,
    AuditLog,
    Dorm,
    FundEntry,
    Member,
    PushLog,
    Report,
    ReportCheckin,
)

TABLES = (
    (ReportCheckin, "填报明细"),
    (Report, "填报记录"),
    (Member, "人员"),
    (Dorm, "宿舍"),
    (FundEntry, "班费明细"),
    (PushLog, "推送日志"),
    (AuditLog, "操作日志"),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="连系统配置和访问码一起清空")
    parser.add_argument("--status", action="store_true", help="只查看当前数据量")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        if args.status:
            print("当前数据：")
            for model, label in TABLES:
                count = db.execute(select(func.count()).select_from(model)).scalar() or 0
                print(f"  {label:<16} {count}")
            accounts = db.execute(select(func.count()).select_from(Account)).scalar() or 0
            print(f"  {'登录账号':<16} {accounts}（保留管理员账号）")
            return 0

        print("清空业务数据：")
        for model, label in TABLES:
            removed = db.execute(delete(model)).rowcount or 0
            print(f"  {label:<16} 删除 {removed}")
        # 寝室长账号跟着寝室一起清掉，管理员账号保留
        removed = db.execute(delete(Account).where(Account.role == "leader")).rowcount or 0
        print(f"  {'寝室长账号':<16} 删除 {removed}")
        if args.all:
            from backend.models import FundSetting, Setting

            removed = db.execute(delete(FundSetting)).rowcount or 0
            print(f"  {'班费设置':<16} 删除 {removed}")
            removed = db.execute(delete(Setting)).rowcount or 0
            print(f"  {'系统配置':<16} 删除 {removed}")
            removed = db.execute(delete(Account)).rowcount or 0
            print(f"  {'登录账号':<16} 删除 {removed}（含管理员，重启后会重建 admin）")

        db.commit()
        print("\n完成。请执行： systemctl restart dorm")
        print("重启后：")
        print("  · 打开管理端口（默认 8091）→ 用管理员账号登录（默认 admin / 原访问码）")
        print("  · 「宿舍与人员」导入名单，「账号管理」建寝室长账号或设置密码")
        if args.all:
            print("  · 账号已全部清空，重启时日志里会打印新的 admin 初始密码")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
