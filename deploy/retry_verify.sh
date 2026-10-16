#!/usr/bin/env bash
# 网络恢复后验证新凭证：反复重试取 token + 连网关
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

echo "=== 1. 到腾讯的网络（10 次探测）==="
ok=0
for i in $(seq 1 10); do
  if timeout 6 bash -c "cat < /dev/null > /dev/tcp/bots.qq.com/443" 2>/dev/null; then
    printf '  %s: ✅  ' "$i"; ok=$((ok+1))
  else
    printf '  %s: ❌  ' "$i"
  fi
done
echo
echo "  成功 $ok/10"

echo
echo "=== 2. 反复尝试取 token（最多 8 次）==="
.venv/bin/python - <<'PY'
import asyncio
import sys
import time

sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import push_service

db = SessionLocal()
for attempt in range(1, 9):
    tok, reason = asyncio.run(
        push_service.get_access_token(db, force=True, retries=1, timeout=12)
    )
    if tok:
        print(f"  第 {attempt} 次: ✅ 取到 token（长度 {len(tok)}）")
        print("  → 新机器人的 AppID / AppSecret 正确！")
        break
    print(f"  第 {attempt} 次: ❌ {reason}")
    time.sleep(3)
else:
    print("  8 次都失败：当前网络到腾讯不通，稍后再试")
db.close()
PY

echo
echo "=== 3. 网关日志（最新 6 条）==="
grep -iE 'qqbot.gateway' /www/dorm-data/logs/service.log | tail -6
