#!/usr/bin/env bash
# 在【完全隔离的临时实例】上跑每个测试套件：
#   - 每个套件都用一份全新的生产数据快照（SQLite 官方备份接口，WAL 安全）
#   - 套件之间互不影响（selftest 清理自己的宿舍，不会影响下一个）
#   - 实例跑在 8190 / 8191，生产 8090 / 8091 全程不动
#   - 跑完自动清理临时数据
set -u
cd /www/dorm || exit 1

PROD_DIR=/www/dorm-data
WORK=$(mktemp -d /tmp/dorm-tests-XXXXXX)
TEST_PUB=8190
TEST_ADM=8191
SERVER_PID=""

cleanup() {
  [ -n "$SERVER_PID" ] && kill -9 "$SERVER_PID" 2>/dev/null
  rm -rf "$WORK"
}
trap cleanup EXIT

echo "=== 制作生产数据快照（一致性，WAL 安全） ==="
DORM_DATA_DIR="$PROD_DIR" SNAP="$WORK/snapshot.db" .venv/bin/python - <<'PY' 2>/dev/null
import os
import shutil
import sys

sys.path.insert(0, '.')
from backend.services import backup_service

result = backup_service.create_backup(keep=200, tag="fortest")
if result.get("ok"):
    shutil.copyfile(result["path"], os.environ["SNAP"])
    try:
        os.unlink(result["path"])
    except OSError:
        pass
PY
[ -f "$WORK/snapshot.db" ] || { echo "  ❌ 快照失败"; exit 1; }
.venv/bin/python - "$WORK/snapshot.db" <<'PY'
import sqlite3, sys
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
cur = con.cursor()
print("  快照数据：", " / ".join(
    f"{n} {cur.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}"
    for n, t in (("宿舍", "dorms"), ("人员", "members"), ("班费", "fund_entries"), ("账号", "accounts"))
))
con.close()
PY
echo "  生产库全程不动: $PROD_DIR/app.db"

PUB="http://127.0.0.1:$TEST_PUB"
ADM="http://127.0.0.1:$TEST_ADM"

SUITES="
selftest|admin
test_two_ports|public
test_access|admin
test_accounts|admin
test_lock_logs|public
test_admin_edit|admin
test_password_reset|admin
test_notify|none
test_qqbot|none
test_qqbot_ws|none
test_fund|none
"

TOTAL_PASS=0
TOTAL_FAIL=0
FAILED=""
SKIPPED=""

echo
echo "=== 逐套件跑（每个套件都用一个全新的隔离实例） ==="
for item in $SUITES; do
  t="${item%%|*}"
  order="${item##*|}"
  [ -f "scripts/$t.py" ] || { SKIPPED="$SKIPPED $t(缺)"; continue; }

  DIR="$WORK/$t"
  mkdir -p "$DIR/backups" "$DIR/exports" "$DIR/uploads" "$DIR/logs"
  cp "$WORK/snapshot.db" "$DIR/app.db"
  [ -f "$PROD_DIR/secret.key" ] && cp "$PROD_DIR/secret.key" "$DIR/secret.key"

  DORM_DATA_DIR="$DIR" DORM_PORT=$TEST_PUB DORM_ADMIN_PORT=$TEST_ADM \
    .venv/bin/python run.py > "$DIR/server.log" 2>&1 &
  SERVER_PID=$!

  READY=0
  for _ in $(seq 1 60); do
    curl -fsS "$PUB/api/health" >/dev/null 2>&1 && { READY=1; break; }
    sleep 0.5
  done
  if [ "$READY" != "1" ]; then
    printf '  ❌ %-20s 隔离实例启动失败\n' "$t"
    tail -5 "$DIR/server.log" | sed 's/^/        /'
    SKIPPED="$SKIPPED $t(启动失败)"
    kill -9 "$SERVER_PID" 2>/dev/null
    SERVER_PID=""
    continue
  fi

  case "$order" in
    admin)  args="$ADM $PUB" ;;
    public) args="$PUB $ADM" ;;
    *)      args="" ;;
  esac

  export DORM_TEST_PUBLIC="$PUB"
  export DORM_TEST_ADMIN="$ADM"
  export DORM_DATA_DIR="$DIR"
  export DORM_ADMIN_PASSWORD="${DORM_ADMIN_PASSWORD:-344940}"

  out=$(.venv/bin/python "scripts/$t.py" $args 2>&1 | tail -4)
  line=$(echo "$out" | grep -oE '通过 [0-9]+ 项，失败 [0-9]+ 项' | tail -1)
  if [ -z "$line" ]; then
    printf '  ⚠️  %-20s 未取到结果\n' "$t"
    echo "$out" | tail -3 | sed 's/^/        /'
    SKIPPED="$SKIPPED $t"
  else
    p=$(echo "$line" | grep -oE '通过 [0-9]+' | grep -oE '[0-9]+')
    f=$(echo "$line" | grep -oE '失败 [0-9]+' | grep -oE '[0-9]+')
    TOTAL_PASS=$((TOTAL_PASS + p))
    TOTAL_FAIL=$((TOTAL_FAIL + f))
    if [ "$f" = "0" ]; then
      printf '  ✅ %-20s 通过 %s 项\n' "$t" "$p"
    else
      printf '  ❌ %-20s 通过 %s 项，失败 %s 项\n' "$t" "$p" "$f"
      FAILED="$FAILED $t"
      echo "$out" | sed 's/^/        /'
    fi
  fi

  kill -9 "$SERVER_PID" 2>/dev/null
  SERVER_PID=""
  sleep 1
done

echo
echo "=================================================="
echo "  合计：通过 $TOTAL_PASS 项，失败 $TOTAL_FAIL 项"
[ -n "$FAILED" ] && echo "  失败套件：$FAILED"
[ -n "$SKIPPED" ] && echo "  未执行：$SKIPPED"
echo "=================================================="
echo
echo "=== 确认生产数据未被动过 ==="
DORM_DATA_DIR=$PROD_DIR .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.models import Account, Dorm, Member, Report
db = SessionLocal()
print(f"  生产库：宿舍 {db.query(Dorm).count()} / 人员 {db.query(Member).count()}"
      f" / 填报 {db.query(Report).count()} / 账号 {db.query(Account).count()}")
print(f"  宿舍列表：{', '.join(d.room_no for d in db.query(Dorm).order_by(Dorm.room_no).all())}")
db.close()
PY
