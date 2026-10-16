#!/usr/bin/env bash
# 验证回调签名（服务器用 PyNaCl；跨库一致性已在本机用 cryptography 交叉验证过）
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

.venv/bin/python - <<'PY'
import base64
import sys

import httpx

sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import settings_service as ss

db = SessionLocal()
app_id = ss.get_setting(db, "qqbot_app_id")
secret = ss.get_setting(db, "qqbot_secret")
db.close()

print(f"  机器人 AppID = {app_id}")

PLAIN = "test_plain_token_abc123"
TS = "1728700000"

r = httpx.post(
    "https://xiaoaiyun.top/api/qqbot/events",
    json={"op": 13, "d": {"plain_token": PLAIN, "event_ts": TS}},
    timeout=30,
)
print(f"  回调接口 HTTP {r.status_code}")
returned = r.json().get("signature", "")

# 参考实现的种子推导：AppSecret 原始字节补足到 32
seed = secret.encode("utf-8")
while len(seed) < 32:
    seed *= 2
seed = seed[:32]

print(f"  seed(hex)      = {seed.hex()}")
print(f"  seed == secret = {seed == secret.encode()}")

from nacl.signing import SigningKey

expected = base64.b64encode(SigningKey(seed).sign((TS + PLAIN).encode()).signature).decode()
print(f"  接口返回签名   = {returned[:48]}...")
print(f"  参考种子签名   = {expected[:48]}...")
print()
if returned == expected:
    print("  ✅ 一致 → 平台回调校验会通过")
else:
    print("  ❌ 仍不一致")
PY
