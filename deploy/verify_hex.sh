#!/usr/bin/env bash
# 用官方样例验证线上接口返回的签名（hex，128 字符）
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

.venv/bin/python - <<'PY'
import sys

import httpx

sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import settings_service as ss

db = SessionLocal()
app_id = ss.get_setting(db, "qqbot_app_id")
db.close()
print(f"  线上机器人 AppID = {app_id}")

PLAIN = "Arq0D5A61EgUu4OxUvOp"
TS = "1725442341"

r = httpx.post(
    "https://xiaoaiyun.top/api/qqbot/events",
    json={"d": {"plain_token": PLAIN, "event_ts": TS}, "op": 13},
    timeout=30,
)
print(f"  接口 HTTP {r.status_code}")
sig = r.json().get("signature", "")
print(f"  返回签名 = {sig}")
print(f"  长度     = {len(sig)}（官方要求 128 位十六进制）")
print()

# 官方样例（secret 不同，所以签名不同）：这里只校验格式与算法自洽
import re

is_hex = bool(re.fullmatch(r"[0-9a-f]{128}", sig))
print(f"  格式为 128 位十六进制: {'✅' if is_hex else '❌'}")

# 用线上 AppSecret 独立复算
db = SessionLocal()
secret = ss.get_setting(db, "qqbot_secret").strip()
db.close()
seed = secret.encode("utf-8")
while len(seed) < 32:
    seed *= 2
seed = seed[:32]
from nacl.signing import SigningKey

expected = SigningKey(seed).sign((TS + PLAIN).encode()).signature.hex()
print(f"  独立复算 = {expected}")
print(f"  两者一致 = {'✅ 是' if expected == sig else '❌ 否'}")
PY
