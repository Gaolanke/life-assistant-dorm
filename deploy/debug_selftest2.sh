#!/usr/bin/env bash
# 单独在隔离实例上跑 selftest，看哪一项失败
set -u
cd /www/dorm || exit 1

PROD_DIR=/www/dorm-data
WORK=$(mktemp -d /tmp/selftest-XXXXXX)
DIR="$WORK/data"
mkdir -p "$DIR/backups" "$DIR/exports" "$DIR/uploads" "$DIR/logs"

# 用一致性快照做种子
DORM_DATA_DIR="$PROD_DIR" SNAP="$DIR/app.db" .venv/bin/python - <<'PY' 2>/dev/null
import os, shutil, sys
sys.path.insert(0, '.')
from backend.services import backup_service
r = backup_service.create_backup(keep=200, tag="selftest")
if r.get("ok"):
    shutil.copyfile(r["path"], os.environ["SNAP"])
    os.unlink(r["path"])
PY
[ -f "$DIR/secret.key" ] || cp "$PROD_DIR/secret.key" "$DIR/secret.key" 2>/dev/null || true

DORM_DATA_DIR="$DIR" DORM_PORT=8194 DORM_ADMIN_PORT=8195 \
  .venv/bin/python run.py > "$WORK/server.log" 2>&1 &
PID=$!

for _ in $(seq 1 60); do
  curl -fsS "http://127.0.0.1:8194/api/health" >/dev/null 2>&1 && break
  sleep 0.5
done

export DORM_TEST_PUBLIC="http://127.0.0.1:8194"
export DORM_TEST_ADMIN="http://127.0.0.1:8195"
export DORM_DATA_DIR="$DIR"

.venv/bin/python scripts/selftest.py "$DORM_TEST_ADMIN" "$DORM_TEST_PUBLIC" 2>&1 | grep -E 'FAIL|通过|失败' | head -20

kill -9 $PID 2>/dev/null
rm -rf "$WORK"
