#!/usr/bin/env bash
# 盘点服务器上的 WireGuard（只查看，不修改）
set -u

echo "=== 1. systemd 单元 ==="
systemctl list-units --all --no-pager 2>/dev/null | grep -iE 'wg|wireguard' || echo "  没有 wg/wireguard 单元"
echo "--- 可能的 wg-quick 实例 ---"
systemctl list-unit-files --no-pager 2>/dev/null | grep -iE 'wg-quick|wireguard' || echo "  没有 wg-quick 单元文件"

echo
echo "=== 2. 网卡与状态 ==="
ip -brief addr show 2>/dev/null | grep -iE 'wg|^wg' || echo "  没有 wg 网卡"
which wg >/dev/null 2>&1 && { echo "--- wg show ---"; wg show 2>/dev/null || echo "  （wg 命令存在但取不到状态）"; } || echo "  没装 wg 命令"

echo
echo "=== 3. 配置文件 ==="
ls -la /etc/wireguard/ 2>/dev/null || echo "  没有 /etc/wireguard 目录"

echo
echo "=== 4. 相关软件包 ==="
dpkg -l 2>/dev/null | grep -iE 'wireguard|wg-' | awk '{print "  " $2, $3}' || echo "  没装 wireguard 包"

echo
echo "=== 5. iptables 里的 WireGuard 规则 ==="
iptables -S 2>/dev/null | grep -iE '51820|wg' || echo "  没有相关规则"

echo
echo "=== 6. 是否有进程在用 ==="
ps aux 2>/dev/null | grep -iE 'wg-quick|wireguard' | grep -v grep || echo "  没有相关进程"

echo
echo "=== 7. /root 下的相关脚本 ==="
ls -la /root/*wireguard* /root/*wg* 2>/dev/null || echo "  没有相关脚本"

echo
echo "=== 8. 确认宿舍服务不受影响 ==="
systemctl is-active dorm
