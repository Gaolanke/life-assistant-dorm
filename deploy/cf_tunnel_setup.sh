#!/usr/bin/env bash
# 创建并启动 Cloudflare Tunnel（配置驱动，本地管理的隧道）
set -eu

DOMAIN="${DOMAIN:-xiaoaiyun.top}"
TUNNEL="${TUNNEL:-life-assistant}"
CF_DIR="/root/.cloudflared"
PUBLIC_PORT="${PUBLIC_PORT:-8090}"
ADMIN_PORT="${ADMIN_PORT:-8091}"

echo "=== 1. 确认已授权 ==="
if [ ! -f "$CF_DIR/cert.pem" ]; then
  echo "  ❗ 没有 cert.pem，请先跑 bash /root/cf_login.sh 并完成浏览器授权"
  exit 1
fi
echo "  ✅ 已授权（cert.pem 存在）"

echo
echo "=== 2. 创建隧道 ==="
if [ -f "$CF_DIR/$TUNNEL.json" ] 2>/dev/null; then
  echo "  隧道已存在"
fi
EXISTING=$(cloudflared tunnel list 2>/dev/null | awk -v t="$TUNNEL" '$2==t{print $1}')
if [ -n "$EXISTING" ]; then
  echo "  已存在同名隧道：$EXISTING"
  UUID="$EXISTING"
else
  cloudflared tunnel create "$TUNNEL" 2>&1 | tail -3
  UUID=$(cloudflared tunnel list 2>/dev/null | awk -v t="$TUNNEL" '$2==t{print $1}')
fi
[ -n "$UUID" ] || { echo "  ❗ 创建失败"; cloudflared tunnel list; exit 1; }
echo "  隧道 ID: $UUID"

CRED="$CF_DIR/$UUID.json"
ls -l "$CRED" >/dev/null 2>&1 || { echo "  ❗ 找不到凭据文件 $CRED"; exit 1; }

echo
echo "=== 3. 写配置文件 ==="
cat > "$CF_DIR/config.yml" <<EOF
# 生活助手 · Cloudflare Tunnel
# 域名 $DOMAIN  ->  本机 $PUBLIC_PORT（同学填报）
# admin.$DOMAIN ->  本机 $ADMIN_PORT（管理端）
tunnel: $UUID
credentials-file: $CRED

ingress:
  - hostname: $DOMAIN
    service: http://127.0.0.1:$PUBLIC_PORT
  - hostname: www.$DOMAIN
    service: http://127.0.0.1:$PUBLIC_PORT
  - hostname: admin.$DOMAIN
    service: http://127.0.0.1:$ADMIN_PORT
  - service: http_status:404
EOF
cat "$CF_DIR/config.yml"

echo
echo "=== 4. 校验配置 ==="
cloudflared tunnel ingress validate --config "$CF_DIR/config.yml" 2>&1 | tail -3

echo
echo "=== 5. 绑定域名（DNS） ==="
for h in "$DOMAIN" "www.$DOMAIN" "admin.$DOMAIN"; do
  printf '  %-26s ' "$h"
  out=$(cloudflared tunnel route dns "$TUNNEL" "$h" 2>&1 | tail -1)
  echo "$out"
done

echo
echo "=== 6. 安装为系统服务 ==="
if systemctl list-unit-files 2>/dev/null | grep -q '^cloudflared.service'; then
  echo "  服务已存在，直接重启"
else
  cloudflared --config "$CF_DIR/config.yml" service install 2>&1 | tail -3
fi
systemctl enable cloudflared >/dev/null 2>&1 || true
systemctl restart cloudflared
sleep 8
echo -n "  服务状态: "; systemctl is-active cloudflared

echo
echo "=== 7. 连接日志 ==="
journalctl -u cloudflared -n 30 --no-pager 2>/dev/null | grep -iE 'registered|connection|error|warn|serve' | tail -8 || true

echo
echo "=== 8. 自检 ==="
printf '  本机 8090: %s\n' "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$PUBLIC_PORT/ || echo 失败)"
printf '  本机 8091: %s\n' "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$ADMIN_PORT/ || echo 失败)"
echo
echo "隧道 ID: $UUID"
echo "配置文件: $CF_DIR/config.yml"
