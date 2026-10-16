#!/usr/bin/env bash
# 部署「QQ 官方机器人 + 邮件推送」通知功能
set -eu
cd /www/dorm || exit 1

echo "=== 1. 解包新代码 ==="
mkdir -p /www/dorm-data/backups
[ -f /www/dorm-data/app.db ] && cp /www/dorm-data/app.db "/www/dorm-data/backups/app-$(date +%Y%m%d-%H%M%S).db"
tar -xzf /root/life_notify.tar.gz -C /www/dorm
for f in deploy/*.sh scripts/*.py; do
  grep -q $'\r' "$f" 2>/dev/null && sed -i 's/\r$//' "$f"
done
chmod +x deploy/*.sh
chown -R www-data:www-data /www/dorm-data 2>/dev/null || true
echo "代码已更新"

echo
echo "=== 2. 重启服务（自动补齐新配置项） ==="
systemctl restart dorm
sleep 6
systemctl is-active dorm

echo
echo "=== 3. 新配置项已写入数据库 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import settings_service as ss
db = SessionLocal()
keys = [k for k in ss.all_settings(db) if k.startswith('qqbot') or k.startswith('smtp')]
print("  共 %d 个通知相关配置项：%s" % (len(keys), ", ".join(sorted(keys))))
PY

echo
echo "=== 4. 通道自检（现在应该都是未配置状态） ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python scripts/notify_push.py check 2>&1 | tail -5 || true

echo
echo "=== 5. 生成 cron 任务（22:00 提醒 / 22:40 汇总） ==="
APP_DIR=/www/dorm DATA_DIR=/www/dorm-data bash deploy/install_cron.sh

echo
echo "=== 6. 交付状态 ==="
systemctl is-active dorm
ss -lntp | grep -E ':(8090|8091) '
printf ' 8091 页面 -> %s\n' "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8091/)"
printf ' 8091 js/pages/config.js -> %s\n' "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8091/js/pages/config.js)"
curl -s http://127.0.0.1:8091/js/pages/config.js | grep -c 'qqbot_app_id' | sed 's/^/ config.js 里的 qqbot 字段数: /'
echo
DORM_DATA_DIR=/www/dorm-data .venv/bin/python scripts/reset_server_data.py --status | tail -10
rm -f /root/life_notify.tar.gz
echo
echo "完成。下一步：登录 8091 →「系统配置 → QQ 官方机器人 / 邮件推送」填写。"
