#!/usr/bin/env bash
# 测服务器到各外网服务的连通性（判断哪条通知通道可行）
set -u

check_tcp() {
  host=$1; port=$2
  if timeout 6 bash -c "cat < /dev/null > /dev/tcp/$host/$port" 2>/dev/null; then
    printf '  %-26s:%-4s 可连 ✅\n' "$host" "$port"
  else
    printf '  %-26s:%-4s 不通 ❌\n' "$host" "$port"
  fi
}

check_http() {
  url=$1
  code=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "$url" 2>/dev/null || echo "超时")
  printf '  %-34s -> %s\n' "$url" "$code"
}

echo "=== 邮件通道（SMTP） ==="
check_tcp smtp.qq.com 465
check_tcp smtp.qq.com 587
check_tcp smtp.163.com 465

echo
echo "=== 腾讯 QQ 机器人 API ==="
check_tcp bots.qq.com 443
check_tcp api.sgroup.qq.com 443

echo
echo "=== 其他常用外网 ==="
check_http https://www.baidu.com/
check_http https://pypi.org/
check_http https://qyapi.weixin.qq.com/
check_http https://oapi.dingtalk.com/
check_http https://sc.ftqq.com/

echo
echo "=== 服务器出口 IP ==="
curl -s -m 8 https://ifconfig.me 2>/dev/null || echo "取不到"
echo
