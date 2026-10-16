#!/usr/bin/env bash
# 安装/卸载系统定时通知（不占用程序进程，服务器重启也不会丢）
#
# 用法：
#   bash deploy/install_cron.sh              # 安装：每天 22:00 提醒、22:40 汇报
#   bash deploy/install_cron.sh --remove     # 卸载
#   bash deploy/install_cron.sh --test       # 立即跑一次，看效果
#
# 也可以通过环境变量调整：
#   REPORT_TIME=22:40 REMIND_TIME=22:00 APP_DIR=/www/dorm DATA_DIR=/www/dorm-data
set -eu

APP_DIR="${APP_DIR:-/www/dorm}"
DATA_DIR="${DATA_DIR:-/www/dorm-data}"
REPORT_TIME="${REPORT_TIME:-22:40}"
REMIND_TIME="${REMIND_TIME:-22:00}"
TAG="# life-assistant-notify"

if [ -z "${BASH_VERSION:-}" ] && command -v bash >/dev/null 2>&1; then
  exec bash "$0" "$@"
fi

PY="$APP_DIR/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "找不到 $PY，请先确认程序装在 $APP_DIR"
  exit 1
fi

mkdir -p "$DATA_DIR/logs"

case "${1:-}" in
  --remove)
    crontab -l 2>/dev/null | grep -v "$TAG" > /tmp/cron.new || true
    crontab /tmp/cron.new && rm -f /tmp/cron.new
    echo "已移除生活助手的定时通知任务"
    exit 0
    ;;
  --test)
    echo "== 通道自检 =="
    cd "$APP_DIR" && DORM_DATA_DIR="$DATA_DIR" "$PY" scripts/notify_push.py check || true
    echo
    echo "== 立即发一次当天汇总 =="
    cd "$APP_DIR" && DORM_DATA_DIR="$DATA_DIR" "$PY" scripts/notify_push.py report || true
    exit 0
    ;;
esac

RH="${REPORT_TIME%%:*}"
RM="${REPORT_TIME##*:}"
NH="${REMIND_TIME%%:*}"
NM="${REMIND_TIME##*:}"

TMP_CRON="$(mktemp)"
crontab -l 2>/dev/null | grep -v "$TAG" > "$TMP_CRON" || true
cat >> "$TMP_CRON" <<EOF
$NM $NH * * * cd $APP_DIR && DORM_DATA_DIR=$DATA_DIR $PY scripts/notify_push.py remind >> $DATA_DIR/logs/notify.log 2>&1 $TAG
$RM $RH * * * cd $APP_DIR && DORM_DATA_DIR=$DATA_DIR $PY scripts/notify_push.py report >> $DATA_DIR/logs/notify.log 2>&1 $TAG
EOF
crontab "$TMP_CRON"
rm -f "$TMP_CRON"

echo "已安装定时通知："
echo "  $REMIND_TIME  提醒未填报寝室"
echo "  $REPORT_TIME  发当天填报汇总到 QQ 群"
echo "日志： $DATA_DIR/logs/notify.log"
echo
echo "当前 crontab："
crontab -l | grep "$TAG"
echo
echo "建议先跑一次看效果： bash deploy/install_cron.sh --test"
