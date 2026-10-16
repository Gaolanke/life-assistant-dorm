#!/usr/bin/env bash
# 问 Cloudflare 权威服务器：xiaoaiyun.top 上有没有解析记录
set -u
DOMAIN="${1:-xiaoaiyun.top}"
NS1="zita.ns.cloudflare.com"
NS2="aragorn.ns.cloudflare.com"

echo "=== A 记录 ==="
for ns in "$NS1" "$NS2"; do
  printf '  @%-26s ' "$ns"
  out=$(timeout 8 nslookup -type=A "$DOMAIN" "$ns" 2>/dev/null | grep -A3 'Name:' | tail -3 | tr '\n' ' ' | sed 's/  */ /g')
  echo "${out:-（无记录）}"
done

echo
echo "=== CNAME 记录 ==="
for ns in "$NS1" "$NS2"; do
  printf '  @%-26s ' "$ns"
  out=$(timeout 8 nslookup -type=CNAME "$DOMAIN" "$ns" 2>/dev/null | grep -iE 'canonical|alias' | tr '\n' ' ')
  echo "${out:-（无记录）}"
done

echo
echo "=== www 子域 ==="
printf '  www  -> '
timeout 8 nslookup -type=A "www.$DOMAIN" "$NS1" 2>/dev/null | grep -A2 'Name:' | tail -2 | tr '\n' ' '
echo
printf '  admin-> '
timeout 8 nslookup -type=A "admin.$DOMAIN" "$NS1" 2>/dev/null | grep -A2 'Name:' | tail -2 | tr '\n' ' '
echo

echo
echo "=== 判断 ==="
a=$(timeout 8 nslookup -type=A "$DOMAIN" "$NS1" 2>/dev/null | awk '/^Address: /{print $2}' | grep -v '^$' | tail -1)
if [ -n "$a" ]; then
  echo "  域名已有 A 记录：$a"
  if [ "$a" = "111.228.38.170" ]; then
    echo "  （直接指向你的服务器：未备案会被京东云拦，建议走 Tunnel）"
  else
    echo "  （返回 $a：如果这是 Cloudflare 的 IP，说明橙云代理已开启，好！）"
  fi
else
  echo "  Cloudflare 上还没有解析记录 → 需要在 Cloudflare 里加 DNS 记录（或建 Tunnel 时自动加）"
fi
