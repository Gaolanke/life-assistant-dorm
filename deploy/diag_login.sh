#!/usr/bin/env bash
# 诊断管理员登录
set -u
cd /www/dorm || exit 1

echo "=== 1. 数据库里的账号 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.models import Account
db = SessionLocal()
for a in db.query(Account).all():
    print(f"  id={a.id} username={a.username!r} role={a.role} active={a.active} "
          f"owner={a.is_owner} hash_len={len(a.password_hash or '')} hash_prefix={(a.password_hash or '')[:20]}")
    print(f"     must_change={a.must_change} last_login={a.last_login_at}")
db.close()
PY

echo
echo "=== 2. admin_code 设置值 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import settings_service as ss
db = SessionLocal()
print("  admin_code =", repr(ss.get_setting(db, 'admin_code')))
db.close()
PY

echo
echo "=== 3. 逐个候选密码试登录 ==="
for pw in 344940 testadmin123 743323; do
  code=$(curl -s -o /tmp/login_out.json -w '%{http_code}' -X POST \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"admin\",\"password\":\"$pw\"}" \
    http://127.0.0.1:8091/api/auth/login)
  printf '  密码 %-14s -> HTTP %s %s\n' "$pw" "$code" "$(head -c 90 /tmp/login_out.json)"
done

echo
echo "=== 4. 直接校验哈希（不经过接口） ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.models import Account
from backend.security import verify_password
db = SessionLocal()
a = db.query(Account).filter(Account.username == 'admin').first()
for pw in ('344940', 'testadmin123', '743323'):
    print(f"  verify('{pw}') =", verify_password(pw, a.password_hash))
db.close()
PY
