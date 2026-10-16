#!/usr/bin/env bash
# 调试：一致性快照到底拿到了什么
set -u
cd /www/dorm || exit 1

echo "=== 直接调 backup_service ==="
DORM_DATA_DIR=/www/dorm-data TEST_TARGET=/tmp/snap-test.db .venv/bin/python - <<'PY'
import os
import shutil
import sqlite3
import sys

sys.path.insert(0, '.')
from backend.services import backup_service

target = os.environ["TEST_TARGET"]
result = backup_service.create_backup(keep=200, tag="dbg")
print("  backup ok:", result.get("ok"), "|", result.get("message"))
if result.get("ok"):
    shutil.copyfile(result["path"], target)
    os.unlink(result["path"])
    con = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    for t in ("dorms", "members", "fund_entries", "accounts"):
        print(f"    快照 {t}: {con.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0]}")
    con.close()

print()
print("=== 直接读生产库 ===")
con = sqlite3.connect("file:/www/dorm-data/app.db?mode=ro", uri=True)
for t in ("dorms", "members", "fund_entries", "accounts"):
    print(f"    生产 {t}: {con.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0]}")
con.close()

print()
print("=== 生产库目录文件 ===")
PY
ls -lh /www/dorm-data/app.db* 2>&1
