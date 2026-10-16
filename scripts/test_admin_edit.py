"""验证：管理员账号自助改密码 + 管理员给选定寝室设置 / 重置 / 取消密码。

说明：改密码这一节用的是**临时管理员账号**，不会动 admin 本身的密码。

用法： .venv\\Scripts\\python.exe scripts\\test_admin_edit.py [管理端口] [公开端口]
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 自动对齐服务的数据目录（服务的 DORM_DATA_DIR 写在 systemd 单元里）
sys.path.insert(0, str(Path(__file__).resolve().parent))
import server_env  # noqa: E402

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auth_client import (  # noqa: E402
    ADMIN_BASE,
    PUBLIC_BASE,
    ensure_admin_client,
    login,
    public_client,
    try_login,
)

ADMIN = sys.argv[1] if len(sys.argv) > 1 else ADMIN_BASE
PUBLIC = sys.argv[2] if len(sys.argv) > 2 else PUBLIC_BASE
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8")

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} :: {detail}")
    print(f"  [{'OK' if ok else 'FAIL'}] {name}{'' if ok else '  ' + detail}")


def main() -> int:
    print(f"数据目录：{server_env.DATA_DIR}")

    admin = ensure_admin_client(base=ADMIN)
    public = public_client(PUBLIC)

    tmp_user = f"tmpadm{random.randint(1000, 9999)}"
    tmp_id = 0

    print("\n== 1. 管理员账号可以自己改密码（用临时账号验证） ==")
    created = admin.post("/api/accounts", json={
        "username": tmp_user,
        "password": "tmp123456",
        "display_name": "临时管理员",
        "role": "admin",
    })
    check("可以新建一个管理员账号", created.status_code == 200 and created.json()["ok"], created.text[:200])
    if created.status_code == 200:
        tmp_id = created.json()["account"]["id"]

    code, _ = try_login(base=ADMIN, username=tmp_user, password="tmp123456")
    check("临时账号可以登录", code == 200, f"状态码 {code}")

    _client, token, _account = login(
        base=ADMIN, username=tmp_user, password="tmp123456"
    )
    tmp_client = httpx.Client(base_url=ADMIN, timeout=40, headers={"X-Session-Token": token})

    wrong_old = tmp_client.post("/api/auth/password", json={"old_password": "not-the-password", "new_password": "tmp654321"})
    check("原密码不对时拒绝改密码", wrong_old.status_code == 403, str(wrong_old.status_code))

    short = tmp_client.post("/api/auth/password", json={"old_password": "tmp123456", "new_password": "123"})
    check("新密码太短被拒绝", short.status_code == 400, str(short.status_code))

    changed = tmp_client.post("/api/auth/password", json={"old_password": "tmp123456", "new_password": "tmp654321"})
    check("改密码成功", changed.status_code == 200 and changed.json()["ok"], changed.text[:200])

    same = tmp_client.post("/api/auth/password", json={"old_password": "tmp654321", "new_password": "tmp654321"})
    check("新密码不能和原密码一样", same.status_code == 400, str(same.status_code))

    code, _ = try_login(base=ADMIN, username=tmp_user, password="tmp123456")
    check("旧密码已失效", code == 403, f"状态码 {code}")
    code, _ = try_login(base=ADMIN, username=tmp_user, password="tmp654321")
    check("新密码可以登录", code == 200, f"状态码 {code}")

    me = tmp_client.get("/api/auth/me").json()
    check("改完密码还是登录状态", me.get("logged_in") is True, str(me))
    tmp_client.close()

    print("\n== 2. 管理员给选定的寝室设置密码 ==")
    accounts = admin.get("/api/access/leader/accounts").json()["items"]
    check("能拿到寝室列表", len(accounts) >= 2, str(len(accounts)))
    if len(accounts) < 2:
        print("  至少需要 2 间寝室，请先导入名单")
        return 2
    first, second = accounts[0], accounts[1]

    res = admin.post("/api/access/leader/password", json={"dorm_id": first["dorm_id"], "action": "set", "password": "myRoom2025"})
    check("可以给单个寝室指定密码", res.status_code == 200 and res.json()["password"] == "myRoom2025", res.text[:200])
    check("返回的寝室号正确", res.json()["room_no"] == first["room_no"], res.text[:200])

    leader = public_client(PUBLIC)
    ok_login = leader.post("/api/access/leader/login", json={"room_no": first["room_no"], "password": "myRoom2025"})
    check("寝室长用这个密码能登录", ok_login.status_code == 200 and ok_login.json()["ok"], ok_login.text[:200])

    other_login = leader.post("/api/access/leader/login", json={"room_no": second["room_no"], "password": "myRoom2025"})
    check("别的寝室用这个密码登不上", other_login.status_code == 403, str(other_login.status_code))

    res = admin.post("/api/access/leader/password", json={"dorm_id": second["dorm_id"], "action": "random"})
    check("随机生成 6 位数字", res.status_code == 200 and len(res.json()["password"]) == 6, res.text[:200])
    check("随机生成的密码可用", leader.post(
        "/api/access/leader/login", json={"room_no": second["room_no"], "password": res.json()["password"]}
    ).status_code == 200)

    too_short = admin.post("/api/access/leader/password", json={"dorm_id": first["dorm_id"], "action": "set", "password": "123"})
    check("3 位密码被拒绝", too_short.status_code == 400, str(too_short.status_code))

    print("\n== 3. 改密码后旧密码失效 ==")
    admin.post("/api/access/leader/password", json={"dorm_id": first["dorm_id"], "action": "set", "password": "newpass123"})
    check("旧密码不能再登录", leader.post(
        "/api/access/leader/login", json={"room_no": first["room_no"], "password": "myRoom2025"}
    ).status_code == 403)
    check("新密码可以登录", leader.post(
        "/api/access/leader/login", json={"room_no": first["room_no"], "password": "newpass123"}
    ).status_code == 200)

    print("\n== 4. 没登录的人改不了这些 ==")
    check("公开端口没有设置寝室密码的接口", public.post(
        "/api/access/leader/password", json={"dorm_id": first["dorm_id"], "password": "hack"}
    ).status_code == 404)
    with httpx.Client(base_url=ADMIN, timeout=40, follow_redirects=True) as anon:
        check("未登录改不了寝室密码", anon.post(
            "/api/access/leader/password", json={"dorm_id": first["dorm_id"], "action": "set", "password": "hack123"}
        ).status_code == 401)
        check("未登录改不了账号密码", anon.post(
            "/api/auth/password", json={"old_password": "x", "new_password": "hack123"}
        ).status_code == 401)
        check("未登录建不了账号", anon.post(
            "/api/accounts", json={"username": "hacker", "password": "hack123"}
        ).status_code == 401)

    print("\n== 5. 收尾：恢复成无密码 + 删掉临时账号 ==")
    admin.post("/api/access/leader/password", json={"dorm_id": first["dorm_id"], "action": "clear"})
    admin.post("/api/access/leader/password", json={"dorm_id": second["dorm_id"], "action": "clear"})
    check("两间寝室已恢复无密码", all(
        item["has_password"] is False
        for item in admin.get("/api/access/leader/accounts").json()["items"]
        if item["dorm_id"] in (first["dorm_id"], second["dorm_id"])
    ))
    if tmp_id:
        deleted = admin.delete(f"/api/accounts/{tmp_id}")
        check("临时管理员账号已删除", deleted.status_code == 200 and deleted.json()["ok"], deleted.text[:200])

    admin.close()
    public.close()
    leader.close()

    print("\n" + "=" * 56)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    for item in FAIL:
        print("  - " + item)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
