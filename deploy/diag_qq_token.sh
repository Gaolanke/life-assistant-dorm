#!/usr/bin/env bash
# 诊断服务器到 bots.qq.com 的网络（换 token 用的域名）
set -u
cd /www/dorm || exit 1
APPID=$(DORM_DATA_DIR=/www/dorm-data .venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from backend.database import SessionLocal
from backend.services import settings_service as ss
db=SessionLocal(); print(ss.get_setting(db,'qqbot_app_id'))
")
SECRET=$(DORM_DATA_DIR=/www/dorm-data .venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from backend.database import SessionLocal
from backend.services import settings_service as ss
db=SessionLocal(); print(ss.get_setting(db,'qqbot_secret'))
")

echo "=== 1. DNS 解析 ==="
getent hosts bots.qq.com || echo "  解析失败"
echo "  IPv4:"; getent ahostsv4 bots.qq.com | head -5

echo
echo "=== 2. TCP 443 连通性（每个 IP 都试） ==="
for ip in $(getent ahostsv4 bots.qq.com | awk '{print $1}' | sort -u | head -5); do
  if timeout 6 bash -c "cat < /dev/null > /dev/tcp/$ip/443" 2>/dev/null; then
    echo "  $ip:443 可连 ✅"
  else
    echo "  $ip:443 不通 ❌"
  fi
done

echo
echo "=== 3. curl 换 token（多种方式） ==="
for ip in $(getent ahostsv4 bots.qq.com | awk '{print $1}' | sort -u | head -3); do
  code=$(curl -s -m 12 -o /tmp/tok.json -w '%{http_code}' \
    --resolve "bots.qq.com:443:$ip" \
    -X POST -H 'Content-Type: application/json' \
    -d "{\"appId\":\"$APPID\",\"clientSecret\":\"$SECRET\"}" \
    https://bots.qq.com/app/getAppAccessToken 2>/dev/null || echo "超时")
  printf '  --resolve %-16s -> %s %s\n' "$ip" "$code" "$(head -c 90 /tmp/tok.json 2>/dev/null)"
done

echo
echo "=== 4. 强制 IPv4 的 python 请求 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import socket
import sys
sys.path.insert(0, '.')
import httpx

appid = None
secret = None
from backend.database import SessionLocal
from backend.services import settings_service as ss
db = SessionLocal()
appid = ss.get_setting(db, 'qqbot_app_id')
secret = ss.get_setting(db, 'qqbot_secret')
db.close()

print("  默认解析:", socket.getaddrinfo('bots.qq.com', 443, socket.AF_INET)[:2])
for timeout in (10, 20):
    try:
        r = httpx.post('https://bots.qq.com/app/getAppAccessToken',
                       json={'appId': appid, 'clientSecret': secret},
                       timeout=httpx.Timeout(timeout, connect=timeout),
                       trust_env=False)
        print(f"  timeout={timeout}s -> HTTP {r.status_code} {r.text[:100]}")
        break
    except Exception as exc:
        print(f"  timeout={timeout}s -> {type(exc).__name__}: {str(exc)[:110]}")

# 对照：发消息用的域名
try:
    r2 = httpx.get('https://api.sgroup.qq.com/', timeout=10, trust_env=False)
    print("  对照 api.sgroup.qq.com ->", r2.status_code)
except Exception as exc:
    print("  对照 api.sgroup.qq.com ->", type(exc).__name__, str(exc)[:80])
PY

echo
echo "=== 5. 有没有走代理 / 特殊路由 ==="
env | grep -i proxy || echo "  没有代理环境变量"
ip route get 109.244.244.163 2>/dev/null | head -2 || true
