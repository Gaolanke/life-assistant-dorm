#!/usr/bin/env bash
# 用全新 client（无 cookie）验证删除接口的鉴权
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

.venv/bin/python - <<'PY'
import sys

sys.path.insert(0, '.')
import httpx

print("=== 用一个全新的、未登录的 client ===")
anon = httpx.Client(base_url="http://127.0.0.1:8091", timeout=20)
for method, url in (
    ("DELETE", "/api/qqbot/groups/2"),
    ("DELETE", "/api/qqbot/groups"),
    ("GET", "/api/qqbot/groups"),
):
    r = anon.request(method, url)
    mark = "✅ 已挡住" if r.status_code in (401, 403, 404) else "❌ 竟然放行"
    print(f"  未登录 {method:<7} {url:<26} -> HTTP {r.status_code} {mark}")

print()
print("=== 确认数据没被未登录请求删掉 ===")
c = httpx.Client(base_url="http://127.0.0.1:8091", timeout=20)
tok = c.post("/api/auth/login", json={"username": "admin", "password": "344940"}).json().get("token", "")
h = {"X-Session-Token": tok}
g = c.get("/api/qqbot/groups", headers=h).json()
print(f"  组记录 {g.get('total')} 条：")
for it in g.get("items", []):
    print(f"    id={it['id']}  {it['group_openid'][:24]}…  推送中={it.get('is_target')}")
print(f"  推送目标 = {g.get('configured_groups')!r}")
PY
