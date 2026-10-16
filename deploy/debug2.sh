#!/usr/bin/env bash
# 查清：selftest 失败项 + 生产库那条填报记录是什么
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

echo "=== 1. 生产库里的填报记录 ==="
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.models import Report, Dorm

db = SessionLocal()
rows = db.query(Report).order_by(Report.id.desc()).limit(5).all()
print(f"  共 {db.query(Report).count()} 条：")
for r in rows:
    dorm = db.get(Dorm, r.dorm_id)
    print(f"    id={r.id} 宿舍={dorm.room_no if dorm else '?'} 日期={r.report_date}")
    print(f"      齐全={r.is_complete} 缺勤={r.absent_count} 备注={str(r.remark)[:40]!r}")
    print(f"      提交时间={getattr(r, 'submitted_at', '?')} 来源={getattr(r, 'source', '?')}")
db.close()
PY

echo
echo "=== 2. selftest 失败项 ==="
WORK=$(mktemp -d /tmp/st-XXXXXX)
DIR="$WORK/data"
mkdir -p "$DIR/backups" "$DIR/exports" "$DIR/uploads" "$DIR/logs"
DORM_DATA_DIR=/www/dorm-data SNAP="$DIR/app.db" .venv/bin/python - <<'PY' 2>/dev/null
import os, shutil, sys
sys.path.insert(0, '.')
from backend.services import backup_service
r = backup_service.create_backup(keep=200, tag="st")
if r.get("ok"):
    shutil.copyfile(r["path"], os.environ["SNAP"])
    os.unlink(r["path"])
PY
cp /www/dorm-data/secret.key "$DIR/secret.key" 2>/dev/null || true

DORM_DATA_DIR="$DIR" DORM_PORT=8196 DORM_ADMIN_PORT=8197 .venv/bin/python run.py > "$WORK/s.log" 2>&1 &
PID=$!
for _ in $(seq 1 60); do curl -fsS http://127.0.0.1:8196/api/health >/dev/null 2>&1 && break; sleep 0.5; done

DORM_DATA_DIR="$DIR" DORM_TEST_PUBLIC="http://127.0.0.1:8196" DORM_TEST_ADMIN="http://127.0.0.1:8197" \
  .venv/bin/python scripts/selftest.py http://127.0.0.1:8197 http://127.0.0.1:8196 2>&1 | grep -E 'FAIL|通过|失败明细|^  - ' | head -10

kill -9 $PID 2>/dev/null
rm -rf "$WORK"
