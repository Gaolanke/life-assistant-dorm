"""给测试实例准备数据：管理员登录 + 导入两间寝室。"""

from __future__ import annotations

import io
import sys

import httpx
from openpyxl import Workbook

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8123"
PASSWORD = sys.argv[2] if len(sys.argv) > 2 else "testadmin123"
sys.path.insert(0, ".")

import sqlite3  # noqa: E402
from pathlib import Path  # noqa: E402

from backend import config  # noqa: E402
from backend.database import SessionLocal, init_db  # noqa: E402
from backend.services import settings_service as ss  # noqa: E402

client = httpx.Client(base_url=BASE, timeout=60)
admin: dict[str, str] = {}

init_db()
db = SessionLocal()
ss.ensure_settings(db)
db.close()

# 直接从数据库读初始密码，避免用了另一个数据目录
con = sqlite3.connect(str(Path(config.DB_PATH)))
row = con.execute("select value from settings where key='admin_code'").fetchone()
con.close()
code = row[0] if row else ""
print(f"数据库 {config.DB_PATH}")
print("数据库里的初始密码:", code)

response = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
if response.status_code != 200:
    print("管理员登录失败:", response.status_code, response.text[:200])
    raise SystemExit(1)
client.headers["X-Session-Token"] = response.json()["token"]
print("管理员登录:", response.status_code, response.json().get("message"))

wb = Workbook()
ws = wb.active
ws.append(["姓名", "学号", "电话号", "宿舍号", "备注（宿舍长）"])
ws.append(["张伟", "2023010101", "13800000001", "新区校区3号学生公寓201", "宿舍长"])
ws.append(["李强", "2023010102", "13800000002", "新区校区3号学生公寓201", ""])
ws.append(["王磊", "2023010103", "13800000003", "新区校区3号学生公寓201", ""])
ws.append(["刘洋", "2023010104", "13800000004", "新区校区3号学生公寓202", "宿舍长"])
ws.append(["陈晨", "2023010105", "13800000005", "新区校区3号学生公寓202", ""])
buffer = io.BytesIO()
wb.save(buffer)

preview = client.post("/api/members/import/preview", headers=admin, files={"file": ("t.xlsx", buffer.getvalue())})
print("导入预览:", preview.status_code, preview.json().get("total_dorms"), "间", preview.json().get("total_members"), "人")
commit = client.post(
    "/api/members/import/commit",
    headers=admin,
    json={"token": preview.json()["token"], "strategy": "overwrite", "update_member": True},
)
print("导入结果:", commit.status_code, commit.json().get("message"))

dorms = client.get("/api/dorms?with_members=false").json()["items"]
for dorm in dorms:
    print(f"  {dorm['room_no']}  {dorm['leader_name']}  {dorm['member_count']} 人")

# 给两间寝室都设一个密码，方便测试
for dorm in dorms:
    res = client.post("/api/access/leader/password", headers=admin, json={"dorm_id": dorm["id"], "action": "set", "password": "123456"})
    print("设置密码:", res.json().get("message"))
