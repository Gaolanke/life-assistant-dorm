#!/usr/bin/env bash
# 检查每个备份的数据量，找出最完整的一份
set -u
cd /www/dorm || exit 1

.venv/bin/python - <<'PY'
import sqlite3
from pathlib import Path

BACKUP_DIR = Path("/www/dorm-data/backups")
CURRENT = Path("/www/dorm-data/app.db")

def counts(path):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    cur = con.cursor()
    out = {}
    for t in ("dorms", "members", "reports", "report_checkins", "fund_entries", "accounts", "push_logs", "bot_groups"):
        try:
            out[t] = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except Exception:
            out[t] = -1
    # 取几个宿舍号作为样本
    try:
        out["sample"] = ",".join(r[0] for r in cur.execute("SELECT room_no FROM dorms ORDER BY room_no LIMIT 5"))
    except Exception:
        out["sample"] = ""
    con.close()
    return out

print("当前生产库:", CURRENT)
cur_c = counts(CURRENT)
print(f"  宿舍={cur_c['dorms']} 人员={cur_c['members']} 填报={cur_c['reports']} 班费={cur_c['fund_entries']} 账号={cur_c['accounts']}")
print()

print(f"{'备份文件':<40}{'宿舍':>5}{'人员':>5}{'填报':>5}{'班费':>5}  样本宿舍")
print("-" * 92)
best = None
for f in sorted(BACKUP_DIR.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True):
    try:
        c = counts(f)
    except Exception as exc:
        print(f"{f.name:<40}  读取失败 {exc}")
        continue
    print(f"{f.name:<40}{c['dorms']:>5}{c['members']:>5}{c['reports']:>5}{c['fund_entries']:>5}  {c['sample']}")
    if c["dorms"] >= 14 and c["members"] >= 40:
        if best is None:
            best = (f, c)

print()
if best:
    print(f"✅ 最完整且最新的可用备份：{best[0].name}")
    print(f"   宿舍 {best[1]['dorms']} 间 / 人员 {best[1]['members']} 人 / 班费 {best[1]['fund_entries']} 条 / 账号 {best[1]['accounts']} 个")
else:
    print("❌ 没有找到含完整名单的备份")
PY
