"""通知通道：QQ 官方机器人（QQ 开放平台）。

QQ 官方机器人是**腾讯官方**的机器人，不需要挂 QQ 客户端、不用小号、不会被风控封号，
服务器上的定时脚本直接调 HTTP 就能发群消息。

接口（QQ 开放平台 API v2）：
    取凭证  POST https://bots.qq.com/app/getAppAccessToken
            {"appId": "...", "clientSecret": "..."} -> {"access_token": "...", "expires_in": "7200"}
    发群消息 POST https://api.sgroup.qq.com/v2/groups/{group_openid}/messages
            Header: Authorization: QQBot <access_token>
            {"content": "文字", "msg_type": 0, "msg_id": "可选：回复某条消息"}

注意：官方机器人**主动推送有配额**，多数场景是「用户 @ 机器人后 5 分钟内可回复」。
配额不足或未获授权时接口会返回错误码，程序会把失败原因记到推送日志里。
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..services import settings_service as ss

log = logging.getLogger("dorm.qqbot.push")

TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"

# 缓存 access_token（按 appid 维度），避免每次发消息都去取一遍
_TOKEN_CACHE: dict[str, tuple[str, float]] = {}
_TOKEN_LOCK = asyncio.Lock()

# 常见错误码 → 人话
ERROR_HINTS = {
    11244: "机器人未加入这个群，或群主还没启用机器人",
    11245: "该群没有开通主动消息，需要群主在群里启用机器人",
    11293: "机器人不在这个群里（换群后群 openid 会变）：先把机器人拉进新群，"
           "在群里 @ 它一次，再到「系统配置 → QQ 官方机器人」刷新群列表并填入新群",
    11700: "机器人状态异常：该机器人可能已被停用或删除。请在 QQ 开放平台确认机器人状态，"
           "并在「系统配置 → QQ 官方机器人」里换成有效机器人的 AppID / AppSecret",
    22009: "发送频率超限，稍后再试",
    304003: "参数不对（群 openid 可能是错的）",
    304023: "机器人被限制发言",
    306005: "频道不存在或机器人不在频道里",
    40034004: "主动消息额度已用完（官方限制，无法绕过）",
    40034105: "该群没有开通机器人主动消息权限：让群主在群里启用/授权机器人；"
              "或者改成在群里 @ 机器人，它会用「被动回复」把内容发出来（被动回复不受这个限制）",
}


def hint_for(code: Any, message: str = "") -> str:
    try:
        return ERROR_HINTS.get(int(code), "") or message or f"错误码 {code}"
    except (TypeError, ValueError):
        return message or f"错误码 {code}"


def _split(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").replace("，", ",").split(",") if part.strip()]


def mask_secret(value: str) -> str:
    text = str(value or "")
    if len(text) <= 6:
        return "*" * len(text)
    return f"{text[:4]}{'*' * (len(text) - 8)}{text[-4:]}"


def is_success(status_code: int, data: dict) -> bool:
    """判断发消息是否成功。

    注意：QQ 官方接口出错时也常常返回 HTTP 200，正文里带 code/err_code，
    所以不能只看状态码——必须同时没有错误码，且有消息 id。
    """
    if not isinstance(data, dict):
        return False
    if data.get("code") or data.get("err_code"):
        return False
    if data.get("id") or data.get("msg_id") or data.get("message_id"):
        return True
    return status_code in (200, 201) and "message" not in data


# --------------------------------------------------------------------------
# QQ 官方机器人
# --------------------------------------------------------------------------
async def get_access_token(
    db: Session, *, force: bool = False, retries: int = 3, timeout: float = 20.0
) -> tuple[str, str]:
    """取 QQ 机器人 access_token。返回 (token, 错误说明)。"""
    app_id = ss.get_setting(db, "qqbot_app_id").strip()
    secret = ss.get_setting(db, "qqbot_secret").strip()
    if not app_id or not secret:
        return "", "还没有填写 AppID / AppSecret（去「系统配置 → QQ 官方机器人」填）"

    cached = _TOKEN_CACHE.get(app_id)
    if cached and not force and cached[1] - time.time() > 120:
        return cached[0], ""

    async with _TOKEN_LOCK:
        cached = _TOKEN_CACHE.get(app_id)
        if cached and not force and cached[1] - time.time() > 120:
            return cached[0], ""
        try:
            data = {}
            last_error = ""
            attempts_total = max(1, retries)
            for attempt in range(attempts_total):
                try:
                    async with httpx.AsyncClient(
                        timeout=httpx.Timeout(timeout, connect=min(10.0, timeout))
                    ) as client:
                        response = await client.post(
                            TOKEN_URL, json={"appId": app_id, "clientSecret": secret}
                        )
                    data = response.json()
                    break
                except httpx.ConnectError as exc:
                    last_error = f"连不上 bots.qq.com（{exc}）"
                except httpx.TimeoutException:
                    last_error = "连接 bots.qq.com 超时（这台服务器到腾讯的网络不稳）"
                except Exception as exc:  # noqa: BLE001
                    last_error = f"取 access_token 失败：{exc}"
                if attempt < attempts_total - 1:
                    await asyncio.sleep(1.5 * (attempt + 1))
            else:
                # 网络抖到取不到新 token 时，只要缓存还没过期就先用着，
                # 不要因为一次握手失败就把长连接搞断
                cached = _TOKEN_CACHE.get(app_id)
                if cached and cached[1] - time.time() > 60:
                    log.warning("取 token 失败（%s），复用缓存里的 token", last_error)
                    return cached[0], ""
                return "", last_error

            token = str(data.get("access_token") or "")
            if not token:
                return "", last_error or f"官方接口没返回 access_token：{str(data)[:200]}"
            try:
                expires = int(data.get("expires_in") or 7200)
            except (TypeError, ValueError):
                expires = 7200
            _TOKEN_CACHE[app_id] = (token, time.time() + expires)
            return token, ""
        except Exception as exc:  # noqa: BLE001
            return "", f"取 access_token 失败：{exc}"


def api_base(db: Session) -> str:
    sandbox = ss.get_bool(db, "qqbot_sandbox", False)
    if sandbox:
        return "https://sandbox.api.sgroup.qq.com"
    return (ss.get_setting(db, "qqbot_api").strip() or "https://api.sgroup.qq.com").rstrip("/")


async def send_group_message(
    db: Session,
    group_openid: str,
    content: str,
    *,
    msg_id: str = "",
    msg_type: int | None = None,
    attempts: int = 4,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """给一个 QQ 群发消息（官方机器人接口）。

    注意：这台服务器到腾讯的网络丢包严重（实测 5 次里 3 次 30 秒超时，
    成功的请求也要 5~10 秒），所以这里默认重试 4 次、超时放宽到 30 秒。
    """
    group = str(group_openid or "").strip()
    if not group:
        return {"ok": False, "channel": "qqbot", "message": "没有配置 QQ 群 openid"}

    token, reason = await get_access_token(db)
    if not token:
        return {"ok": False, "channel": "qqbot", "message": reason}

    if msg_type is None:
        try:
            msg_type = int(ss.get_setting(db, "qqbot_msg_type", "0") or 0)
        except ValueError:
            msg_type = 0
    payload: dict[str, Any] = {"content": content, "msg_type": msg_type}
    if msg_id:
        payload["msg_id"] = msg_id

    url = f"{api_base(db)}/v2/groups/{group}/messages"
    headers = {"Authorization": f"QQBot {token}", "Content-Type": "application/json"}

    last: dict[str, Any] = {"ok": False, "channel": "qqbot", "message": "未发出"}
    for attempt in range(1, max(1, attempts) + 1):
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout, connect=min(15.0, timeout))
            ) as client:
                response = await client.post(url, json=payload, headers=headers)
            try:
                data = response.json()
            except Exception:  # noqa: BLE001
                data = {"raw": response.text[:200]}
        except httpx.TimeoutException:
            last = {"ok": False, "channel": "qqbot", "message": "发送超时（网络到腾讯不稳）", "attempt": attempt}
            log.warning("发群超时（第 %s/%s 次），稍后重试", attempt, attempts)
            await asyncio.sleep(1.5 * attempt)
            continue
        except Exception as exc:  # noqa: BLE001
            last = {"ok": False, "channel": "qqbot", "message": f"发送失败：{exc}", "attempt": attempt}
            await asyncio.sleep(1.5 * attempt)
            continue

        if is_success(response.status_code, data):
            return {"ok": True, "channel": "qqbot", "message": "已发到 QQ 群", "data": data, "attempt": attempt}

        code = data.get("code") or data.get("err_code") or response.status_code
        detail = hint_for(code, str(data.get("message") or ""))

        if response.status_code == 401:  # token 过期，刷新后重试
            token, _ = await get_access_token(db, force=True)
            if token:
                headers["Authorization"] = f"QQBot {token}"
                last = {"ok": False, "channel": "qqbot", "message": detail, "code": code, "attempt": attempt}
                await asyncio.sleep(1)
                continue

        last = {"ok": False, "channel": "qqbot", "message": detail, "code": code, "data": data, "attempt": attempt}
        # 配额 / 权限类错误重试也没用，直接返回
        if str(code) in {"40034004", "40034105", "11244", "11245", "304023"}:
            return last
        log.warning("发群失败（第 %s/%s 次）：%s", attempt, attempts, detail)
        await asyncio.sleep(1.5 * attempt)

    return last



async def check_qqbot(db: Session) -> dict[str, Any]:
    """连接自检：能不能拿到 access_token（这是官方机器人配置正确的标志）。"""
    if not ss.get_bool(db, "qqbot_enabled", False):
        return {"ok": False, "message": "QQ 官方机器人推送还没启用（开关设为 1 才会发）"}
    token, reason = await get_access_token(db, force=True, retries=1, timeout=8.0)
    if not token:
        return {"ok": False, "message": reason}
    groups = _split(ss.get_setting(db, "qqbot_groups"))
    return {
        "ok": True,
        "message": f"官方机器人凭证正常（token 已获取，有效期约 2 小时，会自动续）"
        + (f"，已配置 {len(groups)} 个群" if groups else "，但还没填群 openid"),
        "groups": groups,
    }


# --------------------------------------------------------------------------
# 统一投递：QQ 官方机器人
# --------------------------------------------------------------------------
async def deliver_notification(
    db: Session,
    *,
    title: str,
    content: str,
    scene: str = "daily_report",
    group_openid: str = "",
    attempts: int = 4,
    timeout: float = 30.0,
    quick: bool = False,
) -> dict[str, Any]:
    """把一条通知投递到 QQ 官方机器人。

    返回 {"ok": bool, "channel": "qqbot"/"none", "message": str, "results": [...]}
    """
    results: list[dict[str, Any]] = []

    # quick（检测/测试按钮）：整体限时，超时就返回"网络不稳"，不让用户干等
    if quick:
        try:
            return await asyncio.wait_for(
                _deliver_impl(
                    db,
                    title=title,
                    content=content,
                    scene=scene,
                    group_openid=group_openid,
                    attempts=attempts,
                    timeout=timeout,
                ),
                timeout=max(8.0, timeout * max(1, attempts) + 5),
            )
        except asyncio.TimeoutError:
            return {
                "ok": False,
                "channel": "none",
                "message": "检测超时：这台服务器到腾讯的网络不稳，稍后再试或直接发一次试试",
                "results": results,
            }

    return await _deliver_impl(
        db,
        title=title,
        content=content,
        scene=scene,
        group_openid=group_openid,
        attempts=attempts,
        timeout=timeout,
    )


async def _deliver_impl(
    db: Session,
    *,
    title: str,
    content: str,
    scene: str,
    group_openid: str,
    attempts: int,
    timeout: float,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []

    groups = _split(group_openid) or _split(ss.get_setting(db, "qqbot_groups"))
    qq_ok = False
    if ss.get_bool(db, "qqbot_enabled", False) and groups:
        for group in groups:
            try:
                sent = await send_group_message(
                    db, group, content, attempts=attempts, timeout=timeout
                )
            except Exception as exc:  # noqa: BLE001
                sent = {"ok": False, "channel": "qqbot", "message": f"发送异常：{exc}"}
            sent["group"] = group
            results.append(sent)
            qq_ok = qq_ok or bool(sent.get("ok"))
    elif ss.get_bool(db, "qqbot_enabled", False) and not groups:
        results.append({"ok": False, "channel": "qqbot", "message": "启用了官方机器人但没填群 openid"})

    if qq_ok:
        return {"ok": True, "channel": "qqbot", "message": "已发到 QQ 群", "results": results}

    reason = next((r.get("message") for r in results if not r.get("ok")), "没有可用的通知通道")
    return {"ok": False, "channel": "none", "message": reason, "results": results}
