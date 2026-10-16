#!/usr/bin/env bash
# 查 xiaoaiyun.top 的 NS 到底改了没有（直接问 .top 顶级域权威）
set -u
DOMAIN="${1:-xiaoaiyun.top}"

echo "=== 1. 找 .top 顶级域的权威服务器 ==="
TLD_NS=$(timeout 10 nslookup -type=NS top 223.5.5.5 2>/dev/null | awk '/nameserver/{print $NF}' | head -3)
echo "  $TLD_NS"

echo
echo "=== 2. 直接问顶级域：这个域名委派给谁 ==="
for ns in $TLD_NS; do
  printf '  @%-28s ' "$ns"
  out=$(timeout 10 nslookup -type=NS "$DOMAIN" "$ns" 2>/dev/null | awk '/nameserver/{print $NF}' | tr '\n' ' ')
  echo "${out:-无}"
done

echo
echo "=== 3. 公共 DNS 缓存 ==="
for ns in 223.5.5.5 1.1.1.1 8.8.8.8; do
  printf '  @%-14s ' "$ns"
  out=$(timeout 8 nslookup -type=NS "$DOMAIN" "$ns" 2>/dev/null | awk '/nameserver/{print $NF}' | tr '\n' ' ')
  echo "${out:-无}"
done

echo
echo "=== 4. 结论 ==="
DELEGATED=$(timeout 10 nslookup -type=NS "$DOMAIN" "${TLD_NS%% *}" 2>/dev/null | awk '/nameserver/{print $NF}' | tr '\n' ' ')
if echo "$DELEGATED" | grep -qi cloudflare; then
  echo "  ✅ 已经委派给 Cloudflare：$DELEGATED"
elif echo "$DELEGATED" | grep -qi jdgslb; then
  echo "  ❌ 还委派在京东云：$DELEGATED"
  echo "     → 需要在【域名注册商】处修改 DNS 服务器，不是在京东云 DNS 里加记录"
else
  echo "  ⚠️ 委派情况：${DELEGATED:-查询不到}"
fi
