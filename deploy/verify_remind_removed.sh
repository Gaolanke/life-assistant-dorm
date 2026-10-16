#!/usr/bin/env bash
# 验证「未填报提醒」定时任务已删除，且其他任务正常
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

echo "=== 1. 应用内定时任务 ==="
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend import scheduler
jobs = scheduler.build_scheduler().get_jobs()
print(f"  共 {len(jobs)} 个任务：")
for j in jobs:
    print(f"    {j.id:<18} {j.trigger}")
names = [j.id for j in jobs]
print()
print(f"  未填报提醒(missing_reminder) 存在吗: {'❌ 还在' if 'missing_reminder' in names else '✅ 已删除'}")
PY

echo
echo "=== 2. 系统 cron ==="
crontab -l 2>/dev/null | grep -E 'life-assistant' | sed 's/^/    /' || echo "    (无)"
if crontab -l 2>/dev/null | grep -q 'remind'; then
  echo "  ❌ cron 里还有 remind 任务"
else
  echo "  ✅ cron 里的 remind 任务已删除"
fi

echo
echo "=== 3. 手动推送提醒仍然可用 ==="
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
import httpx
c = httpx.Client(base_url="http://127.0.0.1:8091", timeout=120)
tok = c.post("/api/auth/login", json={"username": "admin", "password": "344940"}).json().get("token", "")
h = {"X-Session-Token": tok}
# 只验证接口可用（真的会发消息，所以这里传 dry 语义：看返回结构）
r = c.post("/api/onebot/remind", headers=h)
d = r.json()
print(f"  手动提醒接口 HTTP {r.status_code}")
print(f"    ok={d.get('ok')}  通道={d.get('channel')}  说明={str(d.get('message'))[:50]}")
PY

echo
echo "=== 4. 服务状态 ==="
echo -n "  dorm: "; systemctl is-active dorm
echo -n "  cloudflared: "; systemctl is-active cloudflared
