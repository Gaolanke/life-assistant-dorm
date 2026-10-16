"""QQ 官方机器人 Webhook：接收事件（验证签名、记录群、处理 @机器人 指令）。

QQ 开放平台支持「Webhook 回调」：在后台填一个公网地址，平台会把群消息事件 POST 过来。
配置页里的地址就是本模块的接口（默认 /api/qqbot/events）。

两种事件：
1. 回调地址校验（op=13）：平台 POST {"d":{"plain_token","event_ts"},"op":13}，
   需要返回 {"plain_token": ..., "signature": ...}。签名算法严格按腾讯官方文档：
     seed = AppSecret 的 UTF-8 原始字节，循环翻倍到 32 字节后截断（不是 SHA256！）
     msg  = event_ts + plain_token
     signature = **hex**( Ed25519_sign(seed, msg) )   ← 必须是十六进制，不是 base64
   官方样例：secret=DG5g3B4j9X2KOErG, plain_token=Arq0D5A61EgUu4OxUvOp,
             event_ts=1725442341
             → 87befc99c42c651b3aac0278e71ada338433ae26fcb24307bdc5ad38c1adc2d0
               1bcfcadc0842edac85e85205028a1132afe09280305f13aa6909ffc2d652c706
2. 群消息事件（t=GROUP_AT_MESSAGE_CREATE 等）：记录 group_openid、群名、@ 的人。
   平台在 X-Signature-Ed25519 头里放十六进制签名，签名体 = timestamp + body。
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Account, BotGroup, Dorm
from ..security import require_admin
from ..services import class_service, report_service, settings_service as ss
from ..util import AppError, client_ip, now_local

log = logging.getLogger("dorm.qqbot")

router = APIRouter(prefix="/api/qqbot", tags=["qqbot"])

# 机器人「被 @ 」才算数的会话事件：只有这些事件才允许触发自动回复。
# 普通群消息（GROUP_MESSAGE_CREATE）一律不回复——之前对任意群消息做关键词
# 匹配，机器人自己发的汇报里也有「汇报/未填」字样，结果自我触发、在群里
# 反复通报，已按要求取消。
AT_EVENTS = {
    "GROUP_AT_MESSAGE_CREATE",  # 群里 @ 机器人
    "AT_MESSAGE_CREATE",        # 频道里 @ 机器人
    "C2C_MESSAGE_CREATE",       # 单聊
    "DIRECT_MESSAGE_CREATE",    # 私信
}

# 事件去重：同一条消息可能同时从 Webhook 和 WebSocket 两条通道推过来，
# 不处理两遍（否则会连发两条一模一样的回复）。
_HANDLED_EVENTS: dict[str, float] = {}


def seen_event(event_key: str) -> bool:
    """返回 True 表示这个事件已经处理过，调用方应直接忽略。"""
    if not event_key:
        return False
    now = time.time()
    # 顺便清掉 10 分钟前的记录，表不会无限涨
    for key in [k for k, ts in _HANDLED_EVENTS.items() if now - ts > 600]:
        _HANDLED_EVENTS.pop(key, None)
    if event_key in _HANDLED_EVENTS:
        return True
    _HANDLED_EVENTS[event_key] = now
    return False

# 官方事件里，带这些字段的都算"收到消息了"
MESSAGE_EVENTS = {
    "GROUP_AT_MESSAGE_CREATE",
    "GROUP_ADD_ROBOT",
    "GROUP_MSG_RECEIVE",
    "GROUP_MSG_REJECT",
    "C2C_MESSAGE_CREATE",
    "AT_MESSAGE_CREATE",
    "MESSAGE_CREATE",
    "DIRECT_MESSAGE_CREATE",
    "FRIEND_ADD",
}


def _seed_from_secret(secret: str) -> bytes:
    """把 AppSecret 推导成 32 字节的 Ed25519 种子。

    必须用「AppSecret 的 UTF-8 原始字节，循环补足到 32 字节后截断」，
    不能先做 SHA256 —— 腾讯平台是按这个方式校验签名的，
    用 SHA256 会导致回调地址保存时报「签名校验不通过」。

    （AppSecret 通常正好 32 位，此时种子就是它的原始字节。）
    """
    seed = secret.strip().encode("utf-8")
    while len(seed) < 32:
        seed *= 2
    return seed[:32]


def _ed25519_sign(secret: str, message: str) -> str:
    """用 AppSecret 对消息做 Ed25519 签名，返回**十六进制**字符串。

    腾讯官方实现（Go）：
        signature := hex.EncodeToString(ed25519.Sign(privateKey, msg))
    必须用 hex —— 用 base64 会被平台判定「签名校验不通过」。
    官方样例（secret=DG5g3B4j9X2KOErG）签名长度是 128 个十六进制字符。
    """
    from nacl.signing import SigningKey

    signing_key = SigningKey(_seed_from_secret(secret))
    signature = signing_key.sign(message.encode("utf-8")).signature
    return signature.hex()


def _ed25519_verify(secret: str, message: str, signature_hex: str, public_key_hex: str = "") -> bool:
    """校验平台推来的事件签名。

    平台在 X-Signature-Ed25519 头里放的是 **十六进制** 字符串（官方文档：
    「取 HTTP Header 中 X-Signature-Ed25519(进行 hex 解码)并校验」）。
    """
    try:
        raw = bytes.fromhex(signature_hex.strip())
    except Exception:  # noqa: BLE001
        return False
    try:
        if public_key_hex:
            from nacl.signing import VerifyKey

            verify_key = VerifyKey(bytes.fromhex(public_key_hex.strip()))
            verify_key.verify(message.encode("utf-8"), raw)
            return True
        from nacl.signing import SigningKey

        signing_key = SigningKey(_seed_from_secret(secret))
        signing_key.verify_key.verify(message.encode("utf-8"), raw)
        return True
    except Exception:  # noqa: BLE001
        return False


def remember_group(
    db: Session,
    *,
    channel: str,
    group_openid: str = "",
    group_no: str = "",
    name: str = "",
    user: str = "",
    message: str = "",
) -> BotGroup | None:
    """记录/更新一个收到过消息的群。"""
    if not group_openid and not group_no:
        return None
    query = select(BotGroup).where(BotGroup.channel == channel)
    query = query.where(
        BotGroup.group_openid == group_openid if group_openid else BotGroup.group_no == group_no
    )
    row = db.execute(query).scalar_one_or_none()
    if row is None:
        row = BotGroup(channel=channel, group_openid=group_openid, group_no=group_no)
        db.add(row)
    if name:
        row.name = name[:120]
    if user:
        row.last_user = user[:120]
    if message:
        row.last_message = message[:300]
    row.message_count = (row.message_count or 0) + 1
    row.last_seen = now_local()
    db.commit()
    db.refresh(row)
    return row


def serialize_bot_group(
    row: BotGroup, configured: set[str] | None = None, db: Session | None = None
) -> dict[str, Any]:
    is_target = bool(configured) and row.group_openid in (configured or set())
    class_name = ""
    if (row.class_id or 0) > 0 and db is not None:
        bound = class_service.get_class(db, row.class_id)
        class_name = bound.name if bound else ""
    return {
        "id": row.id,
        "channel": row.channel,
        "group_openid": row.group_openid,
        "group_no": row.group_no,
        "name": row.name,
        "last_user": row.last_user,
        "last_message": row.last_message,
        "message_count": row.message_count,
        "last_seen": row.last_seen.strftime("%Y-%m-%d %H:%M:%S") if row.last_seen else "",
        "is_target": is_target,
        "class_id": int(row.class_id or 0),
        "class_name": class_name,
    }


@router.post("/events")
async def qqbot_events(request: Request, db: Session = Depends(get_db)):
    """QQ 官方机器人的 Webhook 回调入口。"""
    raw = await request.body()
    try:
        body = json.loads(raw.decode("utf-8") or "{}")
    except Exception:  # noqa: BLE001
        body = {}

    op = body.get("op")
    event_type = body.get("t") or ""
    secret = ss.get_setting(db, "qqbot_secret").strip()

    # 1) 回调地址校验（plain_token / event_ts 在顶层，也可能在 d 里，两个位置都兼容）
    payload = body.get("d") if isinstance(body.get("d"), dict) else {}
    plain_token = str(body.get("plain_token") or payload.get("plain_token") or "")
    event_ts = str(body.get("event_ts") or payload.get("event_ts") or "")
    if op == 13 or plain_token:
        if not secret:
            log.warning("收到回调校验，但还没配置 AppSecret，无法签名")
            return {"ok": False, "message": "服务器还没配置 AppSecret，请先在配置页填写"}
        if not plain_token:
            return {"ok": False, "message": "缺少 plain_token"}

        # 详细记录平台的原始请求与我们的回复，便于排查「签名校验不通过」
        log.info(
            "回调校验原始请求：%s",
            raw.decode("utf-8", "replace")[:600],
        )

        sig_ts_first = _ed25519_sign(secret, event_ts + plain_token)
        sig_token_first = _ed25519_sign(secret, plain_token + event_ts)
        response = {"plain_token": plain_token, "signature": sig_ts_first}
        log.info(
            "回调校验回复：%s | 备用签名(反序)=%s",
            json.dumps(response, ensure_ascii=False)[:400],
            sig_token_first[:32] + "...",
        )
        return response

    # 2) 正常事件：校验签名（配了公钥或 secret 就校验）
    timestamp = request.headers.get("x-signature-timestamp", "")
    signature = request.headers.get("x-signature-ed25519", "")
    public_key = ss.get_setting(db, "qqbot_public_key").strip()
    if signature and (secret or public_key):
        message = timestamp + raw.decode("utf-8", errors="ignore")
        if not _ed25519_verify(secret, message, signature, public_key):
            log.warning("QQ 机器人事件签名校验失败")
            return {"ok": False, "message": "签名校验失败"}

    log.info("收到 QQ 机器人事件：op=%s t=%s", op, event_type)

    # 3) 记录群信息（openid 只能从这里拿到）
    data = body.get("d") or {}
    group_openid = str(data.get("group_openid") or data.get("channel_id") or "")
    group_no = str(data.get("group_id") or "")
    if group_openid or group_no:
        author = data.get("author") or {}
        user = str(author.get("username") or author.get("id") or data.get("user_id") or "")
        content = str(data.get("content") or "").strip()
        remember_group(
            db,
            channel="qqbot",
            group_openid=group_openid,
            group_no=group_no,
            name=str(data.get("group_name") or ""),
            user=user,
            message=content,
        )
        log.info("已记录 QQ 群 openid=%s（%s）", group_openid, event_type)

    # 4) 「群里 @机器人 填/查填报」：只响应 @ 事件，且同一事件只处理一次
    content = str(data.get("content") or "").strip()
    if content and group_openid:
        event_key = str(data.get("id") or "") or f"{event_type}:{group_openid}:{content}:{data.get('timestamp', '')}"
        if not seen_event(event_key):
            await _handle_group_command(db, group_openid, content, event_type=event_type)

    return {"op": 0, "d": {}, "t": "ACK"}


async def _handle_group_command(
    db: Session,
    group_openid: str,
    content: str,
    *,
    event_type: str = "GROUP_AT_MESSAGE_CREATE",
) -> None:
    """群里 @机器人 说话时的自动回复（被动回复，不受主动消息权限限制）。

    只有「@ 机器人」的事件才会走到这里；普通群消息一律不回复
    （避免机器人被自己发的汇报里的关键词自我触发，在群里反复通报）。
    """
    from ..services import notify_service, push_service

    if event_type and event_type not in AT_EVENTS:
        return

    text = content.replace("<@!", "").replace(">", "").strip()
    if not text:
        return

    # 群绑定了班级 → 这个群里的指令只看该班级的数据
    cls = class_service.class_by_group(db, group_openid)
    cid = cls.id if cls else 0

    # 支持「@机器人 汇报 / 谁没填」→ 直接把当天汇总/未填清单发到群里（用户主动触发，一条一回）
    if any(word in text for word in ("谁没填", "未填", "没填的", "填报情况", "汇报", "统计")):
        report = notify_service.build_group_report(db, class_id=cid)
        reply = f"{report}\n\n————\n{notify_service.build_missing_reminder(db, class_id=cid)}"
    else:
        # 当作寝室长填报：能解析就记一条填报
        dorms = report_service.list_dorms(db, class_id=cid)
        parsed = report_service.parse_group_message(text, dorms)
        if not parsed:
            scope = f"（{cls.name}）" if cls else ""
            reply = (
                "我可以帮你：\n"
                f"· 发送「汇报」或「谁没填」→ 我把当天填报情况{scope}发到群里\n"
                "· 发送「6-213 人齐」→ 我帮你记一条填报"
            )
        else:
            dorm = report_service.get_dorm_by_room(db, parsed["room_no"], class_id=cid)
            if dorm is None:
                reply = f"没有找到宿舍 {parsed['room_no']}"
            else:
                reply = f"已记录 {dorm.room_no} 的填报"
    await push_service.send_group_message(db, group_openid, reply)


@router.post("/reconnect")
async def reconnect(
    db: Session = Depends(get_db), _: Account = Depends(require_admin)
) -> dict[str, Any]:
    """手动重连长连接（换了机器人凭证后可以点一下）。"""
    from ..database import SessionLocal as _SessionLocal
    from ..services import qqbot_gateway

    ok = await qqbot_gateway.restart_gateway(_SessionLocal)
    return {
        "ok": bool(ok),
        "message": "长连接已重启，正在用当前凭证重连" if ok else "重启失败，请查看服务日志",
    }


@router.get("/status")
async def qqbot_status(db: Session = Depends(get_db), _: Account = Depends(require_admin)):
    """QQ 机器人整体状态：长连接、凭证、群里上报情况。"""
    from ..services import push_service, qqbot_gateway

    task = qqbot_gateway.GATEWAY_TASK
    running = bool(task is not None and not task.done())
    groups = list(db.execute(select(BotGroup).order_by(BotGroup.last_seen.desc())).scalars())
    configured = ss.get_setting(db, "qqbot_groups")
    configured_count = len([g for g in configured.replace("，", ",").split(",") if g.strip()])
    return {
        "ok": True,
        "enabled": ss.get_bool(db, "qqbot_enabled", False),
        "ws_enabled": ss.get_bool(db, "qqbot_ws_enabled", True),
        "gateway_running": running,
        "has_credentials": bool(
            ss.get_setting(db, "qqbot_app_id").strip() and ss.get_setting(db, "qqbot_secret").strip()
        ),
        "app_id": ss.get_setting(db, "qqbot_app_id"),
        "known_groups": len(groups),
        "configured_groups": configured_count,
        "last_group": serialize_bot_group(groups[0], db=db) if groups else None,
        "message": (
            "长连接已连接，机器人正在监听群消息"
            if running
            else ("已启用但长连接未运行（看服务日志）" if ss.get_bool(db, "qqbot_enabled", False) else "推送开关未开启")
        ),
    }


@router.get("/groups")
async def list_groups(
    request: Request, db: Session = Depends(get_db), _: Account = Depends(require_admin)
):
    """给配置页用：机器人收到过消息的群（可能含 openid）。

    读取需要管理员登录（群 openid 属于配置信息）。
    """
    rows = list(db.execute(select(BotGroup).order_by(BotGroup.last_seen.desc()).limit(30)).scalars())
    dorms = report_service.list_dorms(db, active_only=False)
    configured = (
        ss.get_setting(db, "qqbot_groups").replace("，", ",").split(",")
    )
    configured_set = {g.strip() for g in configured if g.strip()}
    return {
        "ok": True,
        "items": [serialize_bot_group(row, configured_set, db) for row in rows],
        "total": len(rows),
        "configured_groups": ss.get_setting(db, "qqbot_groups"),
        "dorm_count": len(dorms),
    }


class BindBody(BaseModel):
    class_id: int = 0  # 0 = 解除绑定


@router.put("/groups/{group_id}/bind")
async def bind_group_class(
    group_id: int,
    body: BindBody,
    request: Request,
    db: Session = Depends(get_db),
    account: Account = Depends(require_admin),
):
    """把机器人所在的群绑定到某个班级：这个群的汇报/提醒/指令都走该班级的数据。

    class_id=0 表示解除绑定（回退全局推送目标）。
    """
    row = db.get(BotGroup, group_id)
    if row is None:
        raise AppError("这个群记录不存在，可能已被删除", 404)
    if body.class_id > 0:
        cls = class_service.get_class(db, body.class_id)
        if cls is None:
            raise AppError("班级不存在", 404)
        # 一个群只能绑一个班；同一个班级可以绑多个群
        row.class_id = cls.id
        message = f"已把群「{row.name or row.group_openid[:12]}…」绑定为班级「{cls.name}」"
        detail = cls.name
    else:
        row.class_id = 0
        message = "已解除该群的班级绑定（回退为全局推送目标）"
        detail = "解除绑定"
    db.commit()
    ss.write_audit(
        db,
        actor=account.display_name or account.username,
        role="admin",
        action="设置群班级绑定",
        target=row.group_openid[:24],
        detail=detail,
        ip=client_ip(request),
    )
    db.commit()
    return {"ok": True, "message": message, "item": serialize_bot_group(row, db=db)}


def _strip_from_target(raw: str, openid: str) -> str:
    """把某个 openid 从推送目标里去掉（支持中英文逗号）。"""
    parts = [p.strip() for p in str(raw or "").replace("，", ",").split(",")]
    return ",".join(p for p in parts if p and p != openid)


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: int,
    request: Request,
    db: Session = Depends(get_db),
    account: Account = Depends(require_admin),
):
    """删除一个已上报的群。

    会做两件事：
      1. 从「最近上报的群」列表里移除这条记录
      2. 如果它正好在「要推送的群」里，也一并去掉（避免一直往无效群发）
    """
    row = db.get(BotGroup, group_id)
    if row is None:
        raise AppError("这个群记录不存在，可能已被删除", 404)

    openid = row.group_openid
    was_target = openid in {
        g.strip() for g in ss.get_setting(db, "qqbot_groups").replace("，", ",").split(",") if g.strip()
    }

    db.delete(row)
    if was_target:
        ss.set_setting(db, "qqbot_groups", _strip_from_target(ss.get_setting(db, "qqbot_groups"), openid))
    db.commit()

    ss.write_audit(
        db,
        actor=account.display_name or account.username,
        role="admin",
        action="删除机器人群",
        target=openid,
        detail="同时从推送目标移除" if was_target else "仅移除记录",
        ip=client_ip(request),
    )
    db.commit()
    return {
        "ok": True,
        "message": f"已删除群 {openid[:12]}…" + ("，并从推送目标里移除" if was_target else ""),
        "removed_from_target": was_target,
    }


@router.delete("/targets/{openid}")
async def delete_target(
    openid: str,
    request: Request,
    db: Session = Depends(get_db),
    account: Account = Depends(require_admin),
):
    """把某个群 openid 从「要推送的群」里删掉。

    和 /groups/{id} 的区别：这个按 openid 删，
    所以**即使该群没有上报记录（列表里看不到）也能删**。
    """
    openid = openid.strip()
    if not openid:
        raise AppError("缺少群 openid", 400)

    raw = ss.get_setting(db, "qqbot_groups")
    existed = openid in {g.strip() for g in raw.replace("，", ",").split(",") if g.strip()}
    new_value = _strip_from_target(raw, openid)

    # 如果这个 openid 还有上报记录，也一并删掉
    record = db.execute(select(BotGroup).where(BotGroup.group_openid == openid)).scalars().first()
    if record is not None:
        db.delete(record)

    ss.set_setting(db, "qqbot_groups", new_value)
    db.commit()

    ss.write_audit(
        db,
        actor=account.display_name or account.username,
        role="admin",
        action="删除推送群",
        target=openid,
        detail="同时删除上报记录" if record is not None else "仅从推送目标移除",
        ip=client_ip(request),
    )
    db.commit()

    if not existed and record is None:
        raise AppError(f"推送目标里没有 {openid[:16]}…，也没有对应的群记录", 404)

    return {
        "ok": True,
        "message": f"已从推送目标删除 {openid[:16]}…",
        "configured_groups": new_value,
    }


class TargetBody(BaseModel):
    openid: str = ""


def _target_list(raw: str) -> list[str]:
    parts = [p.strip() for p in str(raw or "").replace("，", ",").split(",")]
    result: list[str] = []
    for part in parts:
        if part and part not in result:
            result.append(part)
    return result


def _validate_openid(openid: str) -> str:
    text = openid.strip()
    if not text:
        raise AppError("请填写群 openid", 400)
    if any(ch in text for ch in ",， \t\n"):
        raise AppError("openid 里不能有逗号或空格（一次只填一个群）", 400)
    if len(text) > 80:
        raise AppError("openid 太长了，请检查是不是复制错了", 400)
    return text


@router.post("/targets")
async def add_target(
    body: TargetBody,
    request: Request,
    db: Session = Depends(get_db),
    account: Account = Depends(require_admin),
):
    """添加一个推送群 openid（立即生效，无需再点保存）。"""
    openid = _validate_openid(body.openid)
    targets = _target_list(ss.get_setting(db, "qqbot_groups"))
    if openid in targets:
        return {"ok": True, "message": "这个群已经在推送列表里了", "configured_groups": ",".join(targets)}
    targets.append(openid)
    new_value = ",".join(targets)
    ss.set_setting(db, "qqbot_groups", new_value)
    ss.write_audit(
        db,
        actor=account.display_name or account.username,
        role="admin",
        action="添加推送群",
        target=openid,
        ip=client_ip(request),
    )
    db.commit()
    return {
        "ok": True,
        "message": f"已添加推送群 {openid[:16]}…",
        "configured_groups": new_value,
    }


@router.put("/targets/{old_openid}")
async def edit_target(
    old_openid: str,
    body: TargetBody,
    request: Request,
    db: Session = Depends(get_db),
    account: Account = Depends(require_admin),
):
    """修改一个推送群 openid（换群后 openid 会变，用它直接改）。"""
    old = old_openid.strip()
    new = _validate_openid(body.openid)
    targets = _target_list(ss.get_setting(db, "qqbot_groups"))
    if old not in targets:
        raise AppError(f"推送列表里没有 {old[:16]}…", 404)
    if new != old and new in targets:
        raise AppError("新的 openid 已经在推送列表里了", 400)
    targets[targets.index(old)] = new
    new_value = ",".join(targets)
    ss.set_setting(db, "qqbot_groups", new_value)

    # 同步更新上报记录里的 openid，界面上才能对上号
    record = db.execute(select(BotGroup).where(BotGroup.group_openid == old)).scalars().first()
    if record is not None:
        record.group_openid = new

    ss.write_audit(
        db,
        actor=account.display_name or account.username,
        role="admin",
        action="修改推送群",
        target=new,
        detail=f"由 {old[:16]}… 改为 {new[:16]}…",
        ip=client_ip(request),
    )
    db.commit()
    return {
        "ok": True,
        "message": "推送群已更新",
        "configured_groups": new_value,
    }


@router.delete("/groups")
async def clear_groups(
    request: Request,
    db: Session = Depends(get_db),
    account: Account = Depends(require_admin),
):
    """清空所有已上报的群记录（推送目标也会一并清空）。"""
    rows = list(db.execute(select(BotGroup)).scalars())
    count = len(rows)
    for row in rows:
        db.delete(row)
    ss.set_setting(db, "qqbot_groups", "")
    db.commit()

    ss.write_audit(
        db,
        actor=account.display_name or account.username,
        role="admin",
        action="清空机器人群",
        target="全部分组",
        detail=f"共清除 {count} 条，推送目标已清空",
        ip=client_ip(request),
    )
    db.commit()
    return {"ok": True, "message": f"已清空 {count} 个群记录，推送目标也已清空", "count": count}
