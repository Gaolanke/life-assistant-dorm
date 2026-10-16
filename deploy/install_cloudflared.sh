#!/usr/bin/env bash
# 安装 cloudflared（Cloudflare Tunnel 客户端）
# 用 Cloudflare 官方 apt 源（GitHub 在这台机器上不通，所以不用 GitHub 下载）
set -eu

if command -v cloudflared >/dev/null 2>&1; then
  echo "已安装：$(cloudflared --version)"
  exit 0
fi

export DEBIAN_FRONTEND=noninteractive

echo "=== 1. 装依赖 ==="
apt-get install -y -q curl gnupg lsb-release ca-certificates >/dev/null 2>&1 || true

echo "=== 2. 加 Cloudflare 官方源 ==="
mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg -o /usr/share/keyrings/cloudflare-main.gpg
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" \
  > /etc/apt/sources.list.d/cloudflared.list

echo "=== 3. 安装 cloudflared ==="
apt-get update -q 2>&1 | tail -2
apt-get install -y -q cloudflared 2>&1 | tail -3

echo
echo "=== 4. 确认 ==="
cloudflared --version
systemctl is-active cloudflared 2>/dev/null || echo "服务还没配置（等你给 tunnel token）"
