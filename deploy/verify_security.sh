#!/usr/bin/env bash
# 安全加固后的穿透验证：模拟"知道 admin 域名但没登录"的攻击者
set -u
cd /www/dorm || exit 1

PUB="http://127.0.0.1:8090"
ADM="http://127.0.0.1:8091"

probe() {
  url="$1"; expect="$2"; label="$3"
  code=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "$url")
  if [ "$code" = "$expect" ]; then
    printf '  ✅ %-46s %s\n' "$label" "$code"
  else
    printf '  ❌ %-46s %s（期望 %s）\n' "$label" "$code" "$expect"
  fi
}

echo "############ A. 管理端口：未登录直接调接口（应该全部 401） ############"
probe "$ADM/api/settings" "401" "GET  /api/settings（含密钥）"
probe "$ADM/api/logs/push" "401" "GET  /api/logs/push"
probe "$ADM/api/accounts" "401" "GET  /api/accounts"
probe "$ADM/api/fund/entries" "401" "GET  /api/fund/entries"
probe "$ADM/api/reports/records" "401" "GET  /api/reports/records"
probe "$ADM/api/reports/export" "401" "GET  /api/reports/export（导出全表）"
probe "$ADM/api/reports/export-files" "401" "GET  /api/reports/export-files"
probe "$ADM/api/dorms/members/export" "401" "GET  /api/dorms/members/export"
probe "$ADM/api/qqbot/status" "401" "GET  /api/qqbot/status"
probe "$ADM/api/qqbot/groups" "401" "GET  /api/qqbot/groups"
probe "$ADM/api/jobs" "401" "GET  /api/jobs"
probe "$ADM/api/onebot/status" "401" "GET  /api/onebot/status"
probe "$ADM/api/audit" "401" "GET  /api/audit"
echo "  --- 写操作 ---"
probe "$ADM/api/dorms" "401" "GET  /api/dorms"
probe "$ADM/api/system/info" "200" "GET  /api/system/info（登录页要用，放行）"
probe "$ADM/api/system/mode" "200" "GET  /api/system/mode（放行）"
probe "$ADM/api/auth/me" "200" "GET  /api/auth/me（放行）"

echo
echo "############ B. 危险写操作（未登录，应该 401，不能得手） ############"
code=$(curl -s -o /dev/null -m 10 -w '%{http_code}' -X DELETE "$ADM/api/reports/1")
printf '  %s DELETE /api/reports/1 -> %s\n' "$([ "$code" = "401" ] && echo ✅ || echo ❌)" "$code"
code=$(curl -s -o /dev/null -m 10 -w '%{http_code}' -X POST "$ADM/api/reports/export-now")
printf '  %s POST   /api/reports/export-now -> %s\n' "$([ "$code" = "401" ] && echo ✅ || echo ❌)" "$code"
code=$(curl -s -o /dev/null -m 10 -w '%{http_code}' -X POST "$ADM/api/system/reset-data" -H 'Content-Type: application/json' -d '{"confirm":"清空"}')
printf '  %s POST   /api/system/reset-data -> %s\n' "$([ "$code" = "401" ] && echo ✅ || echo ❌)" "$code"
code=$(curl -s -o /dev/null -m 10 -w '%{http_code}' -X PUT "$ADM/api/settings" -H 'Content-Type: application/json' -d '{"values":{"school_name":"hacked"}}')
printf '  %s PUT    /api/settings -> %s\n' "$([ "$code" = "401" ] && echo ✅ || echo ❌)" "$code"

echo
echo "############ C. 公开端口：不该出现的接口（应该 404） ############"
probe "$PUB/api/logs" "404" "GET  /api/logs"
probe "$PUB/api/accounts" "404" "GET  /api/accounts"
probe "$PUB/api/settings" "401" "GET  /api/settings（需管理员）"
probe "$PUB/api/reports/export" "401" "GET  /api/reports/export（需管理员）"
probe "$PUB/api/dorms/members/export" "401" "GET  /api/dorms/members/export（需管理员）"

echo
echo "############ D. 公开端口：正常功能不受影响（应该 200） ############"
probe "$PUB/api/health" "200" "GET  /api/health"
probe "$PUB/api/dorms" "200" "GET  /api/dorms（选寝室）"
probe "$PUB/api/reports/today" "200" "GET  /api/reports/today"
probe "$PUB/api/reports/records" "200" "GET  /api/reports/records（公开看板）"
probe "$PUB/api/reports/stats" "200" "GET  /api/reports/stats"
probe "$PUB/api/access/status" "200" "GET  /api/access/status"
probe "$PUB/api/system/mode" "200" "GET  /api/system/mode"

echo
echo "############ E. 管理员登录后一切正常（应该 200） ############"
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
import httpx
c = httpx.Client(base_url="http://127.0.0.1:8091", timeout=30)
r = c.post("/api/auth/login", json={"username": "admin", "password": "344940"})
print(f"  登录 -> HTTP {r.status_code} ok={r.json().get('ok')}")
tok = r.json().get("token", "")
h = {"X-Session-Token": tok}
for path in ("/api/settings", "/api/logs/push", "/api/accounts", "/api/fund/summary",
             "/api/qqbot/status", "/api/jobs", "/api/reports/records", "/api/reports/export-files",
             "/api/audit", "/api/onebot/status"):
    res = c.get(path, headers=h)
    mark = "✅" if res.status_code == 200 else "❌"
    print(f"  {mark} {path:<32} {res.status_code}")
PY

echo
echo "############ F. 服务与定时任务 ############"
echo -n "  dorm: "; systemctl is-active dorm
echo -n "  cloudflared: "; systemctl is-active cloudflared
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend import scheduler
from backend.services import settings_service as ss
db = SessionLocal()
print("  时间设置：")
for k in ("qq_report_time", "showdoc_remind_time", "auto_export_time", "auto_backup_time", "backup_keep"):
    print(f"    {k:<20} = {ss.get_setting(db, k)!r}")
db.close()
sched = scheduler.build_scheduler()
print("  已注册定时任务：")
for job in sched.get_jobs():
    print(f"    {job.id:<18} {getattr(job, 'trigger', '')}")
PY
