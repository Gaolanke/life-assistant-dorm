#!/usr/bin/env bash
# 用域名上线「生活助手」（Nginx 反代 + Let's Encrypt 证书）
#
# 前提：
#   1. 域名已完成 ICP 备案（京东云大陆机房必须）
#   2. DNS 已加 A 记录指向服务器：@ / www / admin
#   3. 安全组已放行 80 和 443
#
# 用法：
#   bash deploy/setup_domain.sh                       # 默认 xiaoaiyun.top
#   bash deploy/setup_domain.sh example.com           # 指定域名
#   bash deploy/setup_domain.sh xiaoaiyun.top --no-admin   # 不配 admin 子域
#   bash deploy/setup_domain.sh xiaoaiyun.top --http-only  # 先只配 80（还没备案时试）
set -eu

DOMAIN="${1:-xiaoaiyun.top}"
ADMIN_DOMAIN="admin.${DOMAIN}"
WITH_ADMIN=1
HTTP_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --no-admin) WITH_ADMIN=0 ;;
    --http-only) HTTP_ONLY=1 ;;
  esac
done

APP_DIR="${APP_DIR:-/www/dorm}"
PUBLIC_PORT="${PUBLIC_PORT:-8090}"
ADMIN_PORT="${ADMIN_PORT:-8091}"
EMAIL="${CERT_EMAIL:-}"

if [ -z "${BASH_VERSION:-}" ] && command -v bash >/dev/null 2>&1; then
  exec bash "$0" "$@"
fi
[ "$(id -u)" = "0" ] || { echo "请用 root 运行"; exit 1; }

echo "=== 0. 参数 ==="
echo "  主域名    : $DOMAIN  -> 127.0.0.1:$PUBLIC_PORT"
[ "$WITH_ADMIN" = "1" ] && echo "  管理域名  : $ADMIN_DOMAIN -> 127.0.0.1:$ADMIN_PORT"
echo "  代码目录  : $APP_DIR"

echo
echo "=== 1. 检查 DNS 是否已指向本机 ==="
MY_IP=$(curl -s -m 8 ifconfig.me 2>/dev/null || echo "")
echo "  本机公网 IP: ${MY_IP:-取不到}"
for name in "$DOMAIN" "www.$DOMAIN"; do
  ip=$(getent ahostsv4 "$name" 2>/dev/null | awk '{print $1}' | head -1)
  if [ -z "$ip" ]; then
    echo "  ❗ $name 还没解析，先去加 A 记录"
  elif [ "$ip" = "$MY_IP" ]; then
    echo "  ✅ $name -> $ip"
  else
    echo "  ⚠️ $name -> $ip（不是本机）"
  fi
done
[ "$WITH_ADMIN" = "1" ] && {
  ip=$(getent ahostsv4 "$ADMIN_DOMAIN" 2>/dev/null | awk '{print $1}' | head -1)
  echo "  ${ADMIN_DOMAIN}: ${ip:-还没解析}"
}

echo
echo "=== 2. 装 Nginx 和 certbot ==="
export DEBIAN_FRONTEND=noninteractive
command -v nginx >/dev/null 2>&1 || apt-get install -y -q nginx
if [ "$HTTP_ONLY" = "0" ]; then
  command -v certbot >/dev/null 2>&1 || apt-get install -y -q certbot python3-certbot-nginx
fi
mkdir -p /var/www/html
systemctl enable nginx >/dev/null 2>&1 || true

echo
echo "=== 3. 先用 80 端口放行（拿证书前必须能访问） ==="
cat > /etc/nginx/sites-available/life-assistant <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN www.$DOMAIN;
    client_max_body_size 20m;
    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / {
        proxy_pass http://127.0.0.1:$PUBLIC_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
    }
}
EOF
ln -sf /etc/nginx/sites-available/life-assistant /etc/nginx/sites-enabled/life-assistant
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx
echo "  80 端口已通（http://$DOMAIN 应该能看到网站）"

