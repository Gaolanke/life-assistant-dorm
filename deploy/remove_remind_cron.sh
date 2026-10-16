#!/usr/bin/env bash
# 删除「未填报提醒」的 cron 任务，保留「每晚汇报」
set -eu

echo "=== 删除前 ==="
crontab -l 2>/dev/null | grep -E 'life-assistant' || echo "  (无)"

# 备份当前 crontab
STAMP=$(date +%Y%m%d_%H%M%S)
crontab -l > "/root/crontab-backup-${STAMP}.txt" 2>/dev/null || true

# 过滤掉 remind 那一行，保留其他（含 report）
crontab -l 2>/dev/null | grep -v 'notify_push.py --no-email remind' | crontab -

echo
echo "=== 删除后 ==="
crontab -l 2>/dev/null | grep -E 'life-assistant' || echo "  (无 life-assistant 任务)"
echo
echo "  完整 crontab："
crontab -l 2>/dev/null | sed 's/^/    /' || echo "    (空)"

echo
echo "  备份文件: /root/crontab-backup-${STAMP}.txt"
