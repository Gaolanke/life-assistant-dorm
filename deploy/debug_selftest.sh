#!/usr/bin/env bash
# 单独在隔离实例上跑 selftest，定位卡住的步骤
set -u
cd /www/dorm || exit 1

PROD_DIR=/www/dorm-data
TEST_DIR=$(mktemp -d /tmp/dorm-selftest-XXXXXX)
TEST_PUB=8192
TEST_ADM=8193
PID=""
cleanup() { [ -n "$PID" ] && kill -9 "$PID" 2>/dev/null; rm -rf "$TEST_DIR"; }
trap cleanup EXIT

mkdir -p "$TEST_DIR/backups" "$TEST_DIR/exports" "$TEST_DIR/uploads" "$TEST_DIR/logs"
cp "$PROD_DIR/app.db" "$TEST_DIR/app.db"
[ -f "$PROD_DIR/secret.key" ] && cp "$PROD_DIR/secret.key" "$TEST_DIR/secret.key"

DORM_DATA_DIR="$TEST_DIR" DORM_PORT=$TEST_PUB DORM_ADMIN_PORT=$TEST_ADM \
  .venv/bin/python run.py > "$TEST_DIR/server.log" 2>&1 &
PID=$!

for _ in $(seq 1 60); do
  curl -fsS "http://127.0.0.1:$TEST_PUB/api/health" >/dev/null 2>&1 && break
  sleep 0.5
done
echo "隔离实例已就绪 pid=$PID"
echo

export DORM_DATA_DIR="$TEST_DIR"
export DORM_TEST_PUBLIC="http://127.0.0.1:$TEST_PUB"
export DORM_TEST_ADMIN="http://127.0.0.1:$TEST_ADM"

timeout 420 .venv/bin/python -u scripts/selftest.py "http://127.0.0.1:$TEST_ADM" "http://127.0.0.1:$TEST_PUB" 2>&1 | tail -30
echo
echo "退出码: $?"
