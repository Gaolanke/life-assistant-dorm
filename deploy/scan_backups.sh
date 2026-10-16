#!/usr/bin/env bash
# 扫描所有备份，找出含完整数据的那一份
set -u
cd /www/dorm || exit 1

.venv/bin/python - <<'PY'
import sqlite3
from pathlib import Path

from backend import config

print(f"{'备份文件':<38}{'宿舍':>5}{'人员':>5}{'填报':>5}{'班费':>5}{'账号':>5}")
print("-" * 70)
rows = []
for f in sorted(config.BACKUP_DIR.glob("app_*.db"), reverse=True):
    try:
        con = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
        cur = con.cursor()
        def cnt(t):
            try:
                return cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except Exception:
                return -1
        d, m, r, fe, a = cnt("dorms"), cnt("members"), cnt("reports"), cnt("fund_entries"), cnt("accounts")
        con.close()
        rows.append((f.name, d, m, r, fe, a, f))
        print(f"{f.name:<38}{d:>5}{m:>5}{r:>5}{fe:>5}{a:>5}")
    except Exception as exc:
        print(f"{f.name:<38}  读取失败 {exc}")

print()
best = [r for r in rows if r[1] >= 14 and r[2] >= 40]
if best:
    print("✅ 可用于恢复的备份：")
    for name, d, m, r, fe, a, f in best[:5]:
        print(f"    {name}  宿舍 {d} / 人员 {m}")
else:
    partial = [r for r in rows if r[1] > 0]
    print("⚠️ 没有宿舍数 >=14 的备份；有数据的备份：")
    for name, d, m, r, fe, a, f in partial[:8]:
        print(f"    {name}  宿舍 {d} / 人员 {m}")
PY
