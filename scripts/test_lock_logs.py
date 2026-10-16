"""验证：寝室长密码锁 + 填写日志（IP/设备）+ 账号登录后的日志权限。

用法： .venv\\Scripts\\python.exe scripts\\test_lock_logs.py [公开端口] [管理端口]
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

from auth_client import (  # noqa: E402
    ADMIN_BASE,
    PUBLIC_BASE,
    ensure_admin_client,
    public_client,
)

PUBLIC = sys.argv[1] if len(sys.argv) > 1 else PUBLIC_BASE
ADMIN = sys.argv[2] if len(sys.argv) > 2 else ADMIN_BASE
PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} :: {detail}")
    print(f"  [{'OK' if ok else 'FAIL'}] {name}{'' if ok else '  ' + detail}")


def main() -> int:
    print(f"数据目录：{server_env.DATA_DIR}")

    admin = ensure_admin_client(base=ADMIN)
    check("管理员账号登录成功", bool(admin.headers.get("X-Session-Token")), "没有拿到会话令牌")

    dorms = admin.get("/api/dorms?with_members=true&active_only=false").json()["items"]
    if len(dorms) < 3:
        print("  需要至少 3 间寝室，请先导入名单")
        return 2

    locked_dorm, open_dorm, other = dorms[0], dorms[1], dorms[2]
    # 给第一间设密码，第二间清掉密码
    admin.post("/api/access/leader/password", json={"dorm_id": locked_dorm["id"], "action": "set", "password": "lock8888"})
    admin.post("/api/access/leader/password", json={"dorm_id": open_dorm["id"], "action": "clear"})

    public = public_client(PUBLIC)

    print("\n== 1. 未设密码的寝室：任何人都能填 ==")
    detail = public.get(f"/api/reports/dorm/{open_dorm['id']}").json()
    check("查询返回未锁定", detail["locked"] is False and detail["can_write"] is True, str(detail)[:160])
    res = public.post("/api/reports/submit", json={
        "dorm_id": open_dorm["id"], "is_complete": True, "note": "无需密码",
        "submitter": "随便一个同学",
        "checkins": [{"member_id": m["id"], "present": True} for m in detail["members"]],
    })
    check("未设密码的寝室可以直接填报", res.status_code == 200 and res.json()["ok"], res.text[:180])

    print("\n== 2. 设了密码的寝室：必须寝室长账户 ==")
    detail2 = public.get(f"/api/reports/dorm/{locked_dorm['id']}").json()
    check("查询返回已锁定", detail2["locked"] is True and detail2["can_write"] is False, str(detail2)[:160])
    res = public.post("/api/reports/submit", json={
        "dorm_id": locked_dorm["id"], "is_complete": True, "note": "越权",
        "submitter": "没验证的人",
        "checkins": [{"member_id": m["id"], "present": True} for m in detail2["members"]],
    })
    check("未验证直接提交被拒绝", res.status_code == 403, f"状态 {res.status_code} {res.text[:150]}")
    check("提示里说明要用寝室长账户", "寝室长" in res.text, res.text[:180])

    res = public.put(f"/api/members/{detail2['members'][0]['id']}", json={
        "name": detail2["members"][0]["name"], "student_no": "", "phone": "",
        "room_no": locked_dorm["room_no"], "role": "成员", "active": True,
    })
    check("未验证不能改该寝室成员", res.status_code in (403, 404), f"状态 {res.status_code}")

    admin.post("/api/access/leader/password", json={"dorm_id": other["id"], "action": "set", "password": "other9999"})
    login_other = public.post("/api/access/leader/login", json={"room_no": other["room_no"], "password": "other9999"})
    if login_other.status_code == 200:
        other_token = login_other.json()["token"]
        res = public.post(
            "/api/reports/submit",
            headers={"X-Leader-Token": other_token},
            json={"dorm_id": locked_dorm["id"], "is_complete": True, "note": "跨寝室越权", "submitter": "别的寝室长"},
        )
        check("别的寝室长也填不了（跨寝室被拒）", res.status_code == 403, f"状态 {res.status_code}")
    else:
        check("别的寝室长也填不了（跨寝室被拒）", False, f"别的寝室长登录失败：{login_other.status_code}")

    print("\n== 3. 本寝室长验证后可以填 ==")
    login = public.post("/api/access/leader/login", json={"room_no": locked_dorm["room_no"], "password": "lock8888"})
    check("寝室长验证成功", login.status_code == 200 and login.json()["ok"], login.text[:160])
    token = login.json()["token"]
    detail3 = public.get(f"/api/reports/dorm/{locked_dorm['id']}", headers={"X-Leader-Token": token}).json()
    check("验证后 can_write = True", detail3["can_write"] is True, str(detail3)[:150])
    res = public.post(
        "/api/reports/submit",
        headers={"X-Leader-Token": token},
        json={
            "dorm_id": locked_dorm["id"], "is_complete": True, "note": "寝室长本人填报",
            "submitter": locked_dorm["leader_name"] or locked_dorm["room_no"],
            "checkins": [{"member_id": m["id"], "present": True} for m in detail3["members"]],
        },
    )
    check("寝室长验证后能填报", res.status_code == 200 and res.json()["ok"], res.text[:180])

    print("\n== 4. 管理端口不受密码限制，能看到全部 ==")
    res = admin.post("/api/reports/admin", json={
        "dorm_id": locked_dorm["id"], "is_complete": True, "note": "管理员代填", "submitter": "生活委员",
    })
    check("管理员能代填设了密码的寝室", res.status_code == 200 and res.json()["ok"], res.text[:180])
    mode = public.get("/api/system/mode").json()
    check("公开端口仍是 public", mode["mode"] == "public", str(mode))

    print("\n== 5. 填写日志（IP + 设备） ==")
    logs = admin.get("/api/logs/submissions?limit=50")
    check("填报日志接口可用", logs.status_code == 200, str(logs.status_code))
    payload = logs.json()
    items = payload["items"]
    check("有填报日志", len(items) >= 1, str(len(items)))
    with_source = [row for row in items if row["ip"] or row["device"]]
    check("有记录到来源信息的新数据", len(with_source) >= 1, payload.get("note", ""))
    if with_source:
        first = with_source[0]
        check("日志含填表人", bool(first["submitter"]), str(first)[:150])
        check("日志含来源 IP", bool(first["ip"]), str(first)[:150])
        check("日志含填写设备", bool(first["device"]), str(first)[:150])
    else:
        check("日志含填表人", False, "没有带来源信息的日志")
        check("日志含来源 IP", False, "没有带来源信息的日志")
        check("日志含填写设备", False, "没有带来源信息的日志")
    audit = admin.get("/api/logs/audit?limit=50").json()["items"]
    check("操作日志含 IP", any(row["ip"] for row in audit), "没有 IP")
    check("操作日志含设备", any(row["device"] for row in audit), "没有设备")
    check("操作日志含提交填报记录", any(row["action"] == "提交填报" for row in audit), "没有提交记录")
    check("操作日志含登录记录", any(row["action"] == "登录" for row in audit), "没有登录记录")
    check("老地址 /api/audit 仍兼容", admin.get("/api/audit?limit=20").status_code == 200)

    print("\n== 6. 未登录拿不到日志接口 ==")
    check("公开端口 /api/logs/submissions 被隔离", public.get("/api/logs/submissions").status_code == 404)
    check("公开端口 /api/logs/audit 被隔离", public.get("/api/logs/audit").status_code == 404)
    with httpx.Client(base_url=ADMIN, timeout=40, follow_redirects=True) as anon:
        check("管理端口未登录看不了填写日志", anon.get("/api/logs/submissions").status_code == 401, "应返回 401")
        check("管理端口未登录看不了操作日志", anon.get("/api/logs/audit").status_code == 401, "应返回 401")

    print("\n== 7. 收尾：恢复密码状态 ==")
    for dorm in (locked_dorm, open_dorm, other):
        admin.post("/api/access/leader/password", json={"dorm_id": dorm["id"], "action": "clear"})
    check("测试用密码已全部取消", all(
        item["has_password"] is False
        for item in admin.get("/api/access/leader/accounts").json()["items"]
        if item["dorm_id"] in (locked_dorm["id"], open_dorm["id"], other["id"])
    ))

    admin.close()
    public.close()

    print("\n" + "=" * 56)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    for item in FAIL:
        print("  - " + item)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
