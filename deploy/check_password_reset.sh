#!/usr/bin/env bash
# 服务器端验证：密码 设置 / 重置 / 取消 全流程（用现有管理端口和访问码）
set -u
cd /www/dorm || exit 1

echo "=== 造两间测试寝室 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal, init_db
from backend.models import Dorm, Member
from backend.services import settings_service as ss

init_db()
db = SessionLocal()
ss.ensure_settings(db)
for room in ("T-901", "T-902"):
    dorm = db.query(Dorm).filter(Dorm.room_no == room).first()
    if dorm is None:
        dorm = Dorm(room_no=room, room_label="测试楼" + room, building="测试楼", leader_name="测试寝室长")
        db.add(dorm)
        db.commit()
        db.refresh(dorm)
        db.add(Member(dorm_id=dorm.id, name="测试同学", student_no="2025001", room_no=room, role="宿舍长"))
        db.commit()
print("测试寝室已就绪")
db.close()
PY

echo
echo "=== 密码 设置 / 重置 / 取消 测试 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python scripts/test_password_reset.py http://127.0.0.1:8091 http://127.0.0.1:8090 2>&1 | tail -14

echo
echo "=== 清理测试数据 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.models import Dorm

db = SessionLocal()
rows = db.query(Dorm).filter(Dorm.room_no.like("T-9%")).all()
for dorm in rows:
    db.delete(dorm)
db.commit()
db.close()
print("已清理测试寝室 %d 间" % len(rows))
PY
