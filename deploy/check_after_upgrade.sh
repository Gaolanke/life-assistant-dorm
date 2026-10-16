#!/usr/bin/env bash
# 升级后的验收检查
set -u
cd /www/dorm || exit 1

echo "=== 1. 数据库新列（确认自动升级生效） ==="
cat > /tmp/_cols.py <<'PY'
import sqlite3
con = sqlite3.connect('/www/dorm-data/app.db')
for table in ('reports', 'audit_logs', 'push_logs'):
    cols = [row[1] for row in con.execute('PRAGMA table_info(%s)' % table)]
    wanted = [c for c in cols if 'ip' in c or 'agent' in c]
    print(' %-12s -> %s' % (table, wanted or '（缺少！）'))
con.close()
PY
.venv/bin/python /tmp/_cols.py

echo
echo "=== 2. 端口隔离（管理接口只在 8091） ==="
for path in /api/logs/submissions /api/logs/audit /api/access/code /api/settings; do
  pub=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8090$path")
  adm=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8091$path")
  printf ' %-26s 公开端口=%s  管理端口=%s\n' "$path" "$pub" "$adm"
done

echo
echo "=== 3. 前端资源 ==="
for asset in / /js/pages/logs.js /js/app.js /js/core.js /css/style.css; do
  printf ' %-22s %s\n' "$asset" "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8091$asset)"
done

echo
echo "=== 4. 服务与数据 ==="
systemctl is-active dorm
ss -lntp | grep -E ':(8090|8091) '
DORM_DATA_DIR=/www/dorm-data .venv/bin/python scripts/reset_server_data.py --status | tail -8
echo
DORM_DATA_DIR=/www/dorm-data .venv/bin/python scripts/admin_account.py --list 2>&1 | head -12

echo
echo "=== 5. 公网可达性（从服务器访问自己的公网 IP） ==="
for port in 8090 8091; do
  code=$(curl -s -m 6 -o /dev/null -w '%{http_code}' "http://111.228.38.170:$port/api/health")
  echo " 公网 $port -> $code"
done
