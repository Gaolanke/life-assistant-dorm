#!/usr/bin/env bash
# 检查服务器生产数据是否完好
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from sqlalchemy import func, select
from backend import config
from backend.database import SessionLocal
from backend.models import Account, BotGroup, Dorm, FundEntry, Member, PushLog, Report

db = SessionLocal()
print("  数据目录:", config.DATA_DIR)
print("  数据库文件:", config.DB_PATH)
for name, model in (("宿舍", Dorm), ("人员", Member), ("填报", Report),
                    ("班费明细", FundEntry), ("账号", Account),
                    ("推送日志", PushLog), ("机器人群", BotGroup)):
    n = db.execute(select(func.count(model.id))).scalar()
    print(f"    {name:<8} {n}")
print()
print("  宿舍列表：", ", ".join(d.room_no for d in db.execute(select(Dorm).order_by(Dorm.room_no)).scalars()))
db.close()
PY
