#!/usr/bin/env bash
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from sqlalchemy import select
from backend.database import SessionLocal
from backend.models import Setting
db = SessionLocal()
for k in ("site_public_url", "site_admin_url", "report_deadline", "notice_text", "tpl_reminder"):
    row = db.execute(select(Setting).where(Setting.key == k)).scalar()
    v = row.value if row else "(缺)"
    print(f"  {k:<20} = {v[:90]!r}")
db.close()
PY
