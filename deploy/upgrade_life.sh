#!/usr/bin/env bash
# 升级到「生活助手 + 账号登录 + 班费」版本
set -u
cd /www/dorm || exit 1

echo "=== 1. 备份数据库 ==="
mkdir -p /www/dorm-data/backups
if [ -f /www/dorm-data/app.db ]; then
  cp /www/dorm-data/app.db "/www/dorm-data/backups/app-$(date +%Y%m%d-%H%M%S).db"
  ls -lh /www/dorm-data/backups | tail -2
fi

echo
echo "=== 2. 解包新代码 ==="
tar -xzf /root/life_deploy.tar.gz -C /www/dorm
for f in deploy/*.sh scripts/*.py; do
  grep -q $'\r' "$f" 2>/dev/null && sed -i 's/\r$//' "$f"
done
chmod +x deploy/*.sh
chown -R www-data:www-data /www/dorm-data 2>/dev/null || true
echo "代码已更新（程序名：生活助手）"

echo
echo "=== 3. 重启服务（自动补列 + 建超级管理员） ==="
systemctl restart dorm
sleep 7
systemctl is-active dorm
journalctl -u dorm -n 14 --no-pager | grep -E "超级管理员|初始密码|登录地址|数据库|error|Error" | tail -10

echo
echo "=== 4. 数据库结构检查 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sqlite3
con = sqlite3.connect('/www/dorm-data/app.db')
tables = [r[0] for r in con.execute("select name from sqlite_master where type='table' order by name")]
print(" 数据表:", ", ".join(tables))
for table in ('accounts', 'fund_entries', 'fund_settings'):
    if table in tables:
        cols = [r[1] for r in con.execute('PRAGMA table_info(%s)' % table)]
        print("  %s: %s" % (table, ", ".join(cols)))
    else:
        print("  %s: 缺失！" % table)
print(" 已废弃的 admin_devices 表:", "仍存在（无害）" if 'admin_devices' in tables else "已不存在")
con.close()
PY

echo
echo "=== 5. 账号清单 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python scripts/admin_account.py --list 2>&1 | tail -12

echo
echo "=== 6. 服务自检（管理端口 8091） ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python scripts/selftest.py http://127.0.0.1:8091 2>&1 | tail -5

echo
echo "=== 7. 清空所有业务数据（保留管理员账号和配置） ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python scripts/reset_server_data.py | tail -6
systemctl restart dorm
sleep 6

echo
echo "=== 8. 交付状态 ==="
systemctl is-active dorm
ss -lntp | grep -E ':(8090|8091) '
echo "--- 数据 ---"
DORM_DATA_DIR=/www/dorm-data .venv/bin/python scripts/reset_server_data.py --status | tail -10
echo "--- 端口隔离 ---"
printf ' 8090 /api/fund/summary  -> %s\n' "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8090/api/fund/summary)"
printf ' 8091 /api/fund/summary  -> %s\n' "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8091/api/fund/summary)"
printf ' 8091 /api/accounts      -> %s\n' "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8091/api/accounts)"
printf ' 8090 页面               -> %s\n' "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8090/)"
printf ' 8091 页面               -> %s\n' "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8091/)"
echo "--- 公网 ---"
printf ' 公网 8090 -> %s\n' "$(curl -s -m 6 -o /dev/null -w '%{http_code}' http://111.228.38.170:8090/api/health)"
printf ' 公网 8091 -> %s\n' "$(curl -s -m 6 -o /dev/null -w '%{http_code}' http://111.228.38.170:8091/api/health)"
rm -f /root/life_deploy.tar.gz
