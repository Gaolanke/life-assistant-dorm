"""查看 / 重置管理员账号密码（服务器上忘了密码时用）。

用法：
    python scripts/admin_account.py --list               # 看有哪些账号
    python scripts/admin_account.py --reset              # 把 admin 密码重置成随机 6 位并打印
    python scripts/admin_account.py --reset --password 我的新密码
    python scripts/admin_account.py --new teacher01      # 新建一个管理员账号
"""
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server_env  # noqa: E402

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from backend.database import SessionLocal, init_db  # noqa: E402
from backend.models import Account, Dorm  # noqa: E402
from backend.security import ensure_owner_account, hash_password  # noqa: E402
from backend.services import settings_service as ss  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

print(f"数据目录：{server_env.DATA_DIR}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="列出所有账号")
    parser.add_argument("--reset", action="store_true", help="重置管理员密码")
    parser.add_argument("--username", default="admin", help="要操作哪个账号（默认 admin）")
    parser.add_argument("--password", default="", help="指定新密码；留空则随机生成")
    parser.add_argument("--new", default="", help="新建一个管理员账号")
    parser.add_argument("--display", default="", help="新账号的姓名")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        ss.ensure_settings(db)

        if args.new:
            name = args.new.strip()
            if db.execute(select(Account).where(Account.username == name)).scalar_one_or_none():
                print(f"账号 {name} 已经存在")
                return 1
            raw = args.password.strip() or f"{secrets.randbelow(900000) + 100000}"
            db.add(
                Account(
                    username=name,
                    display_name=args.display.strip() or name,
                    password_hash=hash_password(raw),
                    role="admin",
                    must_change=True,
                )
            )
            db.commit()
            print(f"已创建管理员账号：{name}")
            print(f"初始密码：{raw}")
            return 0

        if args.reset:
            account = db.execute(
                select(Account).where(Account.username == args.username)
            ).scalar_one_or_none()
            if account is None:
                owner, initial = ensure_owner_account(db)
                print(f"没有找到 {args.username}，已确保存在超级管理员：{owner.username}")
                if initial:
                    print(f"初始密码：{initial}")
                return 0
            if account.role != "admin":
                print(f"{account.username} 不是管理员账号（角色：{account.role}）")
                return 1
            raw = args.password.strip() or f"{secrets.randbelow(900000) + 100000}"
            if len(raw) < 6:
                print("密码至少 6 位")
                return 1
            account.password_hash = hash_password(raw)
            account.active = True
            account.must_change = True
            db.commit()
            print(f"已重置 {account.username} 的密码")
            print(f"新密码：{raw}")
            print("（用这个密码登录管理端，登录后到「账号管理」改成自己的）")
            return 0

        # 默认 / --list：列出账号
        accounts = list(db.execute(select(Account).order_by(Account.role, Account.username)).scalars())
        dorms = {dorm.id: dorm for dorm in db.execute(select(Dorm)).scalars()}
        print(f"\n共 {len(accounts)} 个账号：")
        for account in accounts:
            role = "管理员" if account.role == "admin" else "寝室长"
            room = dorms.get(account.dorm_id)
            extra = f" 绑定 {room.room_no}" if room else ""
            flag = "（超级管理员）" if account.is_owner else ""
            state = "启用" if account.active else "已停用"
            print(f"  {account.username:<14} {role:<4} {account.display_name or '':<10} {state}{flag}{extra}")
            if account.last_login_at:
                print(f"      最近登录：{account.last_login_at:%Y-%m-%d %H:%M} 来自 {account.last_login_ip or '—'}")
        code = ss.get_setting(db, "admin_code")
        if code:
            print(f"\n初始密码（settings.admin_code，admin 账号首次安装时用它）：{code}")
        print("\n忘了密码就执行： .venv/bin/python scripts/admin_account.py --reset")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
