#!/usr/bin/env bash
# 检查域名解析 + 80 端口是否真的能用（未备案可能被云平台拦）
set -u
DOMAIN="${1:-xiaoaiyun.top}"
MY_IP=$(curl -s -m 8 ifconfig.me 2>/dev/null || echo "")

echo "=== 1. 各子域解析（权威 + 公共） ==="
for name in "$DOMAIN" "www.$DOMAIN" "admin.$DOMAIN"; do
  auth=$(timeout 6 nslookup -type=A "$name" freens1.jdgslb.com 2>/dev/null | awk '/^Address: /{print $2}' | tail -1)
  pub=$(timeout 6 nslookup -type=A "$name" 223.5.5.5 2>/dev/null | awk '/^Address: /{print $2}' | tail -1)
  printf '  %-28s 权威=%-16s 公共=%s\n' "$name" "${auth:-无}" "${pub:-无}"
done

echo
echo "=== 2. 本机 80/443 监听 ==="
ss -lntp 2>/dev/null | grep -E ':(80|443) ' || echo "  80/443 未监听（Nginx 还没配）"

echo
echo "=== 3. 从服务器自己访问域名（测 80 是否被拦） ==="
for url in "http://$DOMAIN/" "http://$DOMAIN:$?" ; do :; done
printf '  http://%s/            -> %s\n' "$DOMAIN" "$(curl -s -m 10 -o /dev/null -w '%{http_code}' "http://$DOMAIN/" 2>/dev/null || echo '失败')"
printf '  http://%s:8090/       -> %s\n' "$DOMAIN" "$(curl -s -m 10 -o /dev/null -w '%{http_code}' "http://$DOMAIN:8090/" 2>/dev/null || echo '失败')"
printf '  http://%s:8091/       -> %s\n' "$DOMAIN" "$(curl -s -m 10 -o /dev/null -w '%{http_code}' "http://$DOMAIN:8091/" 2>/dev/null || echo '失败')"

echo
echo "=== 4. 结论 ==="
c80=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "http://$DOMAIN/" 2>/dev/null || echo 000)
c8090=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "http://$DOMAIN:8090/" 2>/dev/null || echo 000)
if [ "$c8090" = "200" ]; then
  echo "  ✅ 域名 + 8090 端口可用（备用地址 http://$DOMAIN:8090）"
fi
if [ "$c80" = "200" ] || [ "$c80" = "301" ] || [ "$c80" = "302" ]; then
  echo "  ✅ 80 端口可达"
elif [ "$c80" = "000" ]; then
  echo "  ⚠️ 80 端口连不上（未监听，或被云平台拦）——先配 Nginx 再测"
else
  echo "  80 端口返回 $c80"
fi
