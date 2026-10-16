#!/usr/bin/env bash
# 查网关任务为什么停了
set -u
echo "=== service.log 最后 40 行 ==="
tail -40 /www/dorm-data/logs/service.log

echo
echo "=== 含 UnboundLocal / Traceback / 异常 的行 ==="
grep -nE 'UnboundLocal|Traceback|Error|Exception|Task exception' /www/dorm-data/logs/service.log | tail -20

echo
echo "=== journalctl 里的异常 ==="
journalctl -u dorm -n 60 --no-pager 2>/dev/null | grep -iE 'unbound|traceback|error|exception' | tail -15

echo
echo "=== 当前进程内的任务（看是否真的没有 ws 连接）==="
ss -tnp 2>/dev/null | grep -E ':443' | head -10 || echo "  没有到 443 的连接"
