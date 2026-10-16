#!/usr/bin/env bash
# 网络恢复后重测哪些群可用
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

echo "=== 网络探测 ==="
ok=0
for i in $(seq 1 8); do
  if timeout 6 bash -c "cat < /dev/null > /dev/tcp/api.sgroup.qq.com/443" 2>/dev/null; then
    ok=$((ok+1)); printf '✅'
  else
    printf '❌'
  fi
done
echo "  成功 $ok/8"

echo
echo "=== 逐个测试群（每群最多试 4 次） ==="
.venv/bin/python - <<'PY'
import asyncio
import sys

sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import push_service, settings_service as ss

db = SessionLocal()
raw = ss.get_setting(db, "qqbot_groups")
targets = [g.strip() for g in raw.replace("，", ",").split(",") if g.strip()]

for t in targets:
    result = None
    for attempt in range(1, 5):
        r = asyncio.run(push_service.send_group_message(
            db, t, "【生活助手】群可用性检测，收到请忽略。", attempts=1))
        if r.get("ok"):
            result = ("ok", attempt, r)
            break
        result = ("fail", attempt, r)
    kind, attempt, r = result
    if kind == "ok":
        print(f"  ✅ {t[:26]}…  第 {attempt} 次成功")
    else:
        print(f"  ❌ {t[:26]}…  {str(r.get('message'))[:46]}")
        if r.get("code"):
            print(f"       错误码 {r.get('code')}")
db.close()
PY
