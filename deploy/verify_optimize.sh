#!/usr/bin/env bash
# 验证本轮优化：越权、并发、索引、备份
set -u
cd /www/dorm || exit 1

echo "############ 1. 越权：寝室长账号不能登录管理端 ############"
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
import httpx
from backend.database import SessionLocal
from backend.models import Account
from backend.services import settings_service as ss

db = SessionLocal()
# 找一个寝室长账号；没有就临时建一个
leader = db.query(Account).filter(Account.role == "leader").first()
created = False
if leader is None:
    from backend.security import hash_password
    from backend.models import Dorm
    dorm = db.query(Dorm).first()
    leader = Account(username="test-leader", display_name="测试寝室长", password_hash=hash_password("test123456"),
                     role="leader", dorm_id=dorm.id if dorm else 0, active=True)
    db.add(leader)
    db.commit()
    created = True
print("  使用寝室长账号:", leader.username, "| 绑定宿舍:", leader.dorm_id)

admin_port = "http://127.0.0.1:8091"
public_port = "http://127.0.0.1:8090"

# 管理端口登录 → 应该被拒
r = httpx.post(f"{admin_port}/api/auth/login", json={"username": leader.username, "password": "test123456"}, timeout=20)
print(f"  ① 寝室长登录【管理端】 -> HTTP {r.status_code} {'✅ 已拒绝' if r.status_code != 200 else '❌ 竟然放行了'}")
print(f"     提示: {r.json().get('message') if r.status_code != 200 else r.json().get('message')}")

# 公开端口登录 → 应该成功
r2 = httpx.post(f"{public_port}/api/auth/login", json={"username": leader.username, "password": "test123456"}, timeout=20)
ok2 = r2.status_code == 200 and r2.json().get("ok")
print(f"  ② 寝室长登录【公开端】 -> HTTP {r2.status_code} {'✅ 正常' if ok2 else '❌ 不该失败'}")

# 管理端接口用寝室长 token → 应该 401/403
if ok2:
    tok = r2.json().get("token", "")
    h = {"X-Session-Token": tok}
    for path in ("/api/accounts", "/api/logs/push", "/api/fund/entries"):
        res = httpx.get(f"{admin_port}{path}", headers=h, timeout=20)
        mark = "✅ 已挡住" if res.status_code in (401, 403) else f"❌ 返回 {res.status_code}"
        print(f"  ③ 寝室长访问管理接口 {path:<22} -> {res.status_code} {mark}")

if created:
    db.delete(leader)
    db.commit()
    print("  （已删除临时测试账号）")
db.close()
PY

echo
echo "############ 2. 并发重复提交：不会多人数 ############"
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys, threading
sys.path.insert(0, '.')
import httpx
from backend.database import SessionLocal
from backend.models import Dorm, Member, Report
from backend.services import report_service

db = SessionLocal()
dorm = db.query(Dorm).first()
members = [m for m in db.query(Member).filter(Member.dorm_id == dorm.id).all()]
print(f"  测试宿舍: {dorm.room_no} | 成员 {len(members)} 人")
before = db.query(Report).filter(Report.dorm_id == dorm.id).count()

results = []
def submit(n):
    try:
        c = httpx.Client(base_url="http://127.0.0.1:8090", timeout=30)
        payload = {
            "dorm_id": dorm.id,
            "is_complete": True,
            "absent_names": "",
            "note": f"并发测试 {n}",
            "submitter": f"并发{n}",
            "checkins": [{"member_id": m.id, "name": m.name, "present": True} for m in members],
        }
        r = c.post("/api/reports/submit", json=payload)
        results.append((n, r.status_code, (r.json() or {}).get("message", "")[:30]))
    except Exception as exc:
        results.append((n, "异常", str(exc)[:40]))

threads = [threading.Thread(target=submit, args=(i,)) for i in range(1, 7)]
for t in threads: t.start()
for t in threads: t.join()

print("  6 个并发提交结果：")
ok = sum(1 for _, code, _ in results if code == 200)
for n, code, msg in sorted(results):
    print(f"    第{n}次 -> HTTP {code} {msg}")
print(f"  成功 {ok}/6")

db.expire_all()
after = db.query(Report).filter(Report.dorm_id == dorm.id).count()
rec = db.query(Report).filter(Report.dorm_id == dorm.id, Report.report_date == __import__('datetime').date.today()).first()
print(f"  Report 记录数: 之前 {before} -> 之后 {after}  {'✅ 没有重复记录' if after - before <= 1 else '❌ 出现重复'}")
if rec:
    print(f"  该条记录: 总人数={rec.total_count} 在寝={rec.present_count} 缺席={rec.absent_count} 备注={rec.note[:20]!r}")
    print(f"  {'✅ 人数正确' if rec.present_count == len(members) and rec.total_count == len(members) else '❌ 人数异常'}")
db.close()
PY

echo
echo "############ 3. 数据库索引与查询计划 ############"
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
import sqlite3
from backend import config

con = sqlite3.connect(str(config.DB_PATH))
cur = con.cursor()

print("  已有索引：")
for (tbl,) in cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
    idx = cur.execute(f"PRAGMA index_list('{tbl}')").fetchall()
    if idx:
        names = []
        for row in idx:
            # row: (seq, name, unique, origin, partial)
            cols = [c[2] for c in cur.execute(f"PRAGMA index_info('{row[1]}')")]
            names.append(f"{row[1]}({','.join(cols)}){' UNIQUE' if row[2] else ''}")
        print(f"    {tbl:<16} {'; '.join(names)}")

print()
print("  热点查询的执行计划（看有没有 SCAN 全表）：")
queries = [
    ("当天全部填报", "SELECT * FROM reports WHERE report_date = date('now')"),
    ("某宿舍某天", "SELECT * FROM reports WHERE dorm_id=1 AND report_date=date('now')"),
    ("某宿舍成员", "SELECT * FROM members WHERE dorm_id=1"),
    ("勾选明细", "SELECT * FROM report_checkins WHERE report_id=1"),
    ("班费按日期", "SELECT * FROM fund_entries WHERE entry_date >= date('now','-30 day')"),
    ("推送日志", "SELECT * FROM push_logs ORDER BY created_at DESC LIMIT 20"),
    ("审计日志", "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 20"),
]
for label, sql in queries:
    plan = cur.execute("EXPLAIN QUERY PLAN " + sql).fetchall()
    text = " | ".join(str(p[-1]) for p in plan)
    flag = "⚠️ 全表扫描" if "SCAN" in text and "USING INDEX" not in text and "USING COVERING INDEX" not in text else "✅ 走索引"
    print(f"    {label:<14} {flag}")
    print(f"        {text[:110]}")
con.close()
PY

echo
echo "############ 4. 手动触发一次备份 ############"
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.services import backup_service
r = backup_service.create_backup(keep=30, tag="manual")
print("  结果:", "✅" if r["ok"] else "❌", r["message"])
items = backup_service.list_backups()
print(f"  当前共 {len(items)} 份备份：")
for it in items[:5]:
    print(f"    {it['created_at']}  {it['name']:<30} {it['size_text']}")
PY

echo
echo "############ 5. 定时任务清单 ############"
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend import scheduler
from backend.services import settings_service as ss
db = SessionLocal()
for k in ("qq_report_time", "showdoc_remind_time", "auto_export_time", "auto_backup_time", "backup_keep"):
    print(f"  {k:<22} = {ss.get_setting(db, k)!r}")
db.close()
sched = scheduler.build_scheduler()
print("  已注册任务：")
for job in sched.get_jobs():
    print(f"    {job.id:<18} 下次运行 {job.next_run_time}")
PY
