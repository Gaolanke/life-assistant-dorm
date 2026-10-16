#!/usr/bin/env bash
# 最终线上验证
set -u
cd /www/dorm || exit 1

echo "############ 1. 服务状态 ############"
echo -n "  dorm:        "; systemctl is-active dorm
echo -n "  cloudflared: "; systemctl is-active cloudflared
echo -n "  nginx:       "; systemctl is-active nginx

echo
echo "############ 2. 生产数据 ############"
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from sqlalchemy import func, select
from backend.database import SessionLocal
from backend.models import Account, BotGroup, Dorm, FundEntry, Member, Report, Setting
db = SessionLocal()
for name, model in (("宿舍", Dorm), ("人员", Member), ("填报", Report),
                    ("班费明细", FundEntry), ("账号", Account), ("机器人群", BotGroup)):
    print(f"  {name:<8} {db.execute(select(func.count(model.id))).scalar()}")
f = db.execute(select(func.sum(FundEntry.amount))).scalar() or 0
print(f"  班费合计 {f:.2f} 元")
print()
print("  关键设置：")
for k in ("qqbot_enabled", "qqbot_groups", "qq_report_time", "report_deadline",
          "auto_export_time", "auto_backup", "auto_backup_time", "backup_keep"):
    row = db.execute(select(Setting).where(Setting.key == k)).scalar()
    print(f"    {k:<20} = {row.value if row else '(缺)'!r}")
db.close()
PY

echo
echo "############ 3. 定时任务 ############"
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend import scheduler
for job in scheduler.build_scheduler().get_jobs():
    print(f"  {job.id:<18} {job.trigger}")
PY

echo
echo "############ 4. 备份情况 ############"
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.services import backup_service
items = backup_service.list_backups()
print(f"  共 {len(items)} 份备份")
for it in items[:5]:
    print(f"    {it['created_at']}  {it['name']:<34} {it['size_text']}")
PY

echo
echo "############ 5. 公开端口功能自检 ############"
for p in /api/health /api/dorms /api/reports/today /api/reports/records /api/access/status; do
  code=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "http://127.0.0.1:8090$p")
  printf '  %-26s %s\n' "$p" "$code"
done

echo
echo "############ 6. 管理端口鉴权自检（未登录应 401） ############"
for p in /api/settings /api/logs/push /api/accounts /api/reports/export /api/dorms/members/export; do
  code=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "http://127.0.0.1:8091$p")
  flag=$([ "$code" = "401" ] && echo "✅" || echo "❌")
  printf '  %s %-28s %s\n' "$flag" "$p" "$code"
done

echo
echo "############ 7. 管理员登录后正常 + 密钥不外泄 ############"
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
import httpx
c = httpx.Client(base_url="http://127.0.0.1:8091", timeout=30)
r = c.post("/api/auth/login", json={"username": "admin", "password": "344940"})
print(f"  登录 HTTP {r.status_code} ok={r.json().get('ok')}")
h = {"X-Session-Token": r.json().get("token", "")}
for p in ("/api/settings", "/api/logs/push", "/api/qqbot/status", "/api/jobs", "/api/reports/records"):
    res = c.get(p, headers=h)
    mark = "✅" if res.status_code == 200 else "❌"
    print(f"  {mark} {p:<26} {res.status_code}")
pub = httpx.get("http://127.0.0.1:8090/api/settings", timeout=20).json()
vals = pub.get("values", {})
print()
print("  公开端能否看到密钥：")
for k in ("qqbot_secret", "smtp_password", "onebot_token"):
    print(f"    {k:<16} {'❌ 泄露了！' if k in vals else '✅ 不返回'}")
print(f"  公开端可见字段数：{len(vals)}")
print(f"  公开端字段：{', '.join(sorted(vals))}")
PY
