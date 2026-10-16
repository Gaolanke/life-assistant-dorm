#!/usr/bin/env bash
# 用 Cloudflare Tunnel 把 xiaoaiyun.top 挂到京东云服务器上
#
# 原理：服务器主动连 Cloudflare 建一条出站隧道，Cloudflare 把域名请求送到本机，
#      **不需要备案、不需要开任何入站端口、不怕京东云的未备案域名拦截**。
#
# 用法：
#   bash deploy/setup_cloudflare_tunnel.sh <TUNNEL_TOKEN>
#   bash deploy/setup_cloudflare_tunnel.sh --status     # 看状态
#   bash deploy/setup_cloudflare_tunnel.sh --remove     # 卸载隧道
#
# Tunnel Token 从哪来：Cloudflare 控制台 → Zero Trust → Networks → Tunnels
#   → Create a tunnel → 选 Cloudflared → 复制那一长串 token
set -eu

PUBLIC_PORT="${PUBLIC_PORT:-8090}"
ADMIN_PORT="${ADMIN_PORT:-8091}"

if [ -z "${BASH_VERSION:-}" ] && command -v bash >/dev/null 2>&1; then
  exec bash "$0" "$@"
fi
[ "$(id -u)" = "0" ] || { echo "请用 root 运行"; exit 1; }

case "${1:-}" in
  --status)
    echo "=== cloudflared 版本 ==="
    cloudflared --version || true
    echo
    echo "=== 服务状态 ==="
    systemctl is-active cloudflared 2>/dev/null || echo "未运行"
    systemctl status cloudflared --no-pager 2>/dev/null | head -12 || true
    echo
    echo "=== 隧道连接情况（日志尾部）==="
    journalctl -u cloudflared -n 20 --no-pager 2>/dev/null | tail -20 || true
    echo
    echo "=== 本机服务 ==="
    printf '  8090 公开端: %s\n' "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$PUBLIC_PORT/ || echo 失败)"
    printf '  8091 管理端: %s\n' "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$ADMIN_PORT/ || echo 失败)"
    exit 0
    ;;
  --remove)
    cloudflared service uninstall 2>/dev/null || systemctl disable --now cloudflared 2>/dev/null || true
    rm -f /etc/systemd/system/cloudflared.service
    systemctl daemon-reload
    echo "已卸载 cloudflared 服务（Cloudflare 控制台里的隧道记得也删掉）"
    exit 0
    ;;
esac

TOKEN="${1:-}"
if [ -z "$TOKEN" ]; then
  echo "用法：bash $0 <TUNNEL_TOKEN>"
  echo "Token 从 Cloudflare 控制台 → Zero Trust → Networks → Tunnels 里复制"
  exit 1
fi

echo "=== 1. 确认本机服务在跑 ==="
printf '  8090 公开端: %s\n' "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$PUBLIC_PORT/ || echo 失败)"
printf '  8091 管理端: %s\n' "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$ADMIN_PORT/ || echo 失败)"

echo
echo "=== 2. 安装为系统服务（开机自启、断线自动重连） ==="
if systemctl is-active cloudflared >/dev/null 2>&1; then
  echo "  已有服务在跑，先卸掉旧的"
  cloudflared service uninstall >/dev/null 2>&1 || true
fi
cloudflared service install "$TOKEN"

echo
echo "=== 3. 启动 ==="
systemctl enable cloudflared >/dev/null 2>&1 || true
systemctl restart cloudflared
sleep 6
systemctl is-active cloudflared

echo
echo "=== 4. 连接日志 ==="
journalctl -u cloudflared -n 20 --no-pager 2>/dev/null | grep -iE 'connection|registered|error|warn' | tail -10 || true

echo
echo "=== 完成 ==="
cat <<'TIP'
  接下来在 Cloudflare 控制台确认隧道里有这几条 Public Hostname：
    xiaoaiyun.top        -> HTTP  http://127.0.0.1:8090
    www.xiaoaiyun.top    -> HTTP  http://127.0.0.1:8090
    admin.xiaoaiyun.top  -> HTTP  http://127.0.0.1:8091

  然后访问 https://xiaoaiyun.top 就应该能打开（Cloudflare 自动提供 HTTPS）
  看状态： bash deploy/setup_cloudflare_tunnel.sh --status
TIP
