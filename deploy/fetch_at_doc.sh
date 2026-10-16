#!/usr/bin/env bash
# 从腾讯文档源码（GitHub 仓库）找 @ 语法
set -u

try() {
  label="$1"; url="$2"
  echo "--- $label ---"
  curl -sL -m 30 "$url" 2>/dev/null | head -c 8000 | grep -iE '@|mention|all' | head -25
  echo
}

try "message_format.md (gh-proxy)" \
  "https://gh-proxy.com/https://raw.githubusercontent.com/tencent-connect/bot-docs/master/docs/develop/api-v2/server-inter/message/message_format.md"

try "message_format.md (jsdelivr)" \
  "https://cdn.jsdelivr.net/gh/tencent-connect/bot-docs@master/docs/develop/api-v2/server-inter/message/message_format.md"

try "text-chain.md (jsdelivr)" \
  "https://cdn.jsdelivr.net/gh/tencent-connect/bot-docs@master/docs/develop/api-v2/server-inter/message/trans/text-chain.md"

try "内嵌格式页" \
  "https://bot.qq.com/wiki/develop/api-v2/server-inter/channel/message/format.html"
