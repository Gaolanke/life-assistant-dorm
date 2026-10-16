#!/usr/bin/env bash
# 多种途径抓取 QQ 机器人回调签名的参考实现
set -u

try() {
  label="$1"; url="$2"
  echo "--- $label ---"
  body=$(curl -sL -m 25 "$url" 2>/dev/null | head -c 4000)
  if [ -z "$body" ]; then
    echo "  （无内容）"
    return
  fi
  echo "$body" | grep -iE 'plain_token|event_ts|signature|ed25519|SigningKey|sha256|seed' | head -20
}

try "raw.githubusercontent" \
  "https://raw.githubusercontent.com/AstrBotDevs/AstrBot/master/astrbot/core/platform/sources/qqofficial_webhook/qo_webhook_server.py"

try "ghproxy 镜像" \
  "https://ghproxy.net/https://raw.githubusercontent.com/AstrBotDevs/AstrBot/master/astrbot/core/platform/sources/qqofficial_webhook/qo_webhook_server.py"

try "gh-proxy 镜像" \
  "https://gh-proxy.com/https://raw.githubusercontent.com/AstrBotDevs/AstrBot/master/astrbot/core/platform/sources/qqofficial_webhook/qo_webhook_server.py"

try "jsdelivr CDN" \
  "https://cdn.jsdelivr.net/gh/AstrBotDevs/AstrBot@master/astrbot/core/platform/sources/qqofficial_webhook/qo_webhook_server.py"

try "gitee 搜索" \
  "https://gitee.com/api/v5/search/repositories?q=qqbot%20webhook&per_page=3"

echo
echo "=== 官方文档（尝试不同 UA）==="
curl -s -m 25 -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" \
  "https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/sign.html" \
  | sed 's/<[^>]*>/ /g' | tr -s ' ' | grep -oiE '(plain_token|event_ts|Ed25519|SHA256|签名)[^。]{0,120}' | head -25
