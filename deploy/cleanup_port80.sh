#!/usr/bin/env bash
# 停止服务器上遗留的部署进程，并把 Nginx 从 80 端口摘下来（按用户要求不放 80 端口）。
# 用法： bash /root/dorm_cleanup.sh
set -u

SELF=$$
echo "== 停止遗留的 pip / install.sh / uvicorn 进程 =="
for pid in $(ps -eo pid=,args= | grep -E 'deploy/install\.sh|pip install -r requirements\.txt|/www/dorm/\.venv/bin/(python|uvicorn)' | grep -v grep | awk '{print $1}'); do
  [ "$pid" = "$SELF" ] && continue
  if [ -r "/proc/$pid/cmdline" ] && tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q 'dorm_cleanup'; then
    continue
  fi
  echo "  结束进程 $pid: $(tr '\0' ' ' < /proc/$pid/cmdline | cut -c1-90)"
  kill -9 "$pid" 2>/dev/null || true
done

echo "== 摘掉 80 端口（停用 nginx） =="
if systemctl list-unit-files | grep -q '^nginx\.service'; then
  systemctl stop nginx 2>/dev/null || true
  systemctl disable nginx 2>/dev/null || true
  echo "  nginx 已停止并取消开机自启"
else
  echo "  没有安装 nginx 服务"
fi

sleep 2
echo "== 结果 =="
if ss -lntp 2>/dev/null | grep -q ':80 '; then
  ss -lntp | grep ':80 '
else
  echo "  80 端口已空闲"
fi
echo "  当前监听端口："
ss -lntp 2>/dev/null | awk 'NR>1 {print "   ", $4}' | sort -u
echo "== 完成 =="
