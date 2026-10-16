#!/usr/bin/env bash
# 提取官方文档里 op=13 回调校验的完整说明
set -u

echo "################ 1. opcode.html 中 op=13 附近 ################"
curl -sL -m 30 -A "Mozilla/5.0" \
  "https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/opcode.html" \
  > /tmp/op.html 2>/dev/null
python3 - <<'PY'
import re
from pathlib import Path

html = Path("/tmp/op.html").read_text(encoding="utf-8", errors="replace")
text = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
text = re.sub(r"<style.*?</style>", " ", text, flags=re.S)
text = re.sub(r"<[^>]+>", " ", text)
text = re.sub(r"&quot;", '"', text)
text = re.sub(r"&amp;", "&", text)
text = re.sub(r"\s+", " ", text)

for kw in ("plain_token", "13", "回调"):
    for m in re.finditer(re.escape(kw), text):
        seg = text[max(0, m.start() - 320) : m.start() + 420]
        if "plain_token" in seg or "校验" in seg:
            print("=== 片段 ===")
            print(seg.strip())
            print()
            break
PY

echo "################ 2. sign.html 中 Ed25519 附近 ################"
curl -sL -m 30 -A "Mozilla/5.0" \
  "https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/sign.html" \
  > /tmp/sign.html 2>/dev/null
python3 - <<'PY'
import re
from pathlib import Path

html = Path("/tmp/sign.html").read_text(encoding="utf-8", errors="replace")
text = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
text = re.sub(r"<style.*?</style>", " ", text, flags=re.S)
text = re.sub(r"<[^>]+>", " ", text)
text = re.sub(r"&quot;", '"', text)
text = re.sub(r"&amp;", "&", text)
text = re.sub(r"\s+", " ", text)

idx = text.find("Ed25519")
if idx >= 0:
    print(text[max(0, idx - 200) : idx + 2200].strip())
PY
