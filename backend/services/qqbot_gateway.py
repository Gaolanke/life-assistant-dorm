"""QQ 官方机器人的 WebSocket 长连接（不用公网地址、不用域名证书）。

为什么用这个：QQ 开放平台要求「回调地址必须以 https:// 开头」，
我们只有纯 IP，配不了。但官方还支持 **WebSocket 主动连接**：
服务器主动连腾讯，事件通过长连接推下来，完全不需要公网回调地址。

协议（QQ 机器人 API v2）：
    1. GET  {api}/gateway                  → 拿到 wss 地址
    2. 连接后先收 op=10（Hello），里面带 heartbeat_interval
    3. 发 op=2（Identify）：{"op":2,"d":{"token":"QQBot <access_token>","intents":<位掩码>,"shard":[0,1]}}
    4. 每 heartbeat_interval 毫秒发一次 {"op":1,"d":<上次收到的 s 序号>}
    5. op=11 是心跳确认；op=0 是事件（事件名在 t 字段）
"""
from __future__ import annotations

import asyncio
import json
import time
import logging
from typing import Any

from . import settings_service as ss
from .push_service import get_access_token, api_base

log = logging.getLogger("dorm.qqbot.gateway")

# 想收到的事件对应的 intents 位
INTENTS = 1 << 25  # GROUP_AND_C2C_EVENT：群聊 @ 机器人 / 单聊消息

GATEWAY_TASK: asyncio.Task | None = None
_STOP = asyncio.Event()
_CONNECTED_AT: list[float] = [0.0]


def _token_header(token: str) -> dict[str, str]:
    return {"Authorization": f"QQBot {token}"}


def _record_event(db, event_type: str, data: dict) -> None:
    """把事件里的群信息记下来（openid 只能从这里拿到）。"""
    from ..routers.qqbot import remember_group

    group_openid = str(data.get("group_openid") or data.get("channel_id") or "")
    group_no = str(data.get("group_id") or "")
    if not (group_openid or group_no):
        return
    author = data.get("author") or {}
    remember_group(
        db,
        channel="qqbot",
        group_openid=group_openid,
        group_no=group_no,
        name=str(data.get("group_name") or ""),
        user=str(author.get("username") or author.get("id") or data.get("user_id") or ""),
        message=str(data.get("content") or "").strip(),
    )
    log.info("已从 WebSocket 记录 QQ 群：openid=%s（%s）", group_openid, event_type)


async def _handle_event(db, event_type: str, data: dict) -> None:
    _record_event(db, event_type, data)
    content = str(data.get("content") or "").strip()
    group_openid = str(data.get("group_openid") or data.get("channel_id") or "")
    if content and group_openid:
        from ..routers.qqbot import _handle_group_command, seen_event

        # 同一事件可能同时从 WebSocket 和 Webhook 推过来，只处理一次
        event_key = str(data.get("id") or "") or f"{event_type}:{group_openid}:{content}:{data.get('timestamp', '')}"
        if seen_event(event_key):
            return
        try:
            await _handle_group_command(db, group_openid, content, event_type=event_type)
        except Exception:  # noqa: BLE001
            log.exception("处理群消息失败")


async def run_gateway_once(db_factory) -> None:
    """连一次网关，按协议处理到断开为止。"""
    import websockets

    db = db_factory()
    try:
        token, reason = await get_access_token(db)
        if not token:
            log.warning("QQ 机器人 WebSocket 无法连接：%s", reason)
            return
        base = api_base(db)
    finally:
        db.close()

    import httpx

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(f"{base}/gateway", headers=_token_header(token))
    payload = response.json()
    url = str(payload.get("url") or "")
    if not url:
        # 带上人话提示：例如 11700「机器人状态异常」表示该机器人已被停用或删除
        from .push_service import hint_for

        code = payload.get("code") or payload.get("err_code")
        hint = hint_for(code, str(payload.get("message") or ""))
        log.warning("QQ 机器人网关地址获取失败：%s（%s）", str(payload)[:200], hint)
        return

    log.info("QQ 机器人 WebSocket 连接中：%s", url)
    # 关键：关掉 websockets 库自带的保活 ping。
    # 京东云到腾讯的网络有抖动，库的 ping 超时会直接把连接掐断（日志里表现为
    # "keepalive ping timeout"），而 QQ 协议本身有 op=1 心跳，够用了。
    ws = None
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            ws = await websockets.connect(
                url,
                max_size=2**22,
                ping_interval=None,
                open_timeout=60,
                close_timeout=10,
            )
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            log.warning("WebSocket 握手失败（第 %s/3 次）：%s", attempt + 1, exc)
            await asyncio.sleep(2 * (attempt + 1))
    if ws is None:
        raise last_error or RuntimeError("WebSocket 连接失败")

    async with ws:
        _CONNECTED_AT[0] = time.time()
        log.info("QQ 机器人长连接已建立 ✅")
        sequence: int | None = None
        heartbeat_interval = 30.0
        heartbeat_task: asyncio.Task | None = None

        async def heartbeat() -> None:
            while True:
                await asyncio.sleep(heartbeat_interval)
                await ws.send(json.dumps({"op": 1, "d": sequence}))

        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except Exception:  # noqa: BLE001
                    continue
                op = msg.get("op")
                if msg.get("s") is not None:
                    sequence = msg.get("s")

                if op == 10:  # Hello
                    data = msg.get("d") or {}
                    heartbeat_interval = float(data.get("heartbeat_interval") or 30000) / 1000.0
                    await ws.send(json.dumps({
                        "op": 2,
                        "d": {"token": f"QQBot {token}", "intents": INTENTS, "shard": [0, 1]},
                    }))
                    if heartbeat_task is None:
                        heartbeat_task = asyncio.create_task(heartbeat())
                elif op == 11:  # 心跳确认
                    continue
                elif op == 0:  # 事件
                    event_type = str(msg.get("t") or "")
                    data = msg.get("d") or {}
                    session = db_factory()
                    try:
                        await _handle_event(session, event_type, data)
                    finally:
                        session.close()
                elif op in (7, 9):  # 要求重连 / 鉴权失败
                    log.warning("网关要求重连或鉴权失败：op=%s %s", op, str(msg.get("d"))[:120])
                    break
        finally:
            if heartbeat_task is not None:
                heartbeat_task.cancel()


