#!/usr/bin/env bash
# 绑定域名到隧道（A 记录删掉后重跑）
set -u
CF_DIR="/root/.cloudflared"
TUNNEL="life-assistant"
DOMAIN="xiaoaiyun.top"

echo "=== 1. 当前 DNS 记录（确认 A 记录已删） ==="
TUNNEL_ID=$(cloudflared tunnel list 2>/dev/null | awk -v t="$TUNNEL" '$2==t{print $1}')
echo "  隧道 ID: $TUNNEL_ID"

echo
echo "=== 2. 绑定域名 ==="
for h in "$DOMAIN" "www.$DOMAIN" "admin.$DOMAIN"; do
  printf '  %-24s ' "$h"
  out=$(cloudflared tunnel route dns "$TUNNEL" "$h" 2>&1 | tail -1)
  echo "$out"
done

echo
echo "=== 3. 隧道信息 ==="
cloudflared tunnel info "$TUNNEL" 2>&1 | head -20

echo
echo "=== 4. 服务状态 ==="
systemctl is-active cloudflared
journalctl -u cloudflared -n 30 --no-pager 2>/dev/null | grep -iE 'registered tunnel connection|connIndex' | tail -5 || true
