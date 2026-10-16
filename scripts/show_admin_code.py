"""在服务器上查看「管理员初始密码」和账号清单。

注意：程序已经改成账号登录了，``settings.admin_code`` 只是**首次安装时**给
admin 账号用的初始密码；如果 admin 后来自己改过密码，这个值就不再是登录密码了。
真正忘了密码请用 scripts/admin_account.py --reset。

用法（服务器上，项目目录内）：
    .venv/bin/python scripts/show_admin_code.py            # 显示初始密码 + 账号清单
    .venv/bin/python scripts/show_admin_code.py --reset    # 重新生成一个新的初始密码
    .venv/bin/python scripts/show_admin_code.py --accounts # 只看账号清单
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

from sqlalchemy import select  # noqa: E402

from backend.database import SessionLocal, init_db  # noqa: E402
from backend.models import Account, Dorm  # noqa: E402
from backend.security import new_access_code  # noqa: E402
from backend.services import settings_service as ss  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="重新生成初始密码（旧的立即失效）")
    parser.add_argument("--accounts", action="store_true", help="列出所有登录账号")
    # 兼容老参数：以前是「列出现已授权的设备」，设备授权已经取消，现在改成列账号
    parser.add_argument("--devices", action="store_true", help="（旧参数）现在等价于 --accounts")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        ss.ensure_settings(db)
        code = ss.get_setting(db, "admin_code")
        if args.reset or not code:
            code = new_access_code()
            ss.set_setting(db, "admin_code", code)
            db.commit()
            print("已生成新的初始密码" if args.reset else "首次生成初始密码")
        print(f"\n管理员初始密码（settings.admin_code）：{code}\n")
        print("用法：在管理端口（默认 8091）打开网页 → 用账号 admin + 上面的初始密码登录。")
        print("注意：admin 自己改过密码后，这个值就不再是登录密码了；")
        print("      忘了密码请执行： .venv/bin/python scripts/admin_account.py --reset --password 新密码")

        checks = [("管理员初始密码可读", bool(code))]
        if args.accounts or args.devices:
            accounts = list(
                db.execute(select(Account).order_by(Account.role, Account.username)).scalars()
            )
            dorms = {dorm.id: dorm for dorm in db.execute(select(Dorm)).scalars()}
            print(f"\n登录账号（{len(accounts)} 个）：")
            for account in accounts:
                role = "管理员" if account.role == "admin" else "寝室长"
                dorm = dorms.get(account.dorm_id)
                extra = f"  绑定 {dorm.room_no}" if dorm else ""
                flag = "（超级管理员）" if account.is_owner else ""
                state = "启用" if account.active else "已停用"
                last = (
                    account.last_login_at.strftime("%Y-%m-%d %H:%M")
                    if account.last_login_at
                    else "从未登录"
                )
                print(f"  {account.username:<16} {role:<4} {state}{flag}{extra}  最近登录 {last}")
            checks.append(("账号清单可读", len(accounts) >= 1))

        passed = sum(1 for _name, ok in checks if ok)
        for name, ok in checks:
            print(f"  [{'OK' if ok else 'FAIL'}] {name}")
        print(f"\n通过 {passed} 项，失败 {len(checks) - passed} 项")
        return 1 if passed != len(checks) else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
