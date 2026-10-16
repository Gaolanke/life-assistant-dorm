#!/usr/bin/env bash
# 检查服务器到 Cloudflare 的连通性，以及是否已装 cloudflared
set -u

echo "=== 1. Cloudflare 主要域名连通性 ==="
for host in cloudflare.com api.cloudflare.com github.com pkg.cloudflare.com; do
  code=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "https://$host/" 2>/dev/null || echo "失败")
  printf '  %-24s -> %s\n' "$host" "$code"
done

echo
echo "=== 2. 是否已装 cloudflared ==="
command -v cloudflared >/dev/null 2>&1 && cloudflared --version || echo "  未安装"

echo
echo "=== 3. 能否下载 cloudflared（试 HEAD） ==="
for url in \
  "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" \
  "https://pkg.cloudflare.com/index.html" ; do
  code=$(curl -s -I -L -m 15 -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || echo "失败")
  printf '  %-72s -> %s\n' "$(echo "$url" | cut -c1-70)" "$code"
done

echo
echo "=== 4. 当前服务状态（确认没被影响）==="
echo -n "  dorm: "; systemctl is-active dorm
echo -n "  nginx: "; systemctl is-active nginx
echo -n "  8090: "; curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8090/
echo -n "  80 (nginx): "; curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1/
