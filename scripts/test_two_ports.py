"""双端口 + 账号登录 + 寝室长界面 自检。

用法： .venv\\Scripts\\python.exe scripts\\test_two_ports.py [公开端口] [管理端口]

默认： 公开端口 http://127.0.0.1:8090 ，管理端口 http://127.0.0.1:8091
"""
from __future__ import annotations

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
    public_client,
    try_login,
)

MAIN = sys.argv[1] if len(sys.argv) > 1 else PUBLIC_BASE
ADMIN = sys.argv[2] if len(sys.argv) > 2 else ADMIN_BASE
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8")

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} :: {detail}")
    print(f"  [{'OK' if ok else 'FAIL'}] {name}{'' if ok else '  ' + detail}")


def main() -> int:
    print(f"数据目录：{server_env.DATA_DIR}")

    public = public_client(MAIN)
    admin = ensure_admin_client(base=ADMIN)

    print("\n== 1. 两个端口的身份 ==")
    mode_public = public.get("/api/system/mode").json()
    mode_admin = admin.get("/api/system/mode").json()
    check("公开端口报告自己是 public", mode_public["mode"] == "public" and mode_public["is_admin_port"] is False, str(mode_public))
    check("管理端口报告自己是 admin", mode_admin["mode"] == "admin" and mode_admin["is_admin_port"] is True, str(mode_admin))
    check("两端口都标注了彼此端口号", mode_public["admin_port"] == mode_admin["port"], str(mode_public))
    check("两个端口页面都能打开", public.get("/").status_code == 200 and admin.get("/").status_code == 200)
    check("首页标题是「生活助手」", "生活助手" in public.get("/").text, public.get("/").text[:80].replace("\n", " "))

    print("\n== 2. 公开端口拿不到管理接口 ==")
    for path in (
        "/api/accounts",
        "/api/fund/summary",
        "/api/logs/audit",
        "/api/logs/submissions",
        "/api/access/code",
        "/api/access/devices",
        "/api/access/leader/accounts",
    ):
        res = public.get(path)
        check(f"公开端口 {path} 被隔离", res.status_code == 404, str(res.status_code))
    check("公开端口不能改配置", public.put("/api/settings", json={"values": {"school_name": "x"}}).status_code == 404)
    check("公开端口不能改寝室", public.post("/api/dorms", json={"room_no": "1-1"}).status_code == 404)
    check("公开端口不能重置数据", public.post("/api/system/reset-data", json={}).status_code == 404)
    check("公开端口不能看账号统计", public.get("/api/accounts/stats").status_code == 404)
    check("公开端口仍能读配置（填报页需要）", public.get("/api/settings").status_code == 200)
    check("公开端口仍能读寝室与填报", public.get("/api/dorms").status_code == 200 and public.get("/api/reports/today").status_code == 200)

    # 选一间没设密码的寝室验证「公开填报」这条路（设了密码的寝室本来就该被拦）
    dorms = public.get("/api/dorms?with_members=false").json()["items"]
    if not dorms:
        print("  没有寝室数据，请先导入名单")
        return 2
    plain_dorm = dorms[0]
    admin.post("/api/access/leader/password", json={"dorm_id": plain_dorm["id"], "action": "clear"})
    check("公开端口仍能提交填报（未设密码的寝室）", public.post("/api/reports/submit", json={
        "dorm_id": plain_dorm["id"],
        "is_complete": True, "note": "公开填报测试", "submitter": "被测同学",
    }).status_code == 200)

    print("\n== 3. 管理端口（登录后）能用管理接口 ==")
    code, _ = try_login(base=ADMIN, username="admin", password="wrong-password")
    check("管理端口错误密码被拒绝", code == 403, f"状态码 {code}")
    with httpx.Client(base_url=ADMIN, timeout=30, follow_redirects=True) as anon:
        check("管理端口未登录访问管理接口是 401", anon.get("/api/accounts").status_code == 401, "应返回 401")
        check("管理端口未登录访问班费是 401", anon.get("/api/fund/summary").status_code == 401, "应返回 401")
    check("管理端口登录后有令牌", bool(admin.headers.get("X-Session-Token")))
    check("管理端口能看账号列表", admin.get("/api/accounts").status_code == 200)
    check("管理端口能看到寝室长账号", admin.get("/api/access/leader/accounts").status_code == 200)
    check("管理端口能看填写日志", admin.get("/api/logs/submissions").status_code == 200)
    check("管理端口能看班费概览", admin.get("/api/fund/summary").status_code == 200)
    check("管理端口旧接口 /api/access/code 已下线", admin.get("/api/access/code").status_code == 404)
    accounts = admin.get("/api/access/leader/accounts").json()["items"]
    check("管理端口能列出所有寝室", len(accounts) >= 1, str(len(accounts)))

    print("\n== 4. 寝室长密码可选：没设密码时人人可填 ==")
    dorm = accounts[0]
    dorm_id, room_no = dorm["dorm_id"], dorm["room_no"]

    # 先清掉密码（模拟“不设置密码”）
    admin.post("/api/access/leader/password", json={"dorm_id": dorm_id, "action": "clear"})

    no_pwd = public.post("/api/access/leader/login", json={"room_no": room_no, "password": ""})
    check("没设密码时不能进寝室长界面", no_pwd.status_code == 403, str(no_pwd.status_code))
    check("提示语说明原因", "没有设置验证密码" in no_pwd.text, no_pwd.text[:160])

    members = public.get(f"/api/reports/dorm/{dorm_id}").json()["members"]
    res = public.post("/api/reports/submit", json={
        "dorm_id": dorm_id, "is_complete": True, "note": "无密码也能填",
        "submitter": "任何同学",
        "checkins": [{"member_id": m["id"], "present": True} for m in members],
    })
    check("没设密码时任何人都能正常填报", res.status_code == 200 and res.json()["ok"], res.text[:200])

    print("\n== 5. 管理员给该寝室设密码后进入寝室长界面 ==")
    set_pwd = admin.post("/api/access/leader/password", json={"dorm_id": dorm_id, "action": "set", "password": "room8888"})
    check("管理员设置了密码", set_pwd.status_code == 200 and set_pwd.json()["password"] == "room8888", set_pwd.text[:150])

    leader = public_client(MAIN)
    bad = leader.post("/api/access/leader/login", json={"room_no": room_no, "password": "wrong"})
    check("错误密码被拒绝", bad.status_code == 403, str(bad.status_code))

    login = leader.post("/api/access/leader/login", json={"room_no": room_no, "password": "room8888"})
    check("正确密码进入寝室长界面", login.status_code == 200 and login.json()["ok"], login.text[:200])
    token = login.json()["token"]
    leader.headers["X-Leader-Token"] = token

    me = leader.get("/api/access/leader/me").json()
    check("寝室长只看到自己的寝室", me["dorm"]["room_no"] == room_no, str(me))
    check("返回的寝室信息不含其他寝室", "items" not in me, str(me)[:150])

    print("\n== 6. 寝室长权限边界 ==")
    res = leader.post("/api/dorms", json={"room_no": "1-2"})
    check("寝室长不能新增寝室", res.status_code in (401, 403, 404), str(res.status_code))
    res = leader.post("/api/members/import/preview", files={"file": ("x.xlsx", b"x")})
    check("寝室长不能导入名单", res.status_code in (401, 403, 404), str(res.status_code))
    res = leader.get("/api/accounts")
    check("寝室长不能管理账号", res.status_code in (401, 403, 404), str(res.status_code))

    other = next((d for d in accounts if d["dorm_id"] != dorm_id), None)
    if other:
        admin.post("/api/access/leader/password", json={"dorm_id": other["dorm_id"], "action": "set", "password": "other8888"})
        res = leader.post("/api/reports/submit", json={
            "dorm_id": other["dorm_id"], "is_complete": True, "note": "越权填报", "submitter": "越权",
        })
        check("寝室长填不了别人设了密码的寝室", res.status_code == 403, f"状态 {res.status_code}")
        other_members = leader.get(f"/api/reports/dorm/{other['dorm_id']}").json()["members"]
        if other_members:
            res = leader.put(f"/api/members/{other_members[0]['id']}", json={
                "name": other_members[0]["name"], "student_no": "", "phone": "",
                "room_no": other["room_no"], "role": "成员", "active": True,
            })
            check("寝室长改不了别人寝室成员", res.status_code in (403, 404), str(res.status_code))
        admin.post("/api/access/leader/password", json={"dorm_id": other["dorm_id"], "action": "clear"})
    else:
        check("寝室长填不了别人设了密码的寝室", False, "只有一间寝室，无法交叉验证")
        check("寝室长改不了别人寝室成员", False, "只有一间寝室，无法交叉验证")

    print("\n== 7. 管理端口页面（前端资源） ==")
    for asset in ("/js/pages/console.js", "/js/pages/home.js", "/js/app.js", "/js/core.js", "/js/pages/login.js"):
        check(f"管理端口资源 {asset}", admin.get(asset).status_code == 200)

    admin.post("/api/access/leader/password", json={"dorm_id": dorm_id, "action": "clear"})
    check("测试用寝室密码已取消", all(
        item["has_password"] is False
        for item in admin.get("/api/access/leader/accounts").json()["items"]
        if item["dorm_id"] == dorm_id
    ))

    public.close()
    leader.close()
    admin.close()

    print("\n" + "=" * 56)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    for item in FAIL:
        print("  - " + item)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
