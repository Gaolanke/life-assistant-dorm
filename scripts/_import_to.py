"""把真实名单导入到指定实例（测试用）。

用法： python scripts/_import_to.py http://127.0.0.1:8123 [管理员密码]
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8123"
PASSWORD = sys.argv[2] if len(sys.argv) > 2 else "testadmin123"
FILE = ROOT / "新区宿舍物联网25-2(1).xlsx"

client = httpx.Client(base_url=BASE, timeout=120)
login = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
if login.status_code != 200:
    print("管理员登录失败:", login.status_code, login.text[:200])
    raise SystemExit(1)
client.headers["X-Session-Token"] = login.json()["token"]
headers = {}
with FILE.open("rb") as handle:
    content = handle.read()
preview = client.post("/api/members/import/preview", headers=headers, files={"file": (FILE.name, content)})
data = preview.json()
print("预览:", preview.status_code, data.get("total_dorms"), "间", data.get("total_members"), "人")
commit = client.post(
    "/api/members/import/commit",
    headers=headers,
    json={"token": data["token"], "strategy": "overwrite", "update_member": True},
)
print("导入:", commit.status_code, commit.json().get("message"))

# 给所有寝室设置统一密码，便于测试寝室长验证
accounts = client.get("/api/access/leader/accounts", headers=headers).json()["items"]
for dorm in accounts:
    res = client.post("/api/access/leader/password", headers=headers, json={"dorm_id": dorm["dorm_id"], "action": "set", "password": "123456"})
    if res.status_code != 200:
        print("  设密码失败:", dorm["room_no"], res.text[:120])
print(f"已为 {len(accounts)} 间寝室设置验证密码 123456")
