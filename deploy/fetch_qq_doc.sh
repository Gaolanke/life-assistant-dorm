#!/usr/bin/env bash
# 从服务器抓取腾讯官方回调校验文档，确认签名算法
set -u

echo "=== 1. 官方文档：安全与授权（签名） ==="
curl -s -m 25 "https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/sign.html" \
  | sed 's/<[^>]*>/ /g' | tr -s ' \n' ' \n' | grep -iE 'plain_token|event_ts|Ed25519|SHA256|签名|seed|私钥' | head -40

echo
echo "=== 2. 官方文档：事件订阅与回调 ==="
curl -s -m 25 "https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/event-emit.html" \
  | sed 's/<[^>]*>/ /g' | tr -s ' \n' ' \n' | grep -iE 'plain_token|event_ts|signature|校验|回调地址' | head -30
