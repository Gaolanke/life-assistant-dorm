#!/usr/bin/env bash
# 看 message_format.md 里群消息相关字段（mention_everyone 等）
set -u

curl -sL -m 30 \
  "https://cdn.jsdelivr.net/gh/tencent-connect/bot-docs@master/docs/develop/api-v2/server-inter/message/message_format.md" \
  > /tmp/fmt.md 2>/dev/null

echo "=== 文件大小 ==="
wc -c /tmp/fmt.md

echo
echo "=== mention / everyone 相关全部片段 ==="
grep -n -i -B4 -A6 'mention' /tmp/fmt.md | head -60

echo
echo "=== 群消息相关小节标题 ==="
grep -n '^#' /tmp/fmt.md | head -20
