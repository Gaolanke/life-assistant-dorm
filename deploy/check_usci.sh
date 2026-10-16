#!/usr/bin/env bash
# 检查免费域名 xiaoaiyun.us.ci 的解析与 DNS 托管情况
set -u
DOMAIN="${1:-xiaoaiyun.us.ci}"

echo "=== 1. 公共 DNS 查 A / CNAME ==="
for ns in 223.5.5.5 119.29.29.29 1.1.1.1; do
  printf '  @%-16s ' "$ns"
  out=$(timeout 8 nslookup -type=A "$DOMAIN" "$ns" 2>/dev/null | grep -A2 'Name:' | tail -3 | tr '\n' ' ' | sed 's/  */ /g')
  echo "${out:-无记录}"
done

echo
echo "=== 2. 查 CNAME ==="
timeout 8 nslookup -type=CNAME "$DOMAIN" 223.5.5.5 2>/dev/null | grep -iE 'canonical|alias' | head -3 || echo "  无 CNAME"

echo
echo "=== 3. 查 NS（看域名托管在哪） ==="
timeout 10 nslookup -type=NS "$DOMAIN" 223.5.5.5 2>/dev/null | grep -iE 'nameserver' | head -5 || echo "  查询失败"
echo "--- 父域 us.ci 的 NS ---"
timeout 10 nslookup -type=NS us.ci 223.5.5.5 2>/dev/null | grep -iE 'nameserver' | head -5 || echo "  查询失败"

echo
echo "=== 4. 结论 ==="
a=$(timeout 8 nslookup -type=A "$DOMAIN" 223.5.5.5 2>/dev/null | awk '/^Address: /{print $2}' | tail -1)
if [ -n "$a" ]; then
  echo "  解析到: $a"
  if [ "$a" = "111.228.38.170" ]; then
    echo "  ✅ 已指向你的服务器（但未备案的话会被京东云拦）"
  fi
else
  echo "  域名还没有 A 记录"
fi
