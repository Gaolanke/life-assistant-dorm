#!/usr/bin/env bash
# 服务器端验证：控制台/账号管理页不再调失效接口 + 密码可自由修改
set -u
cd /www/dorm || exit 1

echo "=== 1. 重启服务 ==="
systemctl restart dorm
sleep 6
systemctl is-active dorm

echo
echo "=== 2. 前端资源检查（不该再有失效接口引用） ==="
for asset in /js/pages/console.js /js/pages/accounts.js /js/core.js; do
  body=$(curl -s "http://127.0.0.1:8091$asset")
  bad=0
  for dead in "/api/access/code" "/api/access/devices" "/api/access/verify"; do
    if printf '%s' "$body" | grep -q "$dead"; then
      echo "  $asset 仍引用 $dead ❌"
      bad=1
    fi
  done
  [ "$bad" = "0" ] && echo "  $asset 干净 ✅"
done

echo
echo "=== 3. 账号接口与自由改密码 ==="
PW=344940
TOK=$(DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
import httpx
r = httpx.post('http://127.0.0.1:8091/api/auth/login',
               json={'username': 'admin', 'password': '344940'}, timeout=20)
print(r.json().get('token', '') if r.status_code == 200 else '')
PY
)
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
import httpx

base = 'http://127.0.0.1:8091'
c = httpx.Client(base_url=base, timeout=30)
r = c.post('/api/auth/login', json={'username': 'admin', 'password': '344940'})
print("  登录:", r.status_code)
h = {'X-Session-Token': r.json().get('token', '')}
print("  账号列表:", c.get('/api/accounts', headers=h).status_code)
print("  控制台寝室长一览:", c.get('/api/access/leader/accounts', headers=h).status_code)
print("  已删除的访问码接口:", c.get('/api/access/code', headers=h).status_code, '(应为 404)')
print("  已删除的设备接口:", c.get('/api/access/devices', headers=h).status_code, '(应为 404)')
# 建一个演示账号，自由设密码，验证后删除
new = c.post('/api/accounts', headers=h, json={'username': 'tmp_demo', 'role': 'admin', 'password': 'tmp123456'})
print("  新建账号:", new.status_code)
if new.status_code == 200:
    aid = new.json()['account']['id']
    setpwd = c.post(f'/api/accounts/{aid}/password', headers=h, json={'new_password': '自由设定的密码88'})
    print("  给他人设自定义密码:", setpwd.status_code, setpwd.json().get('password'))
    print("  用该密码登录:", c.post('/api/auth/login', json={'username': 'tmp_demo', 'password': '自由设定的密码88'}).status_code)
    c.delete(f'/api/accounts/{aid}', headers=h)
    print("  已删除演示账号")
PY

echo
echo "=== 4. 公开端口隔离 ==="
printf '  8090 /api/accounts        -> %s (应 404)\n' "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8090/api/accounts)"
printf '  8090 /api/fund/summary    -> %s (应 404)\n' "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8090/api/fund/summary)"
printf '  8090 /api/access/leader/accounts -> %s (应 404)\n' "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8090/api/access/leader/accounts)"
printf '  8090 页面 -> %s | 8091 页面 -> %s\n' "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8090/)" "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8091/)"

echo
echo "=== 5. 数据与账号 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python scripts/reset_server_data.py --status | tail -10
DORM_DATA_DIR=/www/dorm-data .venv/bin/python scripts/admin_account.py --list 2>&1 | tail -6
