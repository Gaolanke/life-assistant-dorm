#!/usr/bin/env bash
# 抓取腾讯官方 opcode / event-emit 文档，找 op=13 回调校验的回复格式
set -u

for u in \
  "https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/opcode.html" \
  "https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/event-emit.html" \
  "https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/sign.html" ; do
  echo "--- $u ---"
  curl -sL -m 30 -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" "$u" \
    | sed 's/<[^>]*>/ /g' | tr -s ' \n' ' \n' \
    | grep -oiE '(plain_token|event_ts|signature|Ed25519|hex|base64)[^ ]{0,80}' | head -25
  echo
done
