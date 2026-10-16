#!/usr/bin/env bash
# 确认调度器在运行，并读出各任务下次执行时间
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
import httpx

c = httpx.Client(base_url="http://127.0.0.1:8091", timeout=30)
tok = c.post("/api/auth/login", json={"username": "admin", "password": "344940"}).json().get("token", "")
h = {"X-Session-Token": tok}

r = c.get("/api/jobs", headers=h)
print(f"  /api/jobs HTTP {r.status_code}")
data = r.json()
print(f"  服务器时间：{data.get('server_time')}")
print(f"  调度器任务 {len(data.get('jobs') or [])} 个：")
for j in data.get("jobs") or []:
    print(f"    {j.get('name'):<30} 下次执行 {j.get('next_run')}")
PY
