#!/usr/bin/env bash
# 验证管理员登录 + 管理接口可用
set -u
cd /www/dorm || exit 1

PW="${1:-344940}"
echo "=== 1. 登录接口（账号 admin） ==="
code=$(curl -s -o /tmp/lg.json -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
  -d "{\"username\":\"admin\",\"password\":\"$PW\"}" http://127.0.0.1:8091/api/auth/login)
echo "  HTTP $code"
head -c 160 /tmp/lg.json
echo

TOK=$(DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
import httpx
r = httpx.post('http://127.0.0.1:8091/api/auth/login',
               json={'username': 'admin', 'password': '344940'}, timeout=20)
print(r.json().get('token', '') if r.status_code == 200 else '')
PY
)
echo
echo "=== 2. 带令牌访问管理接口 ==="
if [ -n "$TOK" ]; then
  printf '  /api/accounts      -> %s\n' "$(curl -s -o /dev/null -w '%{http_code}' -H "X-Session-Token: $TOK" http://127.0.0.1:8091/api/accounts)"
  printf '  /api/fund/summary  -> %s\n' "$(curl -s -o /dev/null -w '%{http_code}' -H "X-Session-Token: $TOK" http://127.0.0.1:8091/api/fund/summary)"
  printf '  /api/dorms         -> %s\n' "$(curl -s -o /dev/null -w '%{http_code}' -H "X-Session-Token: $TOK" http://127.0.0.1:8091/api/dorms)"
  printf '  /api/logs/audit    -> %s\n' "$(curl -s -o /dev/null -w '%{http_code}' -H "X-Session-Token: $TOK" http://127.0.0.1:8091/api/logs/audit)"
  echo "  fund summary:"
  curl -s -H "X-Session-Token: $TOK" http://127.0.0.1:8091/api/fund/summary | head -c 220
  echo
else
  echo "  登录失败，拿不到令牌"
fi

echo
echo "=== 3. 错误密码应当被拒 ==="
curl -s -o /dev/null -w '  错密码 -> %{http_code}\n' -X POST -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"000000"}' http://127.0.0.1:8091/api/auth/login
echo
echo "=== 4. 公开端口仍拿不到管理接口 ==="
printf '  8090 /api/accounts -> %s\n' "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8090/api/accounts)"
printf '  8090 /api/fund/summary -> %s\n' "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8090/api/fund/summary)"
