#!/usr/bin/env bash
# 区分：是群没配对，还是网络问题
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

echo "############ 1. 到腾讯的网络（连续 8 次 TCP 探测） ############"
for i in $(seq 1 8); do
  start=$(date +%s%N)
  if timeout 6 bash -c "cat < /dev/null > /dev/tcp/api.sgroup.qq.com/443" 2>/dev/null; then
    end=$(date +%s%N)
    printf '  第 %s 次: ✅ 通  耗时 %s ms\n' "$i" "$(( (end - start) / 1000000 ))"
  else
    printf '  第 %s 次: ❌ 超时/失败\n' "$i"
  fi
done

echo
echo "############ 2. 用 access_token 直连发消息接口 ############"
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import asyncio
import subprocess
import sys

sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import push_service

db = SessionLocal()
token, reason = asyncio.run(push_service.get_access_token(db, force=True, retries=1, timeout=10))
if not token:
    print(f"  ❌ 取 token 失败：{reason}")
    db.close()
    raise SystemExit(0)
print(f"  ✅ 取到 token（长度 {len(token)}）")

# 旧群
old_group = "0AA8122EF2F56427CBB381D49A6314DC"
for label, group in (("旧群", old_group), ("随便一个假 openid", "AAAAAAAAAAAAAAAA")):
    print(f"\n  --- 测试 {label}: {group} ---")
    try:
        r = subprocess.run(
            ["curl", "-s", "-m", "25", "-w", "\nHTTP %{http_code} 耗时 %{time_total}s",
             "-X", "POST", f"https://api.sgroup.qq.com/v2/groups/{group}/messages",
             "-H", f"Authorization: QQBot {token}",
             "-H", "Content-Type: application/json",
             "-d", '{"content":"【测试】换群诊断","msg_type":0}'],
            capture_output=True, text=True, timeout=40, errors="replace")
        print("   ", (r.stdout or "").strip()[:300])
    except Exception as exc:
        print(f"    异常 {exc}")
db.close()
PY

echo
echo "############ 3. 网关当前状态 ############"
grep -iE '长连接已建立|已断开|鉴权失败' /www/dorm-data/logs/service.log 2>/dev/null | tail -4
echo -n "  当前长连接进程: "
pgrep -f 'cloudflared' >/dev/null && echo -n "" ; systemctl is-active dorm
