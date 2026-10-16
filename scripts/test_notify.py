"""通知通道测试：QQ 官方机器人（用模拟 HTTP，不发真实消息）。

用法： .venv\\Scripts\\python.exe scripts\\test_notify.py
"""
from __future__ import annotations

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
from backend.services import push_service, settings_service as ss  # noqa: E402

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} :: {detail}")
    print(f"  [{'OK' if ok else 'FAIL'}] {name}{'' if ok else '  ' + detail}")


class FakeResponse:
    def __init__(self, status_code: int, data: dict):
        self.status_code = status_code
        self._data = data
        self.text = str(data)

    def json(self):
        return self._data


class FakeClient:
    """假的 httpx.AsyncClient，用来模拟 QQ 官方接口。"""

    calls: list[tuple[str, str, dict]] = []
    token_response: dict = {"access_token": "fake-token-abc", "expires_in": "7200"}
    send_response: dict = {"id": "MSG123", "timestamp": 1750000000}
    send_status: int = 200

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None, **kwargs):
        FakeClient.calls.append((url, str((headers or {}).get("Authorization", "")), json or {}))
        if "getAppAccessToken" in url:
            return FakeResponse(200, FakeClient.token_response)
        return FakeResponse(FakeClient.send_status, FakeClient.send_response)


def main() -> int:
    init_db()
    db = SessionLocal()
    original = {
        key: ss.get_setting(db, key)
        for key in (
            "qqbot_enabled", "qqbot_app_id", "qqbot_secret", "qqbot_groups",
        )
    }

    real_client = httpx.AsyncClient
    httpx.AsyncClient = FakeClient  # type: ignore[assignment]
    try:
        print("\n== 1. 没配置时应当给出清晰提示 ==")
        ss.set_setting(db, "qqbot_enabled", "0")
        ss.set_setting(db, "qqbot_app_id", "")
        ss.set_setting(db, "qqbot_secret", "")
        res = asyncio_run(push_service.check_qqbot(db))
        check("未启用时提示去开启", res["ok"] is False and "启用" in res["message"], str(res))

        ss.set_setting(db, "qqbot_enabled", "1")
        res = asyncio_run(push_service.check_qqbot(db))
        check("启用但没填 AppID 时提示去填", "AppID" in res["message"], str(res))

        print("\n== 2. 正常配置：取 token → 发群消息 ==")
        FakeClient.calls.clear()
        ss.set_setting(db, "qqbot_app_id", "102000001")
        ss.set_setting(db, "qqbot_secret", "secret-xyz")
        ss.set_setting(db, "qqbot_groups", "GROUP_OPENID_A")
        push_service._TOKEN_CACHE.clear()

        res = asyncio_run(push_service.check_qqbot(db))
        check("自检能拿到 token", res["ok"] is True, str(res))
        check("自检报告了群数量", "1 个群" in res["message"], str(res))

        sent = asyncio_run(push_service.send_group_message(db, "GROUP_OPENID_A", "今晚 6-213 人齐"))
        check("发群消息成功", sent["ok"] is True, str(sent))
        urls = [call[0] for call in FakeClient.calls]
        check("调了取 token 接口", any("getAppAccessToken" in u for u in urls), str(urls))
        check("调了发消息接口", any("/v2/groups/GROUP_OPENID_A/messages" in u for u in urls), str(urls))
        auth = [call[1] for call in FakeClient.calls if "/messages" in call[0]]
        check("带了 QQBot 鉴权头", auth and auth[0].startswith("QQBot "), str(auth))
        body = [call[2] for call in FakeClient.calls if "/messages" in call[0]][0]
        check("消息体含 content 和 msg_type", body.get("content") and "msg_type" in body, str(body))

        print("\n== 3. token 缓存（不该每次都去取） ==")
        FakeClient.calls.clear()
        asyncio_run(push_service.send_group_message(db, "GROUP_OPENID_A", "第二条"))
        token_calls = [c for c in FakeClient.calls if "getAppAccessToken" in c[0]]
        check("第二次发送复用了 token", len(token_calls) == 0, f"取了 {len(token_calls)} 次")

        print("\n== 4. 常见错误码给出人话提示 ==")
        FakeClient.send_status = 200
        FakeClient.send_response = {"code": 11245, "message": "no permission"}
        bad = asyncio_run(push_service.send_group_message(db, "GROUP_OPENID_A", "测试"))
        check("11245 提示群未开通主动消息", bad["ok"] is False and "主动消息" in bad["message"], str(bad))

        FakeClient.send_response = {"code": 11244, "message": "bot not in group"}
        bad = asyncio_run(push_service.send_group_message(db, "GROUP_OPENID_A", "测试"))
        check("11244 提示机器人未入群", "未加入" in bad["message"] or "启用" in bad["message"], str(bad))

        FakeClient.send_response = {"code": 40034004, "message": "quota"}
        bad = asyncio_run(push_service.send_group_message(db, "GROUP_OPENID_A", "测试"))
        check("配额用完有明确说明", "额度" in bad["message"], str(bad))

        print("\n== 5. token 拿不到时不硬撑 ==")
        FakeClient.token_response = {"code": 100007, "message": "appid invalid"}
        push_service._TOKEN_CACHE.clear()
        bad = asyncio_run(push_service.send_group_message(db, "GROUP_OPENID_A", "测试"))
        check("取 token 失败有提示", bad["ok"] is False and "access_token" in bad["message"], str(bad))

        print("\n== 6. 投递走 QQ 通道 ==")
        FakeClient.token_response = {"access_token": "fake-token-abc", "expires_in": "7200"}
        push_service._TOKEN_CACHE.clear()
        FakeClient.send_response = {"id": "MSG999"}
        FakeClient.send_status = 200
        result3 = asyncio_run(push_service.deliver_notification(
            db, title="填报汇总", content="人齐", scene="test"
        ))
        check("QQ 成功时走 QQ 通道", result3["ok"] and result3["channel"] == "qqbot", str(result3))

        print("\n== 7. 发群接口对错误参数的处理 ==")
        res = asyncio_run(push_service.send_group_message(db, "", "测试"))
        check("群 openid 为空时报错", res["ok"] is False and "openid" in res["message"], str(res))
        check("敏感信息打码", push_service.mask_secret("abcdefghijklmn") == "abcd******klmn", push_service.mask_secret("abcdefghijklmn"))
    finally:
        httpx.AsyncClient = real_client  # type: ignore[assignment]
        for key, value in original.items():
            ss.set_setting(db, key, value)
        db.commit()
        db.close()

    print("\n" + "=" * 56)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    for item in FAIL:
        print("  - " + item)
    return 1 if FAIL else 0


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)


if __name__ == "__main__":
    raise SystemExit(main())
