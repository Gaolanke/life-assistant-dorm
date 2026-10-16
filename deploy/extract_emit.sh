#!/usr/bin/env bash
# 提取 event-emit.html 里「回调地址校验 / plain_token」的完整说明
set -u

curl -sL -m 30 -A "Mozilla/5.0" \
  "https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/event-emit.html" \
  > /tmp/emit.html 2>/dev/null

python3 - <<'PY'
import re
from pathlib import Path

html = Path("/tmp/emit.html").read_text(encoding="utf-8", errors="replace")
text = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
text = re.sub(r"<style.*?</style>", " ", text, flags=re.S)
text = re.sub(r"<[^>]+>", " ", text)
text = re.sub(r"&quot;", '"', text)
text = re.sub(r"&amp;", "&", text)
text = re.sub(r"&lt;", "<", text)
text = re.sub(r"&gt;", ">", text)
text = re.sub(r"\s+", " ", text)

idx = text.find("plain_token")
if idx < 0:
    print("没找到 plain_token")
else:
    print(text[max(0, idx - 900) : idx + 2600].strip())
PY