async def gateway_loop(db_factory, *, retry_seconds: int = 15) -> None:
    """常驻任务：断了就自动重连。"""
    from . import settings_service as ss_local

    # 关键：delay 必须在循环外初始化。
    # 否则首次连接就失败时，异常分支里引用 delay 会抛 UnboundLocalError，
    # 整个重连任务会静默崩溃（表现为 gateway_running=False）。
    delay = retry_seconds

    while not _STOP.is_set():
        session = db_factory()
        try:
            enabled = ss_local.get_bool(session, "qqbot_enabled", False) and ss_local.get_bool(
                session, "qqbot_ws_enabled", True
            )
            has_cred = bool(
                ss_local.get_setting(session, "qqbot_app_id").strip()
                and ss_local.get_setting(session, "qqbot_secret").strip()
            )
        finally:
            session.close()

        if not (enabled and has_cred):
            await asyncio.sleep(20)
            continue

        try:
            await run_gateway_once(db_factory)
            delay = retry_seconds  # 正常断开：回到最短重连间隔
            log.info("QQ 机器人 WebSocket 已断开，%s 秒后重连", delay)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            text = str(exc) or type(exc).__name__
            online = "keepalive ping timeout" in text or "handshake" in text
            if online:
                log.warning("QQ 机器人长连接掉线（网络抖动）：%s；%s 秒后重连", text, delay)
            else:
                log.warning("QQ 机器人 WebSocket 出错：%s；%s 秒后重连", text, delay)
        try:
            await asyncio.wait_for(_STOP.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass
        # 连续失败就退避到最多 2 分钟，避免疯狂重试
        delay = min(int(delay * 1.5) + 1, 120)
        if _CONNECTED_AT[0] and time.time() - _CONNECTED_AT[0] > 60:
            delay = retry_seconds  # 上一轮连接稳定过，就用最短间隔重连



def start_gateway(db_factory) -> asyncio.Task | None:
    """在服务启动时调用，起一个后台任务。"""
    global GATEWAY_TASK
    if GATEWAY_TASK is not None and not GATEWAY_TASK.done():
        return GATEWAY_TASK
    _STOP.clear()
    GATEWAY_TASK = asyncio.create_task(gateway_loop(db_factory))
    log.info("QQ 机器人 WebSocket 后台任务已启动")
    return GATEWAY_TASK


async def stop_gateway() -> None:
    global GATEWAY_TASK
    _STOP.set()
    if GATEWAY_TASK is not None:
        GATEWAY_TASK.cancel()
        try:
            await GATEWAY_TASK
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        GATEWAY_TASK = None


async def restart_gateway(db_factory) -> bool:
    """换机器人凭证后立刻重连：先停掉旧的长连接，再用新凭证重连。

    这样用户在「系统配置 → QQ 官方机器人」改完 AppID / AppSecret 保存后，
    不用重启服务就能用新机器人连上。
    """
    try:
        await stop_gateway()
    except Exception:  # noqa: BLE001
        pass
    _STOP.clear()
    task = start_gateway(db_factory)
    log.info("QQ 机器人长连接已按新凭证重启")
    return task is not None


def reconnect_soon(db_factory) -> None:
    """在同步接口里触发重连（丢到事件循环里执行，不阻塞请求）。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(restart_gateway(db_factory))
