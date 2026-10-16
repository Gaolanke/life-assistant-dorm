"""服务器定时通知脚本：把当天填报情况 / 未填提醒发到 QQ 群（QQ 官方机器人）。

直接命令行跑，也可以交给 cron / systemd timer 定时跑：

    # 每天 22:40 发当天填报汇总到 QQ 群
    40 22 * * * cd /www/dorm && DORM_DATA_DIR=/www/dorm-data .venv/bin/python scripts/notify_push.py report >> /www/dorm-data/logs/notify.log 2>&1

    # 每天 22:00 提醒未填报的寝室
    0 22 * * * cd /www/dorm && DORM_DATA_DIR=/www/dorm-data .venv/bin/python scripts/notify_push.py remind >> /www/dorm-data/logs/notify.log 2>&1

用法：
    python scripts/notify_push.py report            # 发当天填报汇总
    python scripts/notify_push.py remind            # 发未填报提醒
    python scripts/notify_push.py dorm 6-213        # 只发某一间寝室的催填
    python scripts/notify_push.py text "任意内容"    # 发一条自定义消息
    python scripts/notify_push.py check             # 只检查通道配置
    python scripts/notify_push.py --day 2026-10-10 report
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(Path(__file__).resolve().parent))

import server_env  # noqa: E402

from backend.database import SessionLocal, init_db  # noqa: E402
from backend.services import notify_service, push_service, report_service  # noqa: E402
from backend.services import settings_service as ss  # noqa: E402
from backend.util import parse_date  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", nargs="?", default="report",
                        choices=["report", "remind", "dorm", "text", "check"])
    parser.add_argument("value", nargs="?", default="", help="dorm 的宿舍号 / text 的内容")
    parser.add_argument("--day", default="", help="指定日期 YYYY-MM-DD")
    parser.add_argument("--group", default="", help="指定 QQ 群 openid（留空用配置里的）")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        ss.ensure_settings(db)
        day = parse_date(args.day) if args.day else None

        if args.action == "check":
            import asyncio

            print("【通道配置自检】")
            qq = asyncio.run(push_service.check_qqbot(db))
            print(f"  QQ 官方机器人：{'✅' if qq['ok'] else '❌'} {qq['message']}")
            return 0

        if args.action == "report":
            content = notify_service.build_group_report(db, day)
            title = f"{day or '今天'} 填报汇总"
        elif args.action == "remind":
            content = notify_service.build_missing_reminder(db, day)
            title = f"{day or '今天'} 未填报提醒"
        elif args.action == "dorm":
            if not args.value:
                print("请指定宿舍号，例如： notify_push.py dorm 6-213")
                return 2
            dorm = report_service.get_dorm_by_room(db, args.value)
            if dorm is None:
                print(f"没有找到宿舍 {args.value}")
                return 2
            content = notify_service.build_dorm_pending(db, dorm, day)
            title = f"{dorm.room_no} 催填"
        else:
            content = args.value
            title = "自定义通知"

        print(f"【要发送的内容】\n{content}\n")
        result = asyncio.run(push_service.deliver_notification(
            db,
            title=title,
            content=content,
            scene=args.action,
            group_openid=args.group,
        ))
        print(f"投递结果：{'✅' if result['ok'] else '❌'} [{result['channel']}] {result['message']}")
        for item in result.get("results", []):
            mark = "✅" if item.get("ok") else "❌"
            extra = f"（群 {item.get('group')}）" if item.get("group") else ""
            print(f"  {mark} {item.get('channel')}{extra}：{item.get('message')}")

        notify_service.log_push(
            db,
            channel=result["channel"],
            scene=args.action,
            target=args.group or ss.get_setting(db, "qqbot_groups"),
            title=title,
            content=content,
            status="success" if result["ok"] else "failed",
            detail=result["message"],
            trigger="cron",
        )
        return 0 if result["ok"] else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
