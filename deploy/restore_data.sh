#!/usr/bin/env bash
# 从备份恢复生产数据（14 间真实宿舍 / 44 名同学）
set -eu
cd /www/dorm || exit 1

SRC="/www/dorm-data/backups/app_20261011_201141_manual.db"
DB="/www/dorm-data/app.db"
STAMP=$(date +%Y%m%d_%H%M%S)
SAFE="/www/dorm-data/backups/app_BROKEN_${STAMP}.db"

[ -f "$SRC" ] || { echo "找不到备份：$SRC"; exit 1; }

echo "=== 1. 停服务 ==="
systemctl stop dorm
sleep 2
echo "  已停止"

echo
echo "=== 2. 先把当前（被清空的）数据库留一份，万一要查 ==="
cp "$DB" "$SAFE"
echo "  已留存：$SAFE"

echo
echo "=== 3. 恢复 ==="
rm -f "$DB"-wal "$DB"-shm
cp "$SRC" "$DB"
chown www-data:www-data "$DB" 2>/dev/null || true
chmod 664 "$DB"
echo "  已从 $SRC 恢复"

echo
echo "=== 4. 启动 ==="
systemctl start dorm
sleep 10
systemctl is-active dorm

echo
echo "=== 5. 校验恢复结果 ==="
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
import os
os.environ["DORM_DATA_DIR"] = "/www/dorm-data"
from sqlalchemy import func, select
from backend import config
from backend.database import SessionLocal
from backend.models import Account, BotGroup, Dorm, FundEntry, Member, Report, Setting

db = SessionLocal()
print("  数据库:", config.DB_PATH)
for name, model in (("宿舍", Dorm), ("人员", Member), ("填报", Report),
                    ("班费明细", FundEntry), ("账号", Account), ("机器人群", BotGroup)):
    print(f"    {name:<8} {db.execute(select(func.count(model.id))).scalar()}")

print()
print("  宿舍列表:", ", ".join(d.room_no for d in db.execute(select(Dorm).order_by(Dorm.sort_order, Dorm.room_no)).scalars()))
print()
print("  关键配置:")
for k in ("qqbot_groups", "qqbot_enabled", "qq_report_time", "report_deadline", "auto_backup_time"):
    row = db.execute(select(Setting).where(Setting.key == k)).scalar()
    print(f"    {k:<20} = {row.value if row else '(缺失)'!r}")
print()
for a in db.execute(select(Account)).scalars():
    print(f"  账号: {a.username} / {a.role} / {'启用' if a.active else '停用'}")
db.close()
PY

echo
echo "=== 6. 服务自检 ==="
curl -s -o /dev/null -w "  8090 -> %{http_code}\n" http://127.0.0.1:8090/api/health
curl -s -o /dev/null -w "  8091 -> %{http_code}\n" http://127.0.0.1:8091/api/system/mode
curl -s http://127.0.0.1:8090/api/dorms | head -c 160
echo
