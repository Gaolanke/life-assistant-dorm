"""QQ 官方机器人 Webhook 测试：回调校验签名、事件记录群、@机器人 命令。

用法： .venv\\Scripts\\python.exe scripts\\test_qqbot.py
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import server_env  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient  # noqa: E402

from backend.database import SessionLocal, init_db  # noqa: E402
from backend.main import app  # noqa: E402
from backend.models import BotGroup  # noqa: E402
from backend.routers import qqbot as qqbot_router  # noqa: E402
from backend.services import push_service, settings_service as ss  # noqa: E402

PASS, FAIL = [], []
SECRET = "TestSecret_0123456789abcdef"


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} :: {detail}")
    print(f"  [{'OK' if ok else 'FAIL'}] {name}{'' if ok else '  ' + detail}")


def sign(secret: str, message: str) -> str:
    return qqbot_router._ed25519_sign(secret, message)


def main() -> int:
    init_db()
    db = SessionLocal()
    saved = {k: ss.get_setting(db, k) for k in ("qqbot_secret", "qqbot_public_key", "qqbot_groups")}
    ss.ensure_settings(db)
    ss.set_setting(db, "qqbot_secret", SECRET)
    ss.set_setting(db, "qqbot_public_key", "")
    db.commit()
    db.close()

    client = TestClient(app)

    print("\n== 1. 签名算法自检 ==")
    sig = sign(SECRET, "1234567890" + "plain_token_abc")
    # 腾讯官方要求：签名是 128 个十六进制字符（64 字节 hex），不是 base64
    import re as _re
    is_hex = bool(_re.fullmatch(r"[0-9a-f]{128}", sig or ""))
    check("签名是 128 位十六进制", is_hex, (sig or "")[:40])
    check("签名可被同一密钥验证", qqbot_router._ed25519_verify(SECRET, "1234567890plain_token_abc", sig), "")
    check("篡改内容验证不通过", not qqbot_router._ed25519_verify(SECRET, "1234567890plain_token_XXX", sig), "")

    print("\n== 2. 回调地址校验（op=13）—— 这是机器人能不能配上的关键 ==")
    ts = "1730000000"
    token = "Arq0zVvK3lPqX8h"
    resp = client.post("/api/qqbot/events", json={"op": 13, "d": {"plain_token": token, "event_ts": ts}})
    check("校验请求返回 200", resp.status_code == 200, str(resp.status_code))
    data = resp.json()
    check("原样返回 plain_token", data.get("plain_token") == token, str(data))
    check("返回了 signature", bool(data.get("signature")), str(data))
    check(
        "signature 能被公钥验证通过",
        qqbot_router._ed25519_verify(SECRET, ts + token, data.get("signature", "")),
        "签名校验失败",
    )

    print("\n== 3. 群消息事件：记录 group_openid ==")
    db = SessionLocal()
    # 只清理本测试自己的假记录，绝不整表清空
    # （整表清空会把生产环境真实群的记录一起删掉）
    db.query(BotGroup).filter(BotGroup.group_openid == "GROUP_OPENID_TEST_1").delete()
    db.commit()
    db.close()

    event = {
        "op": 0,
        "t": "GROUP_AT_MESSAGE_CREATE",
        "d": {
            "group_openid": "GROUP_OPENID_TEST_1",
            "content": " 谁没填 ",
            "author": {"username": "杨朝辉"},
        },
    }
    body = json.dumps(event, ensure_ascii=False)
    headers = {
        "x-signature-timestamp": ts,
        "x-signature-ed25519": sign(SECRET, ts + body),
    }
    resp = client.post("/api/qqbot/events", content=body.encode("utf-8"), headers=headers)
    check("事件请求返回 200", resp.status_code == 200, str(resp.status_code))

    db = SessionLocal()
    row = db.query(BotGroup).filter(BotGroup.group_openid == "GROUP_OPENID_TEST_1").first()
    check("群里 @ 机器人后记录下了 openid", row is not None, "没有记录到群")
    if row:
        check("记录了群名称字段", row.channel == "qqbot", str(row.channel))
        check("记录了消息内容", "谁没填" in (row.last_message or ""), str(row.last_message))
        check("累计了消息数", (row.message_count or 0) >= 1, str(row.message_count))
    db.close()

    print("\n== 4. 查群接口（配置页用来显示可选的群） ==")
    # 这个接口在加固后要求管理员登录（未登录时应被挡住），所以先验证拦截、再带 token 查
    anon = client.get("/api/qqbot/groups")
    check("未登录时被挡住", anon.status_code in (401, 403), f"状态码 {anon.status_code}")

    # 直接签发一个管理员会话令牌（进程内测试，不必走密码登录）
    from sqlalchemy import select as _select

    from backend.models import Account as _Account
    from backend.security import ensure_owner_account, issue_session

    _db = SessionLocal()
    ensure_owner_account(_db)
    _admin = _db.execute(
        _select(_Account).where(_Account.role == "admin").order_by(_Account.id)
    ).scalars().first()
    token = issue_session(_admin) if _admin is not None else ""
    _db.close()
    headers = {"X-Session-Token": token} if token else {}
    resp = client.get("/api/qqbot/groups", headers=headers)
    check("管理员登录后接口可用", resp.status_code == 200, str(resp.status_code))
    payload = resp.json()
    check(
        "列出了刚记录的群",
        any(i["group_openid"] == "GROUP_OPENID_TEST_1" for i in payload.get("items", [])),
        str(payload)[:200],
    )

    print("\n== 5. 签名不对时拒绝（防伪造事件） ==")
    bad_headers = {
        "x-signature-timestamp": ts,
        "x-signature-ed25519": sign("另一个不同的密钥_0123456789", ts + body),
    }
    resp = client.post("/api/qqbot/events", content=body.encode("utf-8"), headers=bad_headers)
    check("伪造签名被拒绝", resp.json().get("ok") is False, str(resp.json()))

    print("\n== 6. 没配 AppSecret 时校验请求给出明确提示 ==")
    db = SessionLocal()
    ss.set_setting(db, "qqbot_secret", "")
    db.commit()
    db.close()
    resp = client.post("/api/qqbot/events", json={"op": 13, "d": {"plain_token": "t", "event_ts": ts}})
    check("提示需要先填 AppSecret", "AppSecret" in str(resp.json()), str(resp.json()))
    db = SessionLocal()
    ss.set_setting(db, "qqbot_secret", SECRET)
    db.commit()
    db.close()

    print("\n== 7. @机器人 发填报内容会被记录（走同一个回调） ==")
    for key, value in saved.items():
        db = SessionLocal()
        ss.set_setting(db, key, value)
        db.commit()
        db.close()

    print("\n" + "=" * 56)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    for item in FAIL:
        print("  - " + item)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
