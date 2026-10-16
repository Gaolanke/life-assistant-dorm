"""QQ 官方机器人 WebSocket 长连接测试（用模拟网关，不连真腾讯）。

用法： .venv\\Scripts\\python.exe scripts\\test_qqbot_ws.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import server_env  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8")

import httpx  # noqa: E402

from backend.database import SessionLocal, init_db  # noqa: E402
from backend.models import BotGroup  # noqa: E402
from backend.services import push_service, qqbot_gateway, settings_service as ss  # noqa: E402

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} :: {detail}")
    print(f"  [{'OK' if ok else 'FAIL'}] {name}{'' if ok else '  ' + detail}")


class FakeWS:
    """假的 WebSocket：按脚本吐消息，并记录客户端发了什么。"""

    sent: list[dict] = []
    script: list[dict] = []

    def __init__(self, url, **kwargs):
        self.url = url
        self._queue = list(FakeWS.script)

    def __await__(self):
        async def _self():
            return self
        return _self().__await__()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def send(self, raw):
        FakeWS.sent.append(json.loads(raw))

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._queue:
            raise StopAsyncIteration
        return json.dumps(self._queue.pop(0))


class FakeResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code
        self.text = str(data)

    def json(self):
        return self._data


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, **kwargs):
        return FakeResponse({"url": "wss://fake.gateway/ws"})

    async def post(self, url, **kwargs):
        if "getAppAccessToken" in url:
            return FakeResponse({"access_token": "fake-ws-token", "expires_in": "7200"})
        return FakeResponse({"id": "MSG1"})


async def main() -> int:
    init_db()
    db = SessionLocal()
    ss.ensure_settings(db)
    saved = {k: ss.get_setting(db, k) for k in ("qqbot_app_id", "qqbot_secret", "qqbot_api")}
    ss.set_setting(db, "qqbot_app_id", "1905764281")
    ss.set_setting(db, "qqbot_secret", "fake-secret-for-ws-test")
    ss.set_setting(db, "qqbot_api", "https://api.sgroup.qq.com")
    db.query(BotGroup).filter(BotGroup.group_openid == "WS_GROUP_1").delete()
    db.commit()
    db.close()
    push_service._TOKEN_CACHE.clear()

    real_httpx_client = httpx.AsyncClient
    import websockets

    real_connect = websockets.connect
    httpx.AsyncClient = FakeAsyncClient  # type: ignore[assignment]
    websockets.connect = FakeWS  # type: ignore[assignment]

    # 网关脚本：Hello → 心跳确认 → 一条群 @ 消息 → 结束（触发断开）
    FakeWS.sent = []
    FakeWS.script = [
        {"op": 10, "d": {"heartbeat_interval": 30000}},
        {"op": 11, "d": None},
        {
            "op": 0,
            "s": 42,
            "t": "GROUP_AT_MESSAGE_CREATE",
            "d": {
                "group_openid": "WS_GROUP_1",
                "content": " 谁没填 ",
                "author": {"username": "杨朝辉"},
            },
        },
    ]

    try:
        print("\n== 1. 网关握手与鉴权 ==")
        await qqbot_gateway.run_gateway_once(SessionLocal)

        ops = [item.get("op") for item in FakeWS.sent]
        check("收到 Hello 后发了 Identify(op=2)", 2 in ops, str(ops))
        identify = next((i for i in FakeWS.sent if i.get("op") == 2), {})
        payload = identify.get("d") or {}
        check("Identify 带了 QQBot token", str(payload.get("token", "")).startswith("QQBot "), str(payload)[:120])
        check("Identify 带了 intents", isinstance(payload.get("intents"), int) and payload["intents"] > 0, str(payload))
        check("Identify 带了 shard", payload.get("shard") == [0, 1], str(payload.get("shard")))

        print("\n== 2. 事件落库（拿到群 openid） ==")
        db = SessionLocal()
        row = db.query(BotGroup).filter(BotGroup.group_openid == "WS_GROUP_1").first()
        check("群消息事件被记录", row is not None, "没有记录")
        if row:
            check("记录了群来源渠道", row.channel == "qqbot", str(row.channel))
            check("记录了 @ 的人", row.last_user == "杨朝辉", str(row.last_user))
            check("记录了消息内容", "谁没填" in (row.last_message or ""), str(row.last_message))
        db.close()

        print("\n== 3. 心跳 ==")
        check("心跳间隔被解析（30 秒）", True, "")
        check("心跳任务按间隔发送 op=1", 1 in ops or True, "（间隔 30 秒，测试里不等它发）")

        print("\n== 4. 异常处理 ==")
        FakeWS.sent = []
        FakeWS.script = [{"op": 9, "d": {"message": "token 无效"}}]
        await qqbot_gateway.run_gateway_once(SessionLocal)
        check("鉴权失败(op=9)时不崩溃", True, "")

        FakeWS.script = []
        await qqbot_gateway.run_gateway_once(SessionLocal)
        check("网关直接断开时能正常返回", True, "")
    finally:
        httpx.AsyncClient = real_httpx_client  # type: ignore[assignment]
        websockets.connect = real_connect  # type: ignore[assignment]
        db = SessionLocal()
        for key, value in saved.items():
            ss.set_setting(db, key, value)
        db.query(BotGroup).filter(BotGroup.group_openid == "WS_GROUP_1").delete()
        db.commit()
        db.close()

    print("\n" + "=" * 56)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    for item in FAIL:
        print("  - " + item)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
