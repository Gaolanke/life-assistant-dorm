#!/usr/bin/env bash
# 验证 QQ 官方机器人回调链路（公网可达 + 签名校验 + 群记录）
set -u
cd /www/dorm || exit 1

echo "=== 1. 表结构 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import init_db, SessionLocal
from backend.services import settings_service as ss
init_db()
db = SessionLocal()
ss.ensure_settings(db)
import sqlite3
from backend import config
con = sqlite3.connect(str(config.DB_PATH))
tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
print("  bot_groups 表:", "已创建" if 'bot_groups' in tables else "缺失！")
con.close()
print("  qqbot_public_key 配置:", "有" if ss.get_setting(db, 'qqbot_public_key') is not None else "缺失")
print("  qqbot_app_id =", ss.get_setting(db, 'qqbot_app_id'))
db.close()
PY

echo
echo "=== 2. 公网回调地址可达性（会真的发一个校验请求） ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import json
import sys
sys.path.insert(0, '.')
import httpx
from backend.database import SessionLocal
from backend.services import settings_service as ss
from backend.routers.qqbot import _ed25519_sign, _ed25519_verify

db = SessionLocal()
secret = ss.get_setting(db, 'qqbot_secret').strip()
db.close()

url = 'http://111.228.38.170:8090/api/qqbot/events'
payload = {"op": 13, "d": {"plain_token": "ServerCheckToken123", "event_ts": "1730000123"}}
try:
    r = httpx.post(url, json=payload, timeout=15)
    print("  HTTP", r.status_code, r.text[:200])
except Exception as exc:
    print("  请求失败:", exc)
    raise SystemExit(0)

if not secret:
    print("  （还没填 AppSecret，所以服务器无法签名——填上后再测一次）")
else:
    data = r.json()
    ok = _ed25519_verify(secret, "1730000123" + "ServerCheckToken123", data.get("signature", ""))
    print("  签名校验:", "✅ 通过（QQ 后台保存回调地址会成功）" if ok else "❌ 不通过")
PY

echo
echo "=== 3. 群列表接口 ==="
curl -s http://127.0.0.1:8091/api/qqbot/groups | head -c 300
echo
echo
echo "=== 4. 服务与配置页 ==="
systemctl is-active dorm
printf ' 配置页 js: %s\n' "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8091/js/pages/config.js)"
curl -s http://127.0.0.1:8091/js/pages/config.js | grep -c 'qqbotGroups' | sed 's/^/ 群里列表 UI 字段数: /'
rm -f /root/life_qqbot.tar.gz
