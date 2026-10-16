#!/usr/bin/env bash
# 测试群删除功能
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

.venv/bin/python - <<'PY'
import sys

sys.path.insert(0, '.')
import httpx

c = httpx.Client(base_url="http://127.0.0.1:8091", timeout=30)
r = c.post("/api/auth/login", json={"username": "admin", "password": "344940"})
h = {"X-Session-Token": r.json().get("token", "")}
print(f"登录: {r.status_code}")

# 1) 列出当前群
g = c.get("/api/qqbot/groups", headers=h).json()
items = g.get("items", [])
print(f"\n当前 {len(items)} 个群：")
for it in items:
    print(f"  id={it['id']}  openid={it['group_openid'][:20]}…  是否推送中={it.get('is_target')}")

print(f"\n推送目标 = {g.get('configured_groups')!r}")

# 2) 未登录应被拒
anon = c.delete("/api/qqbot/groups/1")
print(f"\n未登录删除 -> HTTP {anon.status_code} {'✅ 已挡住' if anon.status_code == 401 else '❌'}")

# 3) 删除不存在的 id
bad = c.delete("/api/qqbot/groups/999999", headers=h)
print(f"删除不存在的 id -> HTTP {bad.status_code} {bad.json().get('message')}")

# 4) 删除一个测试记录（先造一条假记录，避免误删真实群）
from backend.database import SessionLocal
from backend.models import BotGroup
from backend.services import settings_service as ss

db = SessionLocal()
fake = BotGroup(channel="qqbot", group_openid="TEST_GROUP_TO_DELETE_0001", group_no="0001")
db.add(fake)
db.commit()
fake_id = fake.id
# 顺便把它加进推送目标，验证「同时从目标移除」
old_target = ss.get_setting(db, "qqbot_groups")
ss.set_setting(db, "qqbot_groups", f"{old_target},TEST_GROUP_TO_DELETE_0001")
db.commit()
print(f"\n已造测试记录 id={fake_id}，并加入推送目标")
db.close()

res = c.delete(f"/api/qqbot/groups/{fake_id}", headers=h)
print(f"删除测试记录 -> HTTP {res.status_code} {res.json().get('message')}")
print(f"  是否从目标移除: {res.json().get('removed_from_target')}")

after = c.get("/api/qqbot/groups", headers=h).json()
print(f"\n删除后剩 {after.get('total')} 个群，推送目标 = {after.get('configured_groups')!r}")
names = [i["group_openid"] for i in after.get("items", [])]
print(f"测试记录还在吗: {'❌ 还在' if 'TEST_GROUP_TO_DELETE_0001' in names else '✅ 已删除'}")
print(f"目标里还在吗:   {'❌ 还在' if 'TEST_GROUP_TO_DELETE_0001' in (after.get('configured_groups') or '') else '✅ 已移除'}")

# 恢复推送目标
db = SessionLocal()
ss.set_setting(db, "qqbot_groups", old_target)
db.commit()
db.close()
print(f"\n已恢复推送目标为: {old_target!r}")
PY
