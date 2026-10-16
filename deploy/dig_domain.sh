#!/usr/bin/env bash
# 从服务器用公共 DNS 查 xiaoaiyun.top 的解析情况
set -u
DOMAIN="${1:-xiaoaiyun.top}"

echo "=== A 记录（公共 DNS） ==="
for ns in 223.5.5.5 119.29.29.29 114.114.114.114; do
  printf '  @%-16s ' "$ns"
  ip=$(timeout 8 nslookup -type=A "$DOMAIN" "$ns" 2>/dev/null | awk '/^Address: /{print $2}' | grep -v '^$' | tail -n +1 | head -3 | tr '\n' ' ')
  if [ -z "$ip" ]; then
    echo "无 A 记录 / 解析失败"
  else
    echo "$ip"
  fi
done

echo
echo "=== NS 记录（域名托管在哪） ==="
timeout 8 nslookup -type=NS "$DOMAIN" 223.5.5.5 2>/dev/null | grep -iE 'nameserver|name host' | head -5 || echo "  查询失败"

echo
echo "=== 权威服务器上直接查 A ==="
for ns in freens1.jdgslb.com freens2.jdgslb.com; do
  printf '  @%-24s ' "$ns"
  out=$(timeout 8 nslookup -type=A "$DOMAIN" "$ns" 2>/dev/null | grep -A2 'Name:' | tail -2 | tr '\n' ' ')
  echo "${out:-无记录}"
done

echo
echo "=== 结论 ==="
if timeout 8 nslookup -type=A "$DOMAIN" 223.5.5.5 2>/dev/null | grep -q 'Address'; then
  echo "  域名已有 A 记录"
else
  echo "  ❗ 域名没有 A 记录：需要到京东云 DNS 控制台添加解析，指向 111.228.38.170"
fi
