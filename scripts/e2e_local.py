"""本地端到端测试：模拟真实用户操作（走 HTTP 接口 + 页面资源检查）。

用法： .venv\\Scripts\\python.exe scripts\\e2e_local.py [公开端口] [管理端口]

默认： 公开端口 http://127.0.0.1:8090 ，管理端口 http://127.0.0.1:8091
"""
from __future__ import annotations

import io
import random
import sys
from pathlib import Path

import httpx
from openpyxl import Workbook

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

    print("\n== 场景 1：同学打开网站（公开端口，未登录） ==")
    phone = public_client(MAIN)
    page = phone.get("/")
    check("首页能打开", page.status_code == 200 and "生活助手" in page.text, str(page.status_code))
    for asset in ("/js/pages/home.js", "/js/pages/login.js", "/css/style.css", "/vendor/chart.umd.min.js"):
        res = phone.get(asset)
        check(f"页面资源可访问 {asset}", res.status_code == 200, str(res.status_code))

    access = phone.get("/api/access/status").json()
    check("未登录时不是管理员", access["is_admin"] is False, str(access))
    check("未登录时 logged_in=False", access.get("logged_in") is False, str(access))
    check("能看到寝室列表（入口页数据）", phone.get("/api/dorms?with_members=false&active_only=true").json()["total"] >= 1)

    dorms = phone.get("/api/dorms?with_members=false&active_only=true").json()["items"]
    if not dorms:
        print("  没有寝室数据，请先导入名单")
        return 2
    target = next((d for d in dorms if d["room_no"] == "6-213"), dorms[0])

    admin = ensure_admin_client(base=ADMIN)
    check("管理员账号登录成功", bool(admin.headers.get("X-Session-Token")))
    # 保证目标寝室没设密码，普通同学才填得进去
    admin.post("/api/access/leader/password", json={"dorm_id": target["id"], "action": "clear"})

    detail = phone.get(f"/api/reports/dorm/{target['id']}").json()
    check(f"选中 {target['room_no']} 后能拿到成员", len(detail["members"]) >= 1, str(len(detail["members"])))
    check("返回缺席原因候选项", len(detail["absence_reasons"]) >= 3, str(detail["absence_reasons"]))

    members = detail["members"]
    absent = members[0]
    submit = phone.post("/api/reports/submit", json={
        "dorm_id": target["id"],
        "is_complete": False,
        "absent_names": absent["name"],
        "note": f"{absent['name']}回家（家长已知晓）",
        "submitter": "6-213 同学",
        "checkins": [
            {"member_id": m["id"], "name": m["name"], "present": m["id"] != absent["id"],
             "reason": "回家" if m["id"] == absent["id"] else ""}
            for m in members
        ],
    })
    check("同学能直接提交填报", submit.status_code == 200 and submit.json()["ok"], submit.text[:200])
    report = submit.json()["report"]
    check("记录里有人数统计", report["absent_count"] == 1 and report["present_count"] == len(members) - 1, str(report))
    check("记录里保存了填表人", report["submitter"] == "6-213 同学", str(report.get("submitter")))

    print("\n== 场景 2：没登录进不了管理页面 ==")
    for path in ("/api/accounts", "/api/fund/summary", "/api/logs/audit"):
        res = phone.get(path)
        check(f"公开端口打不开 {path}", res.status_code == 404, str(res.status_code))
    res = phone.post("/api/dorms", json={"room_no": "7-777"})
    check("未登录不能新增寝室", res.status_code == 404, str(res.status_code))
    res = phone.put("/api/settings", json={"values": {"school_name": "改坏的"}})
    check("未登录不能改系统配置", res.status_code == 404, str(res.status_code))
    res = phone.post("/api/members/import/preview", files={"file": ("x.xlsx", b"x")})
    check("未登录不能导入名单", res.status_code == 404, str(res.status_code))
    with httpx.Client(base_url=ADMIN, timeout=40, follow_redirects=True) as anon:
        check("管理端口没令牌也是 401", anon.get("/api/accounts").status_code == 401, "应返回 401")

    print("\n== 场景 3：管理员登录管理端 ==")
    code, _ = try_login(base=ADMIN, username="admin", password="000000")
    check("错误密码被拒绝", code == 403, f"状态码 {code}")
    me = admin.get("/api/auth/me").json()
    check("登录后能查到自己的身份", me.get("logged_in") is True and (me.get("account") or {}).get("role") == "admin", str(me)[:160])
    after = admin.get("/api/access/status").json()
    check("管理端口登录后 is_admin=True", after["is_admin"] is True, str(after))
    check("管理端能看到账号列表", admin.get("/api/accounts").json()["total"] >= 1)

    print("\n== 场景 4：控制台给寝室生成寝室长密码 ==")
    accounts = admin.get("/api/access/leader/accounts").json()["items"]
    check("能列出所有寝室", len(accounts) >= 1, str(len(accounts)))
    # 优先挑「本来没设密码」的寝室，跑完取消密码就能恢复原状
    candidates = [item for item in accounts if not item["has_password"]] or accounts
    generated = []
    touched_dorms = []
    for dorm in candidates[:3]:
        res = admin.post("/api/access/leader/password", json={"dorm_id": dorm["dorm_id"], "action": "random"})
        check(f"{dorm['room_no']} 生成密码", res.status_code == 200 and len(res.json()["password"]) >= 4, res.text[:120])
        if res.status_code == 200:
            generated.append((dorm["room_no"], res.json()["password"], dorm["dorm_id"]))
            touched_dorms.append(dorm["dorm_id"])
    check("控制台显示已设密码", all(
        item["has_password"] for item in admin.get("/api/access/leader/accounts").json()["items"]
        if item["dorm_id"] in touched_dorms
    ))

    print("\n== 场景 5：寝室长验证并填报 ==")
    if not generated:
        check("寝室长验证成功", False, "场景 4 没有生成任何密码")
        return 1
    room_no, password, dorm_id = generated[0]
    leader_client = public_client(MAIN)
    bad = leader_client.post("/api/access/leader/login", json={"room_no": room_no, "password": "wrong"})
    check("寝室长密码错误被拒绝", bad.status_code == 403, str(bad.status_code))

    login_res = leader_client.post("/api/access/leader/login", json={"room_no": room_no, "password": password})
    check("寝室长验证成功", login_res.status_code == 200 and login_res.json()["ok"], login_res.text[:200])
    token = login_res.json()["token"]
    leader_client.headers["X-Leader-Token"] = token

    leader_me = leader_client.get("/api/access/leader/me").json()
    check("寝室长能查到自己的寝室", leader_me["dorm"]["room_no"] == room_no, str(leader_me))

    own = leader_client.get(f"/api/reports/dorm/{dorm_id}").json()["members"]
    res = leader_client.post("/api/reports/submit", json={
        "dorm_id": dorm_id, "is_complete": True, "note": "无",
        "submitter": leader_me["dorm"]["leader_name"] or room_no,
        "checkins": [{"member_id": m["id"], "present": True} for m in own],
    })
    check("寝室长能填报自己寝室", res.status_code == 200 and res.json()["ok"], res.text[:200])

    if own:
        res = leader_client.put(f"/api/members/{own[0]['id']}", json={
            "name": own[0]["name"], "student_no": own[0].get("student_no", ""),
            "phone": own[0].get("phone", ""), "room_no": room_no, "role": "成员", "active": True,
        })
        check("寝室长能改本寝室成员", res.status_code == 200, res.text[:200])

    other = next((d for d in dorms if d["id"] != dorm_id), None)
    if other:
        admin.post("/api/access/leader/password", json={"dorm_id": other["id"], "action": "set", "password": "otherRoom99"})
        other_members = leader_client.get(f"/api/reports/dorm/{other['id']}").json()["members"]
        if other_members:
            res = leader_client.put(f"/api/members/{other_members[0]['id']}", json={
                "name": other_members[0]["name"], "student_no": "", "phone": "",
                "room_no": other["room_no"], "role": "成员", "active": True,
            })
            check("寝室长改不了别人寝室", res.status_code == 403, str(res.status_code))
        touched_dorms.append(other["id"])

    print("\n== 场景 6：室友用入口页网址直接进填报 ==")
    link = public_client(MAIN)
    res = link.get(f"/?room={target['room_no']}&as=室友小王")
    check("带参数的入口网址能打开", res.status_code == 200, str(res.status_code))
    detail = link.get(f"/api/reports/dorm/{target['id']}").json()
    res = link.post("/api/reports/submit", json={
        "dorm_id": target["id"], "is_complete": True, "note": "都在", "submitter": "室友小王",
        "checkins": [{"member_id": m["id"], "present": True} for m in detail["members"]],
    })
    check("室友能提交填报", res.status_code == 200 and res.json()["ok"], res.text[:200])

    print("\n== 场景 7：管理员改配置与导出 ==")
    res = admin.put("/api/settings", json={"values": {"class_name": "物联网25-2", "qq_report_time": "22:40"}})
    check("管理员能改配置", res.status_code == 200 and res.json()["ok"], res.text[:200])
    preview = admin.get("/api/reports/preview").json()
    check("群汇报预览含班级名", "物联网25-2" in preview["group_report"], preview["group_report"][:120])
    export = admin.get("/api/reports/export")
    check("能导出 Excel", export.status_code == 200 and export.content[:2] == b"PK", str(export.status_code))
    jobs = admin.get("/api/jobs").json()["jobs"]
    check("定时任务在跑", any(j["id"] == "group_report" for j in jobs), str(jobs))

    print("\n== 场景 8：账号停用后令牌立刻失效 ==")
    tmp_user = f"e2etmp{random.randint(1000, 9999)}"
    created = admin.post("/api/accounts", json={
        "username": tmp_user, "password": "e2e123456", "display_name": "临时管理员", "role": "admin",
    })
    check("能新建临时管理员账号", created.status_code == 200 and created.json()["ok"], created.text[:160])
    tmp_id = created.json()["account"]["id"] if created.status_code == 200 else 0
    tmp_client = None
    if tmp_id:
        tmp_c, _tmp_token, _tmp_account = login(base=ADMIN, username=tmp_user, password="e2e123456")
        tmp_client = tmp_c
        check("临时账号的令牌可以访问管理接口", tmp_client.get("/api/accounts").status_code == 200)
        stopped = admin.patch(f"/api/accounts/{tmp_id}", json={"active": False})
        check("管理员能停用账号", stopped.status_code == 200 and stopped.json()["account"]["active"] is False, stopped.text[:160])
        check("停用后原令牌立刻失效", tmp_client.get("/api/accounts").status_code == 401, "停用后仍然能访问")
        check("停用后不能登录", try_login(base=ADMIN, username=tmp_user, password="e2e123456")[0] == 403, "停用后还能登录")
        deleted = admin.delete(f"/api/accounts/{tmp_id}")
        check("临时账号已清理", deleted.status_code == 200, deleted.text[:160])

    print("\n== 场景 9：Excel 导入（管理员） ==")
    wb = Workbook()
    ws = wb.active
    ws.append(["姓名", "学工号", "联系方式", "房屋名称", "备注（宿舍长）"])
    ws.append(["测试甲", "9001", "13900000001", "新区校区9号学生公寓901", "宿舍长"])
    ws.append(["测试乙", "9002", "13900000002", "新区校区9号学生公寓901", ""])
    buffer = io.BytesIO()
    wb.save(buffer)
    pv = admin.post("/api/members/import/preview", files={"file": ("t.xlsx", buffer.getvalue())})
    check("导入预览识别成功", pv.status_code == 200 and pv.json()["total_members"] == 2, pv.text[:200])
    cm = admin.post("/api/members/import/commit", json={"token": pv.json()["token"], "strategy": "merge", "update_member": True})
    check("导入提交成功", cm.status_code == 200 and cm.json()["created_members"] == 2, cm.text[:200])
    new_dorm = next((d for d in admin.get("/api/dorms?with_members=false").json()["items"] if d["room_no"] == "9-901"), None)
    check("新生成了 9-901 寝室", new_dorm is not None and new_dorm["leader_name"] == "测试甲", str(new_dorm))
    if new_dorm:
        admin.delete(f"/api/dorms/{new_dorm['id']}?purge_reports=true")

    print("\n== 收尾：取消测试中设置的寝室密码 ==")
    for dorm_id in touched_dorms:
        admin.post("/api/access/leader/password", json={"dorm_id": dorm_id, "action": "clear"})
    check("测试用寝室密码已取消", all(
        item["has_password"] is False
        for item in admin.get("/api/access/leader/accounts").json()["items"]
        if item["dorm_id"] in touched_dorms
    ))

    phone.close()
    link.close()
    leader_client.close()
    if tmp_client is not None:
        tmp_client.close()
    admin.close()

    print("\n" + "=" * 60)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    for item in FAIL:
        print("  - " + item)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
