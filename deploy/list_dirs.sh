#!/usr/bin/env bash
# 列出备份目录、数据目录、导出目录的实际内容
set -u
echo "=== /www/dorm-data ==="
ls -lh /www/dorm-data/ 2>&1

echo
echo "=== /www/dorm-data/backups ==="
ls -lh /www/dorm-data/backups/ 2>&1 | tail -20

echo
echo "=== /www/dorm-data/exports ==="
ls -lh /www/dorm-data/exports/ 2>&1 | tail -10

echo
echo "=== 备份目录里所有 .db 文件 ==="
find /www/dorm-data -name "*.db" -printf '%p  %s bytes  %TY-%Tm-%Td %TH:%TM\n' 2>/dev/null | sort -k4 -r | head -20

echo
echo "=== 配置里的路径 ==="
cd /www/dorm
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend import config
print("  DATA_DIR  :", config.DATA_DIR)
print("  DB_PATH   :", config.DB_PATH)
print("  BACKUP_DIR:", config.BACKUP_DIR)
print("  备份数量  :", len(list(config.BACKUP_DIR.glob('app_*.db'))))
PY
