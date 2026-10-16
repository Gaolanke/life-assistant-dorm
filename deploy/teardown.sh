#!/usr/bin/env bash
# 清理服务器上这次部署尝试留下的东西：服务、目录、残留进程。
# 用法： bash /root/dorm_teardown.sh
set -u

echo "== 1. 停止并删除 systemd 服务 =="
if systemctl list-unit-files 2>/dev/null | grep -q '^dorm\.service'; then
  systemctl stop dorm 2>/dev/null || true
  systemctl disable dorm 2>/dev/null || true
  systemctl reset-failed dorm 2>/dev/null || true
  rm -f /etc/systemd/system/dorm.service
  systemctl daemon-reload
  echo "  已删除 dorm.service"
else
  echo "  没有 dorm 服务"
fi

echo "== 2. 停用 Nginx（避免占用 80 端口） =="
if systemctl list-unit-files 2>/dev/null | grep -q '^nginx\.service'; then
  systemctl stop nginx 2>/dev/null || true
  systemctl disable nginx 2>/dev/null || true
  rm -f /etc/nginx/sites-enabled/dorm
  rm -f /etc/nginx/sites-available/dorm
  echo "  已停止并取消开机自启，删除了反代配置"
else
  echo "  没有 nginx"
fi

echo "== 3. 结束残留进程 =="
SELF=$$
for pid in $(ps -eo pid=,args= | grep -E '/www/dorm|deploy/install\.sh|pip install -r requirements' | grep -v grep | awk '{print $1}'); do
  [ "$pid" = "$SELF" ] && continue
  if [ -r "/proc/$pid/cmdline" ] && tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q 'dorm_teardown'; then
    continue
  fi
  echo "  结束 $pid"
  kill -9 "$pid" 2>/dev/null || true
done

echo "== 4. 删除目录与上传包 =="
rm -rf /www/dorm /www/dorm-data /root/dorm_deploy.tar.gz /root/dorm_cleanup.sh
rmdir /www 2>/dev/null || true
echo "  /www 下内容：$(ls -A /www 2>/dev/null || echo '（已删除）')"

echo "== 5. 确认端口 =="
ss -lntp 2>/dev/null | awk 'NR>1 {print "  监听:", $4}' | sort -u
if ss -lntp 2>/dev/null | grep -qE ':(80|8000|8090) '; then
  echo "  注意：80/8000/8090 里还有在监听的进程，见上面列表"
else
  echo "  80 / 8000 / 8090 都没有监听"
fi
echo "== 清理完成 =="
