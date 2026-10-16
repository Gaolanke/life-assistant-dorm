#!/usr/bin/env bash
# 服务器端验证：对齐数据目录 + 跑完整自检（管理端口）
set -u
cd /www/dorm || exit 1

# 1. 统一 LF 行尾并加执行权限
for f in deploy/install.sh scripts/*.py; do
  if grep -q $'\r' "$f" 2>/dev/null; then
    sed -i 's/\r$//' "$f"
    echo "已转换行尾：$f"
  fi
done
chmod +x deploy/*.sh 2>/dev/null || true

echo
echo "=== 数据目录对齐检查 ==="
.venv/bin/python scripts/admin_account.py --list 2>&1 | tail -12

echo
echo "=== 完整自检（管理端口 8091） ==="
.venv/bin/python scripts/selftest.py http://127.0.0.1:8091 2>&1 | tail -8
