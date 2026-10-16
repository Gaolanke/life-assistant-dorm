#!/usr/bin/env bash
# 检查域名 xiaoaiyun.top 的解析与服务器 80/443 情况
set -u
cd /www/dorm || exit 1
DOMAIN="${1:-xiaoaiyun.top}"
SERVER_IP="${2:-111.228.38.170}"

echo "=== 1. 从服务器解析域名 ==="
for name in "$DOMAIN" "www.$DOMAIN" "admin.$DOMAIN"; do
  ip=$(getent ahostsv4 "$name" 2>/dev/null | awk '{print $1}' | head -1)
  if [ -n "$ip" ]; then
    if [ "$ip" = "$SERVER_IP" ]; then
      echo "  $name -> $ip  ✅ 指向本机"
    else
      echo "  $name -> $ip  ⚠️ 不是本机（$SERVER_IP）"
    fi
  else
    echo "  $name -> 解析失败（还没加解析记录）"
  fi
done

echo
echo "=== 2. 服务器本地 80/443 是否被占用 ==="
ss -lntp 2>/dev/null | grep -E ':(80|443) ' || echo "  80/443 都空闲"

echo
echo "=== 3. 是否有 Nginx ==="
command -v nginx >/dev/null 2>&1 && { echo -n "  nginx: "; nginx -v 2>&1; systemctl is-active nginx; } || echo "  nginx 未安装（之前按你的要求不装）"
command -v certbot >/dev/null 2>&1 && echo "  certbot 已安装" || echo "  certbot 未安装"

echo
echo "=== 4. 当前对外服务 ==="
echo -n "  8090 页面: "; curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8090/
echo -n "  8091 页面: "; curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8091/
echo -n "  dorm 服务: "; systemctl is-active dorm

echo
echo "=== 5. 备案状态探测（大陆机房对未备案域名会拦 80） ==="
echo "  （这个只能从外网访问时才能确认，服务器自己测不出来）"
echo "  参考：京东云华北/华东等大陆地域，域名必须完成 ICP 备案才能用 80/443 对外服务"
