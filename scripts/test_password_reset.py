"""验证：寝室长密码的设置 / 重置 / 取消。

用法： .venv\\Scripts\\python.exe scripts\\test_password_reset.py [管理端口] [公开端口]
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import server_env  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8")

ADMIN = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8091"
PUBLIC = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8090"
PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} :: {detail}")
    print(f"  [{'OK' if ok else 'FAIL'}] {name}{'' if ok else '  ' + detail}")


def main() -> int:
    from auth_client import ensure_admin_client, public_client

    from backend.database import SessionLocal
    from backend.models import Dorm

    admin = ensure_admin_client(base=ADMIN)
    check("管理员账号登录成功", bool(admin.headers.get("X-Session-Token")), "没有拿到会话令牌")

    dorms = admin.get("/api/dorms?with_members=true&active_only=false").json()["items"]
    if not dorms:
        print("  没有寝室数据，请先导入名单")
        return 2
    dorm = dorms[0]
    room = dorm["room_no"]
    public = public_client(PUBLIC)

    def locked_db() -> bool:
        session = SessionLocal()
        row = session.get(Dorm, dorm["id"])
        value = bool(row.leader_password)
        session.close()
        return value

    def api_locked() -> bool:
        return public.get("/api/reports/dorm/" + str(dorm["id"])).json()["locked"]

    def submit(room_password: str = "") -> int:
        headers = {}
        if room_password:
            login = public.post("/api/access/leader/login", json={"room_no": room, "password": room_password})
            if login.status_code == 200:
                headers["X-Leader-Token"] = login.json()["token"]
        return public.post(
            "/api/reports/submit",
            headers=headers,
            json={"dorm_id": dorm["id"], "is_complete": True, "note": "密码测试", "submitter": "测试"},
        ).status_code

    print("\n== 1. 设置密码 ==")
    res = admin.post("/api/access/leader/password", json={"dorm_id": dorm["id"], "action": "set", "password": "first123"})
    check("按指定密码设置成功", res.status_code == 200 and res.json()["password"] == "first123", res.text[:160])
    check("数据库里已有密码", locked_db())
    check("接口对外显示为锁定", api_locked() is True)
    check("正确密码能进", public.post("/api/access/leader/login", json={"room_no": room, "password": "first123"}).status_code == 200)
    check("错误密码被拒", public.post("/api/access/leader/login", json={"room_no": room, "password": "nope9999"}).status_code == 403)
    check("未验证不能填报", submit() == 403, str(submit()))
    check("用该密码可以填报", submit("first123") == 200)

    print("\n== 2. 重置密码（忘了旧密码的情况） ==")
    res = admin.post("/api/access/leader/password", json={"dorm_id": dorm["id"], "action": "random"})
    check("随机重置成功", res.status_code == 200 and len(res.json()["password"]) >= 4, res.text[:160])
    new_password = res.json()["password"]
    check("重置后返回新密码", new_password != "first123", new_password)
    check("旧密码立即失效", public.post("/api/access/leader/login", json={"room_no": room, "password": "first123"}).status_code == 403)
    check("新密码可以登录", public.post("/api/access/leader/login", json={"room_no": room, "password": new_password}).status_code == 200)
    check("重置后依然锁定", api_locked() is True and submit() == 403)

    print("\n== 3. 改成自己指定的密码 ==")
    res = admin.post("/api/access/leader/password", json={"dorm_id": dorm["id"], "action": "set", "password": "mynew2025"})
    check("可以改成一个自己喜欢的密码", res.status_code == 200 and res.json()["password"] == "mynew2025", res.text[:160])
    check("新密码生效", public.post("/api/access/leader/login", json={"room_no": room, "password": "mynew2025"}).status_code == 200)
    check("上一次的密码失效", public.post("/api/access/leader/login", json={"room_no": room, "password": new_password}).status_code == 403)

    print("\n== 4. 取消密码（恢复公开填报） ==")
    res = admin.post("/api/access/leader/password", json={"dorm_id": dorm["id"], "action": "clear"})
    check("取消密码成功", res.status_code == 200 and res.json().get("action") == "clear", res.text[:160])
    check("提示语说明已恢复公开", "任何人都能" in res.json().get("message", ""), res.text[:160])
    check("数据库里密码已清空", locked_db() is False)
    check("接口对外不再是锁定", api_locked() is False)
    check("取消后任何人都能填报", submit() == 200, str(submit()))
    check("取消后寝室长登录会提示没设密码", "没有设置验证密码" in public.post(
        "/api/access/leader/login", json={"room_no": room, "password": "anything"}
    ).text)

    print("\n== 5. 取消后还能再设回来 ==")
    res = admin.post("/api/access/leader/password", json={"dorm_id": dorm["id"], "action": "set", "password": "again123"})
    check("可以重新设置密码", res.status_code == 200 and locked_db() is True, res.text[:160])
    check("重新设置后又锁上了", api_locked() is True and submit() == 403)

    print("\n== 6. 参数校验与兼容 ==")
    res = admin.post("/api/access/leader/password", json={"dorm_id": dorm["id"], "action": "set", "password": "123"})
    check("密码太短被拒绝", res.status_code == 400, str(res.status_code))
    res = admin.post("/api/access/leader/password", json={"dorm_id": dorm["id"], "action": "set", "password": ""})
    check("设密码却不填密码被拒绝", res.status_code == 400, str(res.status_code))
    # 老写法：只传 password（不传 action）
    res = admin.post("/api/access/leader/password", json={"dorm_id": dorm["id"], "password": "legacy123"})
    check("老写法（只传 password）仍然可用", res.status_code == 200 and res.json()["password"] == "legacy123", res.text[:160])
    res = admin.post("/api/access/leader/password", json={"dorm_id": dorm["id"], "password": ""})
    check("老写法留空仍是随机生成", res.status_code == 200 and len(res.json()["password"]) == 6, res.text[:160])

    print("\n== 7. 收尾：把这间寝室恢复成无密码 ==")
    admin.post("/api/access/leader/password", json={"dorm_id": dorm["id"], "action": "clear"})
    check("已恢复无密码", locked_db() is False)

    print("\n" + "=" * 56)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    for item in FAIL:
        print("  - " + item)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
