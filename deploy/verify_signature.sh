#!/usr/bin/env bash
# 用正确的参考算法验证回调签名
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

# 参考实现（AstrBot）：seed = AppSecret 原始字节补足到 32
seed = secret.encode("utf-8")
while len(seed) < 32:
    seed *= 2
seed = seed[:32]

from cryptography.hazmat.primitives.asymmetric import ed25519

key = ed25519.Ed25519PrivateKey.from_private_bytes(seed)
expected = base64.b64encode(key.sign((TS + PLAIN).encode()).signature).decode()

print(f"  接口返回签名   = {returned[:48]}...")
print(f"  参考算法计算   = {expected[:48]}...")
print()
if returned == expected:
    print("  ✅ 签名与参考实现一致 —— 平台校验会通过")
else:
    print("  ❌ 仍不一致")
PY
