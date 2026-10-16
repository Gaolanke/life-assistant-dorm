#!/usr/bin/env bash
# 彻底删除服务器上的 WireGuard（先备份配置，再停服务、删配置、删包）
set -u

echo "=== 0. 先备份（配置和脚本都存到 /root） ==="
STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP="/root/wireguard-backup-${STAMP}.tar.gz"
tar -czf "$BACKUP" /etc/wireguard 2>/dev/null || true
[ -f /root/wireguard.sh ] && tar -rf /dev/null 2>/dev/null || true
if [ -f /root/wireguard.sh ]; then
  cp /root/wireguard.sh "/root/wireguard.sh.bak-${STAMP}" 2>/dev/null || true
fi
ls -lh "$BACKUP" 2>/dev/null && echo "  备份完成：$BACKUP" || echo "  （没有配置可备份）"

echo
echo "=== 1. 停掉并禁用服务 ==="
for unit in wg-quick@wg0 wg-quick@wg0.service wireguard; do
  if systemctl list-unit-files 2>/dev/null | grep -q "^${unit%%.service}"; then
    systemctl stop "$unit" 2>/dev/null && echo "  已停止 $unit" || true
    systemctl disable "$unit" 2>/dev/null && echo "  已禁用 $unit" || true
  fi
done
systemctl daemon-reload
echo "  当前 wg 相关单元："
systemctl list-units --all --no-pager 2>/dev/null | grep -iE 'wg-quick|wireguard' || echo "    无"

echo
echo "=== 2. 关掉网卡 ==="
if command -v wg-quick >/dev/null 2>&1 && [ -f /etc/wireguard/wg0.conf ]; then
  wg-quick down wg0 2>/dev/null && echo "  wg-quick down wg0 完成" || echo "  wg-quick down 失败（可能已经关了）"
fi
if ip link show wg0 >/dev/null 2>&1; then
  ip link delete wg0 2>/dev/null && echo "  已删除 wg0 网卡" || echo "  删网卡失败"
fi
ip -brief addr show 2>/dev/null | grep -i wg || echo "  已没有 wg 网卡 ✅"

echo
echo "=== 3. 删除 iptables 里的 51820 规则 ==="
iptables -D INPUT -p udp -m udp --dport 51820 -j ACCEPT 2>/dev/null && echo "  已删除 UDP 51820 放行规则" || echo "  规则不存在或已删除"
iptables -S 2>/dev/null | grep -iE '51820|wg' || echo "  没有残留规则 ✅"
command -v netfilter-persistent >/dev/null 2>&1 && netfilter-persistent save >/dev/null 2>&1 && echo "  已保存 iptables 规则" || true

echo
echo "=== 4. 删除配置目录 ==="
rm -rf /etc/wireguard && echo "  已删除 /etc/wireguard"
ls -d /etc/wireguard 2>/dev/null || echo "  确认不存在 ✅"

echo
echo "=== 5. 卸载软件包 ==="
export DEBIAN_FRONTEND=noninteractive
apt-get purge -y -q wireguard wireguard-tools wireguard-dkms 2>&1 | tail -4
apt-get autoremove -y -q 2>&1 | tail -2
echo "--- 剩余相关包 ---"
dpkg -l 2>/dev/null | grep -iE 'wireguard' || echo "  已全部卸载 ✅"

echo
echo "=== 6. 删除 /root 下的一键脚本 ==="
rm -f /root/wireguard.sh && echo "  已删除 /root/wireguard.sh（备份在 /root/wireguard.sh.bak-*）"
rm -f /root/diag_wireguard.sh
ls /root/*wireguard* 2>/dev/null || echo "  只剩备份文件"

echo
echo "=== 7. 最终确认 ==="
echo -n "  wg 网卡："; ip -brief addr show 2>/dev/null | grep -ci wg || echo "0 个"
echo -n "  wg 进程："; pgrep -c -f 'wg-quick|wireguard' 2>/dev/null || echo "0 个"
echo -n "  dorm 服务："; systemctl is-active dorm
echo -n "  8091 页面："; curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8091/
echo -n "  QQ 长连接："; curl -s http://127.0.0.1:8091/api/qqbot/status | grep -o '"gateway_running":[a-z]*'
echo
echo "  备份文件："
ls -lh /root/wireguard-backup-*.tar.gz 2>/dev/null || echo "    （无）"
