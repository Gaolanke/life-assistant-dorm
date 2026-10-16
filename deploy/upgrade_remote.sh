#!/usr/bin/env bash
# 服务器端升级：解包新代码 → 重启服务（自动补列）→ 自检 → 清空数据
set -u
cd /www/dorm || exit 1

echo "=== 1. 备份现有数据 ==="
mkdir -p /www/dorm-data/backups
if [ -f /www/dorm-data/app.db ]; then
  cp /www/dorm-data/app.db "/www/dorm-data/backups/app-$(date +%Y%m%d-%H%M%S).db"
  ls -lh /www/dorm-data/backups | tail -3
fi

echo
echo "=== 2. 解包新代码 ==="
tar -xzf /root/dorm_deploy.tar.gz -C /www/dorm
for f in deploy/*.sh scripts/*.py; do
  grep -q $'\r' "$f" 2>/dev/null && sed -i 's/\r$//' "$f"
done
chmod +x deploy/*.sh
chown -R www-data:www-data /www/dorm-data 2>/dev/null || true
echo "代码已更新"

echo
echo "=== 3. 重启服务（会自动补新增的数据库列） ==="
systemctl restart dorm
sleep 6
systemctl is-active dorm
journalctl -u dorm -n 8 --no-pager | tail -8

echo
echo "=== 4. 服务自检（管理端口 8091） ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python scripts/selftest.py http://127.0.0.1:8091 2>&1 | tail -5

echo
echo "=== 5. 清空所有填写数据，交付干净库 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python scripts/reset_server_data.py
systemctl restart dorm
sleep 5

echo
echo "=== 6. 交付状态 ==="
systemctl is-active dorm
ss -lntp | grep -E ':(8090|8091) '
DORM_DATA_DIR=/www/dorm-data .venv/bin/python scripts/reset_server_data.py --status | tail -8
echo
echo "管理员账号："
DORM_DATA_DIR=/www/dorm-data .venv/bin/python scripts/admin_account.py --list 2>&1 | tail -12
rm -f /root/dorm_deploy.tar.gz
