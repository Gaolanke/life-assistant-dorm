"""账号管理端到端测试（登录 / 新增 / 改密 / 停用 / 删除 / 批量建寝室长账号）。

覆盖：
  未登录 401、公开端口 404、管理员登录、新增管理员账号、重复用户名被拒、
  参数校验、改自己密码、管理员重置他人密码、停用后不能登录、删除账号、
  批量建寝室长账号、宿舍号+密码登录仍可用。

用法： .venv\\Scripts\\python.exe scripts\\test_accounts.py [管理端口] [公开端口]
"""
from __future__ import annotations

import random
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
    login,
    public_client,
    try_login,
)

ADMIN = sys.argv[1] if len(sys.argv) > 1 else ADMIN_BASE
PUBLIC = sys.argv[2] if len(sys.argv) > 2 else PUBLIC_BASE

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} :: {detail}")
    print(f"  [{'OK' if ok else 'FAIL'}] {name}{'' if ok else '  ' + detail}")


def account_by_username(client: httpx.Client, username: str) -> dict | None:
    payload = client.get("/api/accounts", params={"keyword": username}).json()
    return next((item for item in payload.get("items", []) if item["username"] == username), None)


def main() -> int:
    print(f"数据目录：{server_env.DATA_DIR}")

    suffix = random.randint(1000, 9999)
    tmp_user = f"acct{suffix}"
    tmp_password = "acct123456"
    tmp_id = 0
    tmp_client = None

    admin = ensure_admin_client(base=ADMIN)
    public = public_client(PUBLIC)

    print("\n== 1. 登录与权限 ==")
    check("管理员登录成功", bool(admin.headers.get("X-Session-Token")), "没有拿到会话令牌")
    me = admin.get("/api/auth/me").json()
    check("登录身份是管理员", (me.get("account") or {}).get("role") == "admin", str(me)[:160])
    with httpx.Client(base_url=ADMIN, timeout=40, follow_redirects=True) as anon:
        check("未登录看不了账号列表", anon.get("/api/accounts").status_code == 401, "应返回 401")
        check("未登录建不了账号", anon.post("/api/accounts", json={"username": "hacker"}).status_code == 401, "应返回 401")
        check("未登录看不了账号统计", anon.get("/api/accounts/stats").status_code == 401, "应返回 401")
    check("公开端口没有账号接口", public.get("/api/accounts").status_code == 404, "公开端口不应该有 /api/accounts")
    check("公开端口建账号返回 404", public.post("/api/accounts", json={"username": "hacker"}).status_code == 404, "公开端口不应该能建账号")

    accounts = admin.get("/api/accounts").json()
    check("账号列表可用", accounts["ok"] and accounts["total"] >= 1, str(accounts)[:150])
    check("列表里带 admin 且标出超级管理员", any(item["username"] == "admin" and item["is_owner"] for item in accounts["items"]), str(accounts["items"])[:150])
    stats = admin.get("/api/accounts/stats").json()
    check("账号统计字段齐全", {"total", "admins", "leaders", "active", "dorm_total"} <= set(stats), str(stats)[:200])
    roles = admin.get("/api/accounts?role=admin").json()
    check("按角色过滤可用", roles["total"] == roles["admin_count"] and roles["total"] >= 1, str(roles)[:150])

    print("\n== 2. 新增管理员账号 ==")
    created = admin.post("/api/accounts", json={
        "username": tmp_user, "password": tmp_password, "display_name": "测试管理员", "role": "admin",
    })
    check("新增管理员账号成功", created.status_code == 200 and created.json()["ok"], created.text[:200])
    if created.status_code == 200:
        tmp_id = created.json()["account"]["id"]
        check("返回初始密码就是设置的密码", created.json()["password"] == tmp_password and created.json()["generated"] is False, created.text[:200])
        check("新账号角色是管理员", created.json()["account"]["role"] == "admin", created.text[:160])

    code, data = try_login(base=ADMIN, username=tmp_user, password=tmp_password)
    check("新账号可以登录", code == 200, f"状态码 {code} {str(data)[:120]}")

    dup = admin.post("/api/accounts", json={"username": tmp_user, "password": "other123456", "role": "admin"})
    check("重复用户名被拒绝", dup.status_code == 400, f"状态码 {dup.status_code}")

    short_name = admin.post("/api/accounts", json={"username": "ab", "password": "abc123456", "role": "admin"})
    check("太短的用户名被拒绝", short_name.status_code == 400, f"状态码 {short_name.status_code}")

    weak = admin.post("/api/accounts", json={"username": f"{tmp_user}b", "password": "123", "role": "admin"})
    check("太短的密码被拒绝", weak.status_code == 400, f"状态码 {weak.status_code}")

    no_dorm = admin.post("/api/accounts", json={"username": f"{tmp_user}c", "password": "abc123456", "role": "leader"})
    check("寝室长账号必须绑定寝室", no_dorm.status_code == 400, f"状态码 {no_dorm.status_code}")

    auto = admin.post("/api/accounts", json={"username": f"{tmp_user}d", "display_name": "随机密码", "role": "admin"})
    check("不填密码会随机生成", auto.status_code == 200 and len(auto.json()["password"]) == 6 and auto.json()["generated"] is True, auto.text[:200])
    if auto.status_code == 200:
        auto_id = auto.json()["account"]["id"]
        auto_password = auto.json()["password"]
        check("随机密码可以登录", try_login(base=ADMIN, username=f"{tmp_user}d", password=auto_password)[0] == 200, "随机密码登录失败")
        admin.delete(f"/api/accounts/{auto_id}")

    print("\n== 3. 改自己的密码 ==")
    tmp_client, _token, _account = login(base=ADMIN, username=tmp_user, password=tmp_password)
    wrong = tmp_client.post("/api/auth/password", json={"old_password": "nope-nope", "new_password": "acct654321"})
    check("原密码错误被拒绝", wrong.status_code == 403, str(wrong.status_code))
    short = tmp_client.post("/api/auth/password", json={"old_password": tmp_password, "new_password": "123"})
    check("新密码太短被拒绝", short.status_code == 400, str(short.status_code))
    changed = tmp_client.post("/api/auth/password", json={"old_password": tmp_password, "new_password": "acct654321"})
    check("改密码成功", changed.status_code == 200 and changed.json()["ok"], changed.text[:200])
    check("旧密码不能登录了", try_login(base=ADMIN, username=tmp_user, password=tmp_password)[0] == 403, "旧密码竟然还能用")
    check("新密码可以登录", try_login(base=ADMIN, username=tmp_user, password="acct654321")[0] == 200, "新密码登录失败")
    check("改完密码当前令牌还有效", tmp_client.get("/api/auth/me").json().get("logged_in") is True, "令牌失效了")

    print("\n== 4. 管理员重置他人密码 ==")
    reset = admin.post(f"/api/accounts/{tmp_id}/password", json={"new_password": "reset654321"})
    check("管理员指定新密码成功", reset.status_code == 200 and reset.json()["password"] == "reset654321", reset.text[:200])
    check("重置后新密码可登录", try_login(base=ADMIN, username=tmp_user, password="reset654321")[0] == 200, "重置后的密码登录失败")
    check("重置后旧密码失效", try_login(base=ADMIN, username=tmp_user, password="acct654321")[0] == 403, "旧密码还能用")

    random_reset = admin.post(f"/api/accounts/{tmp_id}/password", json={})
    check("留空则随机生成 6 位", random_reset.status_code == 200 and len(random_reset.json()["password"]) == 6, random_reset.text[:200])
    random_password = random_reset.json()["password"]
    check("随机密码可登录", try_login(base=ADMIN, username=tmp_user, password=random_password)[0] == 200, "随机密码登录失败")

    missing_reset = admin.post("/api/accounts/99999999/password", json={"new_password": "whatever1"})
    check("重置不存在的账号返回 404", missing_reset.status_code == 404, str(missing_reset.status_code))

    print("\n== 5. 停用 / 启用 ==")
    tmp_client.close()
    tmp_client, _token, _account = login(base=ADMIN, username=tmp_user, password=random_password)
    stopped = admin.patch(f"/api/accounts/{tmp_id}", json={"active": False})
    check("停用账号成功", stopped.status_code == 200 and stopped.json()["account"]["active"] is False, stopped.text[:180])
    check("停用后不能登录", try_login(base=ADMIN, username=tmp_user, password=random_password)[0] == 403, "停用后还能登录")
    check("停用后原令牌立刻失效", tmp_client.get("/api/accounts").status_code == 401, "停用后令牌还能用")
    back = admin.patch(f"/api/accounts/{tmp_id}", json={"active": True})
    check("重新启用成功", back.status_code == 200 and back.json()["account"]["active"] is True, back.text[:180])
    check("启用后又能登录", try_login(base=ADMIN, username=tmp_user, password=random_password)[0] == 200, "启用后登录失败")

    renamed = admin.patch(f"/api/accounts/{tmp_id}", json={"display_name": "改名后的管理员", "note": "自动化测试"})
    check("修改账号资料成功", renamed.status_code == 200 and renamed.json()["account"]["display_name"] == "改名后的管理员", renamed.text[:180])

    print("\n== 6. 删除账号与自我保护 ==")
    check("不能删除自己", admin.delete(f"/api/accounts/{admin.get('/api/auth/me').json()['account']['id']}").status_code == 400, "竟然删掉了自己")
    check("不能停用自己", admin.patch(f"/api/accounts/{admin.get('/api/auth/me').json()['account']['id']}", json={"active": False}).status_code == 400, "竟然停用了自己")
    owner = next(item for item in admin.get("/api/accounts").json()["items"] if item["is_owner"])
    check("超级管理员不能被删除", admin.delete(f"/api/accounts/{owner['id']}").status_code == 400, "竟然删掉了超级管理员")
    check("超级管理员不能被停用", admin.patch(f"/api/accounts/{owner['id']}", json={"active": False}).status_code == 400, "竟然停用了超级管理员")

    deleted = admin.delete(f"/api/accounts/{tmp_id}")
    check("删除账号成功", deleted.status_code == 200 and deleted.json()["ok"], deleted.text[:200])
    check("删除后不能登录", try_login(base=ADMIN, username=tmp_user, password=random_password)[0] == 403, "删除后还能登录")
    check("删除后列表里查不到", account_by_username(admin, tmp_user) is None, "列表里还在")
    check("重复删除返回 404", admin.delete(f"/api/accounts/{tmp_id}").status_code == 404, "重复删除不是 404")
    if tmp_client is not None:
        tmp_client.close()

    print("\n== 7. 批量建寝室长账号 + 宿舍号密码登录 ==")
    dorms = admin.get("/api/dorms?with_members=false&active_only=false").json()["items"]
    if len(dorms) < 2:
        print("  寝室数据不足，请先导入名单")
        return 2
    before_leaders = admin.get("/api/accounts?role=leader").json()["total"]

    batch = admin.post("/api/accounts/batch-leader", params={"only_missing": "true"})
    check("批量建账号接口可用", batch.status_code == 200 and batch.json()["ok"], batch.text[:200])
    items = batch.json().get("items") or []
    check("给所有缺账号的寝室都建了账号", len(items) >= len(dorms) - before_leaders, f"items={len(items)} dorms={len(dorms)}")
    check("账号名就是宿舍号", all(item["username"] == item["room_no"] for item in items), str(items[:2]))
    check("每个账号都有初始密码", all(item["password"] for item in items), str(items[:2]))

    after_leaders = admin.get("/api/accounts?role=leader").json()["total"]
    check("寝室长账号数量增加了", after_leaders >= before_leaders + len(items), f"{before_leaders} -> {after_leaders}")

    console = admin.get("/api/access/leader/accounts").json()
    check("控制台显示每间寝室都有账号", console["with_account"] >= len(dorms), str(console)[:150])
    check("控制台显示寝室都已设密码", console["with_password"] >= len(dorms), str(console)[:150])

    sample = items[0]
    leader_login = public.post("/api/access/leader/login", json={"room_no": sample["room_no"], "password": sample["password"]})
    check("宿舍号 + 密码仍能登录寝室长界面", leader_login.status_code == 200 and leader_login.json()["ok"], leader_login.text[:200])
    check("登录返回了寝室长令牌", bool(leader_login.json().get("token")), leader_login.text[:200])

    account_login = try_login(base=PUBLIC, username=sample["room_no"], password=sample["password"])
    check("寝室长也能用账号密码登录", account_login[0] == 200, f"状态码 {account_login[0]}")
    check("登录身份是寝室长", (account_login[1].get("account") or {}).get("role") == "leader", str(account_login[1])[:200])
    check("密码不对时登录失败", try_login(base=PUBLIC, username=sample["room_no"], password="wrong-password")[0] == 403, "错误密码竟然通过了")

    again = admin.post("/api/accounts/batch-leader", params={"only_missing": "true"})
    check("再跑一次不会重复建账号", len(again.json().get("items") or []) == 0, again.text[:200])

    print("\n== 8. 收尾：删掉批量创建的寝室长账号 ==")
    for item in items:
        row = account_by_username(admin, item["username"])
        if row:
            admin.delete(f"/api/accounts/{row['id']}")
    check("批量创建的账号已删除", all(account_by_username(admin, item["username"]) is None for item in items), "还有账号残留")
    check("取消账号后寝室密码也清了", all(
        row["has_password"] is False
        for row in admin.get("/api/access/leader/accounts").json()["items"]
        if row["room_no"] in {item["room_no"] for item in items}
    ), "寝室密码没有跟着清掉")
    check("账号数量回到测试前", admin.get("/api/accounts?role=leader").json()["total"] == before_leaders, "数量没恢复")

    admin.close()
    public.close()

    print("\n" + "=" * 60)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    for item in FAIL:
        print("  - " + item)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
