#!/usr/bin/env bash
# 确认调度器在跑、任务下次执行时间、以及历史上有没有重复发送
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

echo "=== 1. 调度器状态（通过接口读） ==="
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
import httpx
c = httpx.Client(base_url="http://127.0.0.1:8091", timeout=30)
tok = c.post("/api/auth/login", json={"username": "admin", "password": "344940"}).json().get("token", "")
h = {"X-Session-Token": tok}
r = c.get("/api/jobs/status", headers=h)
if r.status_code == 404:
    # 换个可能的路径
    r = c.get("/api/settings/jobs", headers=h)
print(f"  接口 HTTP {r.status_code}")
try:
    data = r.json()
    for j in (data.get("jobs") or data.get("items") or []):
        print(f"    {j.get('name') or j.get('id'):<28} 下次执行 {j.get('next_run')}")
except Exception as e:
    print(f"  解析失败: {e} {r.text[:200]}")
PY

echo
echo "=== 2. 历史上有没有「同一晚发两次汇报」 ==="
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from sqlalchemy import select
from backend.database import SessionLocal
from backend.models import PushLog

db = SessionLocal()
rows = db.execute(
    select(PushLog).where(PushLog.scene == "daily_report").order_by(PushLog.id.desc()).limit(12)
).scalars().all()
for r in rows:
    print(f"  {r.created_at}  trigger={r.trigger:<7} status={r.status:<8} {str(r.detail)[:30]}")
db.close()
PY

echo
echo "=== 3. 服务与 cron ==="
echo -n "  dorm: "; systemctl is-active dorm
echo "  cron:"
crontab -l 2>/dev/null | grep -E 'life-assistant' | sed 's/^/    /' || echo "    (无)"
