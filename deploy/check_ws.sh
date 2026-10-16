#!/usr/bin/env bash
# 验证 QQ 机器人 WebSocket 长连接：服务是否真连上了腾讯网关
set -u
cd /www/dorm || exit 1

echo "=== 1. 服务状态 ==="
systemctl is-active dorm
sleep 2

echo
echo "=== 2. 日志里 WebSocket 相关输出 ==="
journalctl -u dorm -n 120 --no-pager 2>/dev/null | grep -iE "qqbot|websocket|网关|gateway|长连接" | tail -12 || echo "  （暂无相关日志）"

echo
echo "=== 3. 单独跑一次连接，看能不能连上真网关 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import asyncio
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import qqbot_gateway, push_service

async def probe():
    db = SessionLocal()
    token, reason = await push_service.get_access_token(db, force=True)
    print("  取 token:", "✅" if token else f"❌ {reason}")
    if not token:
        db.close()
        return
    import httpx
    base = push_service.api_base(db)
    db.close()
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{base}/gateway",
                             headers={"Authorization": f"QQBot {token}"})
    print("  GET /gateway ->", r.status_code, r.text[:200])
    url = (r.json() or {}).get("url")
    if not url:
        return
    print("  网关地址:", url)
    # 真连一次，收到 Hello 就算通过
    import websockets, json as _json
    try:
        async with websockets.connect(url, max_size=2**22) as ws:
            raw = await asyncio.wait_for(ws.recv(), timeout=20)
            msg = _json.loads(raw)
            print("  收到首包 op =", msg.get("op"), "（10 = Hello，说明长连接通了 ✅）")
            await ws.send(_json.dumps({
                "op": 2,
                "d": {"token": f"QQBot {token}", "intents": 1 << 25, "shard": [0, 1]},
            }))
            print("  已发送 Identify(op=2)")
            for _ in range(3):
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=8)
                    m = _json.loads(raw)
                    print("    收到 op =", m.get("op"), "t =", m.get("t"))
                    if m.get("op") == 0:
                        print("    → 收到事件！", _json.dumps(m.get("d"), ensure_ascii=False)[:200])
                except asyncio.TimeoutError:
                    print("    （暂无更多消息）")
                    break
    except Exception as exc:
        print("  连接失败:", type(exc).__name__, str(exc)[:150])

asyncio.run(probe())
PY

echo
echo "=== 4. 群里有没有上报过（openid 列表） ==="
curl -s http://127.0.0.1:8091/api/qqbot/groups | head -c 400
echo
rm -f /root/life_ws.tar.gz
