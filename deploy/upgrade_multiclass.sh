#!/usr/bin/env bash
# 多班级管理版本升级：备份数据库 → 解包 → 重启（自动迁移）→ 验证
# 注意：本次升级【保留全部业务数据】，老数据自动归入默认班级
set -u
cd /www/dorm || exit 1

echo "=== 1. 备份数据库 ==="
mkdir -p /www/dorm-data/backups
if [ -f /www/dorm-data/app.db ]; then
  cp /www/dorm-data/app.db "/www/dorm-data/backups/app-$(date +%Y%m%d-%H%M%S).db"
  ls -lh /www/dorm-data/backups | tail -3
else
  echo "  （警告：没有找到 /www/dorm-data/app.db）"
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
echo "=== 3. 重启服务（自动执行多班级迁移：建表 + 补列 + 默认班级收养老数据） ==="
systemctl restart dorm
sleep 10
systemctl is-active dorm
journalctl -u dorm -n 40 --no-pager | grep -E "班级|数据库|升级|error|Error|Traceback" | tail -12

echo
echo "=== 4. 迁移结果验证 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.models import SchoolClass, Dorm, FundSetting, BotGroup

db = SessionLocal()
classes = db.query(SchoolClass).order_by(SchoolClass.id).all()
print(f"  班级数: {len(classes)}")
for c in classes:
    dorms = db.query(Dorm).filter(Dorm.class_id == c.id).count()
    print(f"    - {c.name} (id={c.id}): {dorms} 个宿舍")
orphans = db.query(Dorm).filter((Dorm.class_id == 0) | (Dorm.class_id.is_(None))).count()
print(f"  未归班的宿舍（应为 0）: {orphans}")
groups = db.query(BotGroup).all()
print(f"  QQ 群绑定数: {sum(1 for g in groups if (g.class_id or 0) > 0)} / 共 {len(groups)} 个群（未绑定的走全局配置，正常）")
db.close()
PY

echo
echo "=== 5. 定时任务核对（实际数 = 班级×(1群汇报+提醒条数) + 备份/导出） ==="
ADDED=$(journalctl -u dorm --since "-2 min" --no-pager | grep -c 'Added job')
echo "  本次启动注册的任务数: ${ADDED:-0}"
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import class_service, settings_service as ss
db = SessionLocal()
expected = 2  # 数据库备份 + 自动导出
for c in class_service.list_classes(db):
    reminders = [r for r in ss.get_reminders(db, class_id=c.id) if r.get("enabled", True)]
    expected += 1 + len(reminders)
    print(f"  {c.name}: 1 个群汇报 + {len(reminders)} 条启用提醒")
print(f"  期望任务总数: {expected}")
db.close()
PY

echo
echo "=== 6. 端口隔离与新接口 ==="
printf ' 8090 /api/classes      -> %s（应 404，公开端拦截）\n' "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8090/api/classes)"
printf ' 8091 /api/classes      -> %s（应 401，未登录）\n' "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8091/api/classes)"
printf ' 8090 /api/dorms        -> %s（应 200）\n' "$(curl -s -o /dev/null -w '%{http_code}' 'http://127.0.0.1:8090/api/dorms?with_members=false&class_id=-1')"
printf ' 8091 /api/fund/summary -> %s（应 401，未登录）\n' "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8091/api/fund/summary)"

echo
echo "=== 7. 交付状态 ==="
systemctl is-active dorm
ss -lntp | grep -E ':(8090|8091) '
printf ' 公网 8090 -> %s\n' "$(curl -s -m 6 -o /dev/null -w '%{http_code}' http://111.228.38.170:8090/api/health)"
printf ' 公网 8091 -> %s\n' "$(curl -s -m 6 -o /dev/null -w '%{http_code}' http://111.228.38.170:8091/api/health)"
printf ' 填报站    -> %s\n' "$(curl -s -m 8 -o /dev/null -w '%{http_code}' https://xiaoaiyun.top/api/health)"
printf ' 管理端    -> %s\n' "$(curl -s -m 8 -o /dev/null -w '%{http_code}' https://admin.xiaoaiyun.top/api/health)"
rm -f /root/dorm_deploy.tar.gz
echo
echo "升级完成。请到管理端「班级管理」确认班级名称，并把 QQ 群绑定到对应班级。"
