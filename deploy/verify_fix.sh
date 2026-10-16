#!/usr/bin/env bash
# 验证修复：配置页各检测接口不再 500
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
import httpx

c = httpx.Client(base_url="http://127.0.0.1:8091", timeout=120)
r = c.post("/api/auth/login", json={"username": "admin", "password": "344940"})
tok = r.json().get("token", "")
h = {"X-Session-Token": tok}
print(f"登录: {r.status_code} ok={r.json().get('ok')}")
print()
print("配置页各检测接口（修复前都是 500 UnboundLocalError）：")
for kind in ("qqbot", "smtp", "email", "notify", "onebot_group", "showdoc", "preview"):
    try:
        res = c.post("/api/settings/test", headers=h, json={"kind": kind})
        d = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
        mark = "✅" if res.status_code == 200 else "❌"
        msg = str(d.get("message"))[:52]
        print(f"  {mark} kind={kind:<14} HTTP {res.status_code}  {msg}")
    except Exception as exc:
        print(f"  ❌ kind={kind:<14} 异常 {type(exc).__name__}: {str(exc)[:60]}")

print()
print("长连接状态：")
s = c.get("/api/qqbot/status", headers=h, timeout=90).json()
for k in ("gateway_running", "enabled", "has_credentials", "known_groups", "message"):
    print(f"  {k:<18} = {s.get(k)}")
PY
