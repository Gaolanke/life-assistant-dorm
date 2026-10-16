#!/usr/bin/env bash
# 跑 QQ 相关测试，确认改 hex 后无回归
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

for t in test_qqbot test_qqbot_ws test_notify; do
  printf '  %-18s ' "$t"
  .venv/bin/python "scripts/$t.py" 2>&1 | grep -oE '通过 [0-9]+ 项，失败 [0-9]+ 项' | tail -1 || echo "未取到结果"
done
