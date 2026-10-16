#!/usr/bin/env bash
# 查腾讯官方文档：群消息如何 @ 全体成员
set -u

for u in \
  "https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/send-receive/send.html" \
  "https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/send-receive/send-message.html" \
  "https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/type/message.html" ; do
  echo "--- $u ---"
  curl -sL -m 30 -A "Mozilla/5.0" "$u" \
    | sed 's/<[^>]*>/ /g' | tr -s ' \n' ' \n' \
    | grep -oiE '(<@[^ ]{0,40}|@全体|全体成员|mention|@all|at_?all)[^ ]{0,60}' | head -15
  echo
done

echo "=== 尝试搜 '@全体' 的用法说明 ==="
curl -sL -m 30 -A "Mozilla/5.0" \
  "https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/send-receive/send.html" \
  | sed 's/<[^>]*>/ /g' | tr -s ' \n' ' \n' | grep -iE 'content|<@|msg_seq|msg_id' | head -20
