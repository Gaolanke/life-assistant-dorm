"""验证访问流程：公开端口选寝室填报 / 账号登录管理端 / 寝室长验证 / 密码锁。

用法： .venv\\Scripts\\python.exe scripts\\test_access.py [管理端口] [公开端口]

默认： 管理端口 http://127.0.0.1:8091 ，公开端口 http://127.0.0.1:8090
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

ADMIN = sys.argv[1] if len(sys.argv) > 1 else ADMIN_BASE
PUBLIC = sys.argv[2] if len(sys.argv) > 2 else PUBLIC_BASE
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8")

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(name if ok else f"{name} :: {detail}")
    print(f"  [{'OK' if ok else 'FAIL'}] {name}  {'' if ok else detail}")


def ensure_sample_dorms(admin: httpx.Client) -> list[int]:
    """自检需要带成员的寝室；不够就临时建两间（结束后会删掉）。"""
    dorms = admin.get("/api/dorms?with_members=false&active_only=true").json()
    if dorms["total"] >= 2:
        return []
    created: list[int] = []
    for room in ("8-801", "8-802"):
        res = admin.post(
            "/api/dorms",
            json={"room_no": room, "building": "8号楼", "leader_name": "自检同学"},
        )
        if res.status_code != 200:
            raise SystemExit(f"创建测试寝室失败：{res.text[:200]}")
        dorm_id = res.json()["item"]["id"]
        created.append(dorm_id)
        for index in range(2):
            admin.post(
                f"/api/dorms/{dorm_id}/members",
                json={"name": f"自检同学{index + 1}", "student_no": f"99{len(created)}{index}", "phone": "13800000000"},
            )
    print(f"  （自检临时创建了 {len(created)} 间寝室，结束后会删除）")
    return created


def main() -> int:
    print(f"数据目录：{server_env.DATA_DIR}")

    print("\n== 0. 准备：登录管理员 ==")
    admin = ensure_admin_client(base=ADMIN)
    check("管理员账号登录成功", bool(admin.headers.get("X-Session-Token")), "没有拿到会话令牌")

    temporary = ensure_sample_dorms(admin)

    public = public_client(PUBLIC)

    print("\n== 1. 普通访问：公开端口选寝室 -> 填报 ==")
    status = public.get("/api/access/status").json()
    check("未登录时不是管理员", status["is_admin"] is False, str(status))
    check("未登录时 logged_in=False", status.get("logged_in") is False, str(status))
    check("接口提示必须登录管理端", status.get("login_required") is True, str(status))
    check("公开端口模式是 public", public.get("/api/system/mode").json()["mode"] == "public")

    dorms = public.get("/api/dorms?with_members=false&active_only=true").json()
    check("入口页能拿到寝室列表", dorms["total"] >= 1, str(dorms["total"]))
    dorm = dorms["items"][0]
    check("寝室带人数与寝室长", "member_count" in dorm and "leader_name" in dorm)

    # 确保这间寝室没设密码，才能演示「任何人都能填」
    admin.post("/api/access/leader/password", json={"dorm_id": dorm["id"], "action": "clear"})

    detail = public.get(f"/api/reports/dorm/{dorm['id']}").json()
    check("选中寝室后能拿到成员", len(detail["members"]) >= 1, str(len(detail["members"])))
    submit = public.post("/api/reports/submit", json={
        "dorm_id": dorm["id"],
        "is_complete": True,
        "note": "普通填报测试",
        "submitter": "路过的同学",
        "checkins": [{"member_id": m["id"], "present": True} for m in detail["members"]],
    })
    check("普通访问可以直接填报", submit.status_code == 200 and submit.json()["ok"], submit.text[:200])

    print("\n== 2. 管理接口门禁（未登录 / 公开端口） ==")
    for path in ("/api/accounts", "/api/fund/summary", "/api/logs/audit", "/api/logs/submissions"):
        res = public.get(path)
        check(f"公开端口 {path} 返回 404", res.status_code == 404, str(res.status_code))

    with httpx.Client(base_url=ADMIN, timeout=30, follow_redirects=True) as anon:
        check("未登录访问 /api/accounts 是 401", anon.get("/api/accounts").status_code == 401, "应返回 401")
        check("未登录访问 /api/fund/summary 是 401", anon.get("/api/fund/summary").status_code == 401, "应返回 401")
        check("未登录访问 /api/logs/submissions 是 401", anon.get("/api/logs/submissions").status_code == 401, "应返回 401")
        check("未登录不能改配置", anon.put("/api/settings", json={"values": {"school_name": "黑客"}}).status_code == 401, "应返回 401")
        check("未登录不能新增寝室", anon.post("/api/dorms", json={"room_no": "9-999"}).status_code == 401, "应返回 401")
        check("未登录不能清空数据", anon.post("/api/system/reset-data", json={}).status_code == 401, "应返回 401")
    check("未登录也能读配置（填报页需要）", public.get("/api/settings").status_code == 200)

    print("\n== 3. 管理员账号登录 ==")
    code, _ = try_login(base=ADMIN, username="admin", password="000000")
    check("错误的密码被拒绝", code == 403, f"状态码 {code}")

    status2 = admin.get("/api/access/status").json()
    check("管理端口登录后 is_admin=True", status2["is_admin"] is True, str(status2))
    check("管理端口 current_port 正确", status2["current_port"] == status2["admin_port_number"], str(status2))

    accounts = admin.get("/api/accounts").json()
    check("管理员能看账号列表", accounts["ok"] and accounts["total"] >= 1, str(accounts)[:150])

    created = admin.post("/api/dorms", json={"room_no": "9-999", "building": "9号楼"})
    check("管理员能新增寝室", created.status_code == 200 and created.json()["ok"], created.text[:200])
    new_dorm_id = created.json()["item"]["id"] if created.status_code == 200 else 0

    console = admin.get("/api/access/leader/accounts").json()
    check("管理员能看寝室长账号状态", console["ok"] and console["total"] >= 1, str(console)[:150])

    print("\n== 4. 寝室长验证与密码锁 ==")
    all_dorms = [d for d in admin.get("/api/dorms?with_members=true&active_only=false").json()["items"] if d["members"]]
    if len(all_dorms) < 2:
        check("至少有两间带成员的寝室", False, "数据不足")
        return 1
    dorm_a, dorm_b = all_dorms[0], all_dorms[1]

    pw = admin.post("/api/access/leader/password", json={"dorm_id": dorm_a["id"], "action": "set", "password": "lock1234"})
    check("管理员可设置寝室密码", pw.status_code == 200 and pw.json()["password"] == "lock1234", pw.text[:200])
    room_no, password = dorm_a["room_no"], "lock1234"

    bad_login = public.post("/api/access/leader/login", json={"room_no": room_no, "password": "000000"})
    check("错误密码被拒绝", bad_login.status_code == 403, str(bad_login.status_code))

    login = public.post("/api/access/leader/login", json={"room_no": room_no, "password": password})
    check("寝室长验证成功", login.status_code == 200 and login.json()["ok"], login.text[:200])
    token = login.json()["token"]

    me = public.get("/api/access/leader/me", headers={"X-Leader-Token": token}).json()
    check("寝室长身份可查询", me["dorm"] and me["dorm"]["room_no"] == room_no, str(me))

    console2 = admin.get("/api/access/leader/accounts").json()
    check("控制台能列出寝室账号", len(console2["items"]) >= 1, str(len(console2["items"])))
    check("密码状态正确", any(item["has_password"] for item in console2["items"]))

    visitor = public_client(PUBLIC)
    detail_locked = visitor.get("/api/reports/dorm/" + str(dorm_a["id"])).json()
    check("设了密码的寝室对外显示为锁定", detail_locked["locked"] is True and detail_locked["can_write"] is False, str(detail_locked)[:160])
    blocked = visitor.post("/api/reports/submit", json={
        "dorm_id": dorm_a["id"], "is_complete": True, "note": "未验证", "submitter": "路人",
    })
    check("未验证不能填设了密码的寝室", blocked.status_code == 403, f"状态 {blocked.status_code} {blocked.text[:120]}")

    members = visitor.get(f"/api/reports/dorm/{dorm_a['id']}", headers={"X-Leader-Token": token}).json()["members"]
    check("验证后本人可以填报", visitor.post(
        "/api/reports/submit",
        headers={"X-Leader-Token": token},
        json={
            "dorm_id": dorm_a["id"], "is_complete": True, "note": "寝室长本人填报", "submitter": room_no,
            "checkins": [{"member_id": m["id"], "present": True} for m in members],
        },
    ).status_code == 200)

    # 另一间寝室也设密码，用它自己的寝室长令牌来填 dorm_a，必须被拒
    admin.post("/api/access/leader/password", json={"dorm_id": dorm_b["id"], "action": "set", "password": "other1234"})
    other_login = visitor.post("/api/access/leader/login", json={"room_no": dorm_b["room_no"], "password": "other1234"})
    other_token = other_login.json().get("token", "") if other_login.status_code == 200 else ""
    cross_detail = visitor.get("/api/reports/dorm/" + str(dorm_a["id"]), headers={"X-Leader-Token": other_token}).json()
    check("别人的寝室长看目标寝室 can_write=False", cross_detail["can_write"] is False, str(cross_detail)[:150])
    denied = visitor.post(
        "/api/reports/submit",
        headers={"X-Leader-Token": other_token},
        json={"dorm_id": dorm_a["id"], "is_complete": True, "note": "跨寝室越权", "submitter": "别的寝室长"},
    )
    check("设了密码的寝室，别的寝室长填不了", denied.status_code == 403, f"状态 {denied.status_code} {denied.text[:120]}")

    # 没设密码的寝室：任何人都能填
    admin.post("/api/access/leader/password", json={"dorm_id": dorm_b["id"], "action": "clear"})
    open_detail = visitor.get("/api/reports/dorm/" + str(dorm_b["id"])).json()
    check("没设密码的寝室对外可写", open_detail["locked"] is False and open_detail["can_write"] is True, str(open_detail)[:150])
    check("没设密码的寝室谁都能填", visitor.post("/api/reports/submit", json={
        "dorm_id": dorm_b["id"], "is_complete": True, "note": "无需密码", "submitter": "任何同学",
    }).status_code == 200)

    # 管理员（管理端口 + 已登录）不受密码限制
    res = admin.post("/api/reports/admin", json={
        "dorm_id": dorm_a["id"], "is_complete": True, "note": "管理员代填", "submitter": "生活委员",
    })
    check("管理员能代填设了密码的寝室", res.status_code == 200 and res.json()["ok"], res.text[:180])

    member_id = members[0]["id"]
    assign = admin.post(
        f"/api/access/leader/assign?dorm_id={dorm_a['id']}&member_id={member_id}",
    )
    check("管理员能指定寝室长", assign.status_code == 200 and assign.json()["ok"], assign.text[:200])

    print("\n== 5. 收尾 ==")
    admin.post("/api/access/leader/password", json={"dorm_id": dorm_a["id"], "action": "clear"})
    admin.post("/api/access/leader/password", json={"dorm_id": dorm_b["id"], "action": "clear"})
    check("测试用寝室密码已取消", all(
        item["has_password"] is False
        for item in admin.get("/api/access/leader/accounts").json()["items"]
        if item["dorm_id"] in (dorm_a["id"], dorm_b["id"])
    ))
    if new_dorm_id:
        admin.delete(f"/api/dorms/{new_dorm_id}?purge_reports=true")
    for row in admin.get("/api/dorms?with_members=false&active_only=false").json()["items"]:
        if temporary and row["room_no"].startswith("8-80"):
            admin.delete(f"/api/dorms/{row['id']}?purge_reports=true")
    check("临时数据已清理", all(not row["room_no"].startswith("8-80") for row in admin.get("/api/dorms").json()["items"]))

    admin.close()
    public.close()
    visitor.close()

    print(f"\n通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    for item in FAILED:
        print("  - " + item)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
