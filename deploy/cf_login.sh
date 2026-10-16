#!/usr/bin/env bash
# 在服务器上发起 cloudflared 授权（后台跑，输出到文件，SSH 可以正常断开）
set -u
mkdir -p /root/.cloudflared
chmod 700 /root/.cloudflared
rm -f /root/.cloudflared/login.log /root/.cloudflared/cert.pem
pkill -f 'cloudflared tunnel login' 2>/dev/null || true
sleep 1

setsid nohup cloudflared tunnel login \
  > /root/.cloudflared/login.log 2>&1 < /dev/null &
disown 2>/dev/null || true

sleep 8
echo "=== 登录进程 ==="
pgrep -af 'cloudflared tunnel login' || echo "  进程没起来"
echo
echo "=== 登录日志 ==="
cat /root/.cloudflared/login.log 2>/dev/null || echo "  日志为空"
echo
echo "=== 授权链接 ==="
grep -o 'https://[^ ]*' /root/.cloudflared/login.log 2>/dev/null | head -1 || echo "  还没输出链接"