if [ "$HTTP_ONLY" = "1" ]; then
  if [ "$WITH_ADMIN" = "1" ]; then
    cat > /etc/nginx/sites-available/life-assistant-admin <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $ADMIN_DOMAIN;
    client_max_body_size 20m;

    # 还没上 HTTPS，管理端建议只允许你自己的 IP 访问（取消注释并改成你的公网 IP）
    # allow 1.2.3.4;
    # deny all;

    location / {
        proxy_pass http://127.0.0.1:$ADMIN_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
    }
}
EOF
    ln -sf /etc/nginx/sites-available/life-assistant-admin /etc/nginx/sites-enabled/life-assistant-admin
  fi
  nginx -t && systemctl restart nginx

  echo
  echo "=== 只配了 HTTP（未申请证书） ==="
  echo "  同学填报 : http://$DOMAIN"
  [ "$WITH_ADMIN" = "1" ] && echo "  管理端   : http://$ADMIN_DOMAIN"
  echo "  备用地址 : http://$DOMAIN:$PUBLIC_PORT  （万一 80 端口被云平台拦，用这个）"
  echo
  echo "  备案下来后执行这一条，自动升级到 HTTPS："
  echo "    bash $APP_DIR/deploy/setup_domain.sh $DOMAIN"
  echo
  echo "  自检："
  printf '    http://%s/api/health -> %s\n' "$DOMAIN" "$(curl -s -m 8 -o /dev/null -w '%{http_code}' "http://$DOMAIN/api/health" || echo 失败)"
  exit 0
fi

echo
echo "=== 4. 申请 Let's Encrypt 证书 ==="
CERT_ARGS=(certonly --nginx -d "$DOMAIN" -d "www.$DOMAIN" --non-interactive --agree-tos --keep-until-expiring)
if [ -n "$EMAIL" ]; then
  CERT_ARGS+=(--email "$EMAIL")
else
  CERT_ARGS+=(--register-unsafely-without-email)
fi
if certbot "${CERT_ARGS[@]}"; then
  echo "  ✅ 证书申请成功"
else
  echo "  ❌ 证书申请失败（多半是没备案，或者 80 端口没放行）"
  echo "     你可以先只用 http://$DOMAIN 访问；备案后再跑一次本脚本"
  exit 1
fi

echo
echo "=== 5. 写入正式配置（含 HTTPS） ==="
cp "$APP_DIR/deploy/nginx-life-assistant.conf" /etc/nginx/sites-available/life-assistant
sed -i "s/xiaoaiyun\.top/$DOMAIN/g" /etc/nginx/sites-available/life-assistant

if [ "$WITH_ADMIN" = "1" ]; then
  cp "$APP_DIR/deploy/nginx-life-assistant-admin.conf" /etc/nginx/sites-available/life-assistant-admin
  sed -i "s/xiaoaiyun\.top/$DOMAIN/g" /etc/nginx/sites-available/life-assistant-admin
  ln -sf /etc/nginx/sites-available/life-assistant-admin /etc/nginx/sites-enabled/life-assistant-admin
  ADMIN_CERT_ARGS=(certonly --nginx -d "$ADMIN_DOMAIN" --non-interactive --agree-tos --keep-until-expiring)
  if [ -n "$EMAIL" ]; then ADMIN_CERT_ARGS+=(--email "$EMAIL"); else ADMIN_CERT_ARGS+=(--register-unsafely-without-email); fi
  certbot "${ADMIN_CERT_ARGS[@]}" || echo "  ⚠️ admin 子域证书失败，管理端仍可用 IP:8091 访问"
fi

nginx -t && systemctl restart nginx

echo
echo "=== 6. 完成 ==="
echo "  同学填报 : https://$DOMAIN"
[ "$WITH_ADMIN" = "1" ] && echo "  管理端   : https://$ADMIN_DOMAIN"
echo "  证书自动续期：systemctl status certbot.timer"
echo
echo "  验证："
for url in "https://$DOMAIN/api/health"; do
  printf '    %s -> %s\n' "$url" "$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$url" || echo 失败)"
done
