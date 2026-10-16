"""把一份真实的宿舍人员名单导入本地系统（走导入接口，和网页上操作完全一致）。

认证方式：用管理员账号登录（POST /api/auth/login）拿会话令牌，管理接口带
`X-Session-Token`。密码默认取本地 data/app.db 的 settings.admin_code，
也可以用 --password 指定。

用法：
    .venv\\Scripts\\python.exe scripts\\import_roster.py "新区宿舍物联网25-2(1).xlsx" --yes
    .venv\\Scripts\\python.exe scripts\\import_roster.py "新区宿舍物联网25-2(1).xlsx" --base http://127.0.0.1:8091 --strategy merge

会先清空已有宿舍与填报数据（--keep 可保留），再导入名单。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

FIELD_NAMES = {"name": "姓名", "student_no": "学号", "phone": "电话号", "room_no": "宿舍号",
               "role": "角色", "grade": "年级/班级"}

# settings.admin_code 只有在 admin 从没改过密码时才等于登录密码。
# 本地开发时密码常被改过，这里再兜底试一次测试脚本常用的密码，避免命令白跑。
DEV_FALLBACK_PASSWORD = "testadmin123"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="Excel 文件路径")
    parser.add_argument("--base", default="http://127.0.0.1:8091")
    parser.add_argument("--strategy", default="overwrite", choices=["merge", "overwrite"])
    parser.add_argument("--keep", action="store_true", help="保留已有宿舍（默认先清空）")
    parser.add_argument("--yes", action="store_true", help="跳过确认")
    parser.add_argument("--device", default="import-script-device", help="（已废弃，保留兼容）")
    parser.add_argument("--user", default="admin", help="管理员用户名（默认 admin）")
    parser.add_argument(
        "--password",
        "--code",
        dest="password",
        default="",
        help="管理员密码（默认从本地 data/app.db 的 settings.admin_code 读取）",
    )
    args = parser.parse_args()

    path = Path(args.file)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        print(f"找不到文件：{path}")
        return 1

    sys.path.insert(0, str(ROOT))
    from backend.database import SessionLocal
    from backend.services import settings_service as ss

    code = args.password
    if not code:
        db = SessionLocal()
        ss.ensure_settings(db)
        code = ss.get_setting(db, "admin_code")
        db.close()

    candidates = [value for value in (code, DEV_FALLBACK_PASSWORD) if value]
    client = httpx.Client(base_url=args.base, timeout=60.0)
    health = client.get("/api/health")
    if health.status_code != 200:
        print(f"服务没启动或地址不对：{args.base}")
        return 1
    login = None
    for guess in candidates:
        login = client.post("/api/auth/login", json={"username": args.user, "password": guess})
        if login.status_code == 200 and login.json().get("ok"):
            break
    if login is None or login.status_code != 200 or not login.json().get("ok"):
        print(f"管理员登录失败：{login.text[:200] if login is not None else '没有可用的密码'}")
        print(
            "提示：脚本默认拿本地 data/app.db 里的 settings.admin_code 当密码（首次安装时的初始密码）。"
            "如果 admin 的密码已经改过，请用 --password 指定，"
            "或先运行 scripts/admin_account.py --reset --password <新密码>。"
        )
        return 1
    client.headers["X-Session-Token"] = login.json()["token"]
    print(f"已用管理员账号 {login.json()['account']['username']} 登录（{args.base}）")

    existing = client.get("/api/dorms?with_members=false&active_only=false").json()["items"]
    if existing and not args.keep:
        if not args.yes:
            answer = input(f"将清空已有 {len(existing)} 间宿舍及其人员、填报记录，确认继续？(y/N) ").strip().lower()
            if answer not in {"y", "yes"}:
                print("已取消")
                return 0
        purge = client.post("/api/system/reset-data", json={"keep_accounts": True, "keep_settings": True})
        if purge.status_code != 200:
            print(f"清空失败：{purge.text[:200]}")
            return 1
        print("已清空原有宿舍与填报数据")

    with path.open("rb") as handle:
        preview = client.post(
            "/api/members/import/preview",
            files={"file": (path.name, handle.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    data = preview.json()
    if preview.status_code != 200 or not data.get("ok"):
        print(f"解析失败：{data.get('message')}")
        return 1

    print(f"\n文件：{path.name}  工作表：{data['sheet']}  有效行：{data['total_rows']}")
    print("列识别：" + "，".join(f"{v} → {FIELD_NAMES.get(k, k)}" for k, v in (data.get("mapping") or {}).items()))
    if data.get("skipped"):
        print("已跳过：" + "；".join(data["skipped"][:5]))
    print(f"\n共 {data['total_dorms']} 间宿舍、{data['total_members']} 人：")
    for group in data["groups"]:
        leaders = "、".join(group.get("leaders") or []) or "未标记"
        print(f"  {group['room_no']:>6}  楼栋 {group.get('building') or '—':<6} {group['incoming_count']} 人  宿舍长：{leaders}   {group.get('room_label', '')}")

    if not args.yes:
        answer = input(f"\n确认按“{args.strategy}”方式导入？(y/N) ").strip().lower()
        if answer not in {"y", "yes"}:
            print("已取消")
            return 0

    commit = client.post(
        "/api/members/import/commit",
        json={"token": data["token"], "strategy": args.strategy, "update_member": True},
    )
    result = commit.json()
    if commit.status_code != 200 or not result.get("ok"):
        print(f"导入失败：{result.get('message')}")
        return 1
    print(f"\n{result['message']}")

    accounts = client.get("/api/access/leader/accounts").json()["items"]
    no_password = [d for d in accounts if not d["has_password"]]
    print(f"\n共 {len(accounts)} 间寝室，其中 {len(no_password)} 间还没有寝室长验证密码。")
    if no_password:
        print("提示：打开「管理控制台 → 寝室长验证账号」→「给没有密码的寝室批量生成」，")
        print("      就能一次拿到「宿舍号 + 密码」清单发到各宿舍群；寝室长不验证也能普通填报。")

    checks = [
        ("管理员登录", True),
        ("名单解析", result.get("created_dorms", 0) + result.get("created_members", 0) > 0),
        ("寝室列表可读", len(accounts) == data["total_dorms"]),
    ]
    passed = sum(1 for _name, ok in checks if ok)
    failed = len(checks) - passed
    for name, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {name}")
    print(f"\n通过 {passed} 项，失败 {failed} 项")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
