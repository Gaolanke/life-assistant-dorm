"""把服务器上的 QQ 机器人 AppID 换成新机器人（1905772776）。

AppSecret 是密钥，脚本不写死，改由用户通过环境变量传入：
  NEW_SECRET=xxx python scripts/switch_bot.py
不传则只改 AppID，保留原密钥（此时鉴权会失败，提示用户补 AppSecret）。
"""
import os
import sys

sys.path.insert(0, ".")

from sqlalchemy import select

from backend.database import SessionLocal
from backend.models import Setting
from backend.services import settings_service as ss

NEW_APP_ID = os.environ.get("NEW_APP_ID", "1905772776").strip()
NEW_SECRET = os.environ.get("NEW_SECRET", "").strip()

db = SessionLocal()

before = {
    "app_id": ss.get_setting(db, "qqbot_app_id"),
    "secret": ss.get_setting(db, "qqbot_secret"),
}
print("修改前：")
print(f"  AppID      = {before['app_id']}")
print(f"  AppSecret  = {'已配置，长度 ' + str(len(before['secret']))}")

updates = {"qqbot_app_id": NEW_APP_ID}
if NEW_SECRET:
    updates["qqbot_secret"] = NEW_SECRET
    print("\n将同时更新 AppSecret")
else:
    print("\n只更新 AppID（AppSecret 未提供，保留原值——届时鉴权会失败）")

for k, v in updates.items():
    row = db.execute(select(Setting).where(Setting.key == k)).scalar()
    if row is None:
        db.add(Setting(key=k, value=v, group="qqbot", description=""))
    else:
        row.value = v
db.commit()

print("\n修改后：")
print(f"  AppID      = {ss.get_setting(db, 'qqbot_app_id')}")
sec = ss.get_setting(db, "qqbot_secret")
print(f"  AppSecret  = {'已配置，长度 ' + str(len(sec)) if sec else '（空）'}")
db.close()
