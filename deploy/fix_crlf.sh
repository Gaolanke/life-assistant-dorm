#!/usr/bin/env bash
# 把部署目录里的 shell 脚本统一成 LF 行尾（Windows 打包容易带 \r）。
# 用法： bash /root/fix_crlf.sh
set -u
cd /www/dorm || exit 1
for f in deploy/*.sh; do
  [ -f "$f" ] || continue
  if grep -q $'\r' "$f" 2>/dev/null; then
    sed -i 's/\r$//' "$f"
    echo "已转换：$f"
  fi
done
chmod +x deploy/*.sh 2>/dev/null
echo "--- 结果 ---"
file deploy/*.sh
