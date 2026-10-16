#!/usr/bin/env bash
# 验证「域名访问 / IP 访问」两种情况下，后端算出来的公开端和管理端地址
set -u

show() {
  label="$1"; shift
  echo "=== $label ==="
  curl -s "$@" http://127.0.0.1:8090/api/system/info \
    | python3 -c '
import json, sys
d = json.load(sys.stdin)
print("  public_base :", d.get("public_base"))
print("  admin_base  :", d.get("admin_base"))
print("  via_domain  :", d.get("via_domain"))
'
  echo
}

show "① 用域名访问公开端（xiaoaiyun.top）" \
  -H "Host: xiaoaiyun.top" -H "X-Forwarded-Proto: https"

show "② 用域名访问管理端（admin.xiaoaiyun.top）" \
  -H "Host: admin.xiaoaiyun.top" -H "X-Forwarded-Proto: https"

show "③ 用 IP 访问" 

echo "=== 服务状态 ==="
echo -n "  dorm: "; systemctl is-active dorm
echo -n "  cloudflared: "; systemctl is-active cloudflared
echo -n "  nginx: "; systemctl is-active nginx
