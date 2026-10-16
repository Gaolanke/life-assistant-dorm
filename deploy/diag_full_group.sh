#!/usr/bin/env bash
# 全面诊断：长连接 / 群采集 / 配置 / 发送 / 网络
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

echo "########## 1. 长连接与配置 ##########"
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
import httpx
c = httpx.Client(base_url="http://127.0.0.1:8091", timeout=90)
r = c.post("/api/auth/login", json={"username": "admin", "password": "344940"})
h = {"X-Session-Token": r.json().get("token", "")}
s = c.get("/api/qqbot/status", headers=h).json()
for k in ("ok", "enabled", "ws_enabled", "gateway_running", "has_credentials",
          "app_id", "known_groups", "configured_groups", "message"):
    print(f"  {k:<18} = {s.get(k)}")
g = c.get("/api/qqbot/groups", headers=h).json()
print()
print(f"  已上报的群 {len(g.get('items', []))} 个：")
for it in g.get("items", []):
    print(f"    openid = {it.get('group_openid')}")
    print(f"      最近消息 = {str(it.get('last_message'))[:45]!r}")
    print(f"      时间 = {it.get('last_seen')}  次数 = {it.get('message_count')}")
PY

echo
echo "########## 2. 推送目标配置 ##########"
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from sqlalchemy import select
from backend.database import SessionLocal
from backend.models import Setting
db = SessionLocal()
for k in ("qqbot_groups", "qqbot_enabled", "qqbot_fallback_email", "smtp_enabled"):
    row = db.execute(select(Setting).where(Setting.key == k)).scalar()
    print(f"  {k:<22} = {row.value!r}" if row else f"  {k:<22} = (缺)")
db.close()
PY

echo
echo "########## 3. 网关日志（最近 15 条） ##########"
grep -iE 'qqbot.gateway' /www/dorm-data/logs/service.log | tail -15

echo
echo "########## 4. 群消息事件日志（有没有收到新群消息） ##########"
grep -iE '记录 QQ 群|群消息|GROUP_AT|已从 WebSocket' /www/dorm-data/logs/service.log | tail -10 || echo "  （没有收到任何群消息事件）"

echo
echo "########## 5. 推送日志 ##########"
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import notify_service
db = SessionLocal()
rows = notify_service.recent_logs(db, 8)
print(f"  最近 {len(rows)} 条：")
for r in rows:
    print(f"    {r.get('created_at')} [{r.get('channel_text')}] {r.get('scene_text')} -> {r.get('status_text')}")
    print(f"       目标={str(r.get('target'))[:46]}")
    print(f"       详情={str(r.get('detail'))[:80]}")
db.close()
PY

echo
echo "########## 6. 网络（腾讯接口） ##########"
for i in 1 2 3 4 5; do
  if timeout 6 bash -c "cat < /dev/null > /dev/tcp/api.sgroup.qq.com/443" 2>/dev/null; then
    printf '  TCP %s: ✅\n' "$i"
  else
    printf '  TCP %s: ❌\n' "$i"
  fi
done

echo
echo "########## 7. 服务状态 ##########"
echo -n "  dorm: "; systemctl is-active dorm
echo -n "  cloudflared: "; systemctl is-active cloudflared
