#!/usr/bin/env bash
# 生活助手 · 一键部署（Ubuntu 22.04 / 24.04）
#
# 用法（在项目根目录执行，需要 root）：
#     sudo bash deploy/install.sh
#
# 可配置项（环境变量）：
#     PORT=8090            公开端口：同学选寝室填报 + 寝室长界面
#     ADMIN_PORT=8091      管理端口：管理员界面与全部管理接口
#     APP_DIR=/www/dorm    代码目录
#     DATA_DIR=/www/dorm-data   数据目录
#     BIND=0.0.0.0         监听地址（默认 0.0.0.0，直接用 IP:端口 访问）
#     WITH_NGINX=0         是否额外配置 Nginx 反代（1 开；默认 0，不用 80 端口）
#     DOMAIN=              域名（WITH_NGINX=1 时写入 server_name，指向公开端口）
#     SERVICE_NAME=dorm    systemd 服务名
#
# 设计说明：默认「不用 Nginx、不碰 80 端口」；
#          8090 给同学和寝室长（公开），8091 给管理员（要设备授权，建议只让内网/固定 IP 访问）；
#          以后要走域名 + HTTPS，再加 WITH_NGINX=1 重新执行一次即可。
#
# 兼容说明：用 bash 或 sh 执行都可以；如果 sh 是 dash，会自动改用 bash 重新执行。
set -eu

if [ -z "${BASH_VERSION:-}" ]; then
  if command -v bash >/dev/null 2>&1; then
    echo "[提示] 当前不是 bash，改用 bash 重新执行"
    exec bash "$0" "$@"
  fi
fi

APP_DIR="${APP_DIR:-/www/dorm}"
DATA_DIR="${DATA_DIR:-/www/dorm-data}"
PORT="${PORT:-8090}"
ADMIN_PORT="${ADMIN_PORT:-8091}"
BIND="${BIND:-0.0.0.0}"
WITH_NGINX="${WITH_NGINX:-0}"
DOMAIN="${DOMAIN:-}"
SERVICE_NAME="${SERVICE_NAME:-dorm}"
PY_BIN="${PY_BIN:-python3}"

log() { printf '\033[1;32m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
warn() { printf '\033[1;33m[警告]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[错误]\033[0m %s\n' "$*"; exit 1; }

[[ $EUID -eq 0 ]] || die "请用 root 或 sudo 运行：sudo bash deploy/install.sh"

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log "项目目录：${SRC_DIR}"
log "部署目录：${APP_DIR}"
log "数据目录：${DATA_DIR}"
log "公开端口：${BIND}:${PORT}（同学填报 / 寝室长）"
log "管理端口：${BIND}:${ADMIN_PORT}（管理员界面）"
log "两个端口都不使用 80"

# ---------- 1. 系统依赖 ----------
log "安装系统依赖（python3 / venv / pip / curl）"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip curl ca-certificates
if [[ "$WITH_NGINX" == "1" ]]; then
  log "另外安装 Nginx（WITH_NGINX=1）"
  apt-get install -y nginx
fi

$PY_BIN -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || die "Python 版本过低，需要 3.9 以上"
log "系统 Python：$($PY_BIN --version)"

# ---------- 2. 同步代码 ----------
mkdir -p "$DATA_DIR"/{exports,backups,logs,uploads}
if [[ "$SRC_DIR" != "$APP_DIR" ]]; then
  log "复制代码到 ${APP_DIR}（不覆盖 data 目录）"
  tar -C "$SRC_DIR" \
      --exclude='.venv' --exclude='data' --exclude='data_test*' --exclude='__pycache__' \
      --exclude='.git' --exclude='*.pyc' -cf - . | tar -C "$APP_DIR" -xf -
fi
cd "$APP_DIR"

# ---------- 3. Python 依赖 ----------
if [[ ! -x "$APP_DIR/.venv/bin/python" ]]; then
  log "创建虚拟环境"
  $PY_BIN -m venv "$APP_DIR/.venv"
fi
log "安装 Python 依赖（慢的话会改用阿里云镜像重试）"
"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip >/dev/null
if ! "$APP_DIR/.venv/bin/python" -m pip install -r requirements.txt >/tmp/dorm_pip.log 2>&1; then
  warn "默认源安装失败，改用阿里云镜像重试"
  "$APP_DIR/.venv/bin/python" -m pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ || {
    cat /tmp/dorm_pip.log; die "依赖安装失败，请看上面的日志"; }
fi
log "依赖安装完成"

# ---------- 4. 权限 ----------
id -u www-data >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin www-data
chown -R www-data:www-data "$DATA_DIR"
chown -R www-data:www-data "$APP_DIR"
chmod 750 "$DATA_DIR"

# ---------- 5. systemd ----------
log "写入 systemd 服务 /etc/systemd/system/${SERVICE_NAME}.service"
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Dorm Management System (FastAPI)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=${APP_DIR}
Environment=DORM_HOST=${BIND}
Environment=DORM_PORT=${PORT}
Environment=DORM_ADMIN_PORT=${ADMIN_PORT}
Environment=DORM_DATA_DIR=${DATA_DIR}
Environment=DORM_TIMEZONE=Asia/Shanghai
Environment=PYTHONUNBUFFERED=1
ExecStart=${APP_DIR}/.venv/bin/python run.py
Restart=always
RestartSec=5
StandardOutput=append:${DATA_DIR}/logs/service.log
StandardError=append:${DATA_DIR}/logs/service.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null
systemctl restart "$SERVICE_NAME"
sleep 3
systemctl is-active --quiet "$SERVICE_NAME" || {
  journalctl -u "$SERVICE_NAME" -n 40 --no-pager
  die "服务启动失败，请看上面的日志"; }
log "服务已启动"

# ---------- 6. 可选：Nginx 反代（默认关闭，避免占用 80） ----------
if [[ "$WITH_NGINX" == "1" ]]; then
  log "配置 Nginx 反代（server_name=${DOMAIN:-_}）"
  cat > "/etc/nginx/sites-available/${SERVICE_NAME}" <<EOF
server {
    listen 80;
    server_name ${DOMAIN:-_};

    client_max_body_size 20m;
    access_log /var/log/nginx/${SERVICE_NAME}.access.log;
    error_log  /var/log/nginx/${SERVICE_NAME}.error.log;

    location / {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }
}
EOF
  ln -sf "/etc/nginx/sites-available/${SERVICE_NAME}" "/etc/nginx/sites-enabled/${SERVICE_NAME}"
  nginx -t && systemctl enable nginx >/dev/null && systemctl restart nginx
  log "Nginx 已生效（80 端口）"
else
  log "跳过 Nginx：同学用 http://服务器IP:${PORT}，管理员用 http://服务器IP:${ADMIN_PORT}"
fi

# ---------- 7. 创建管理员账号（用户名 admin，密码与 admin_code 一致并打印出来） ----------
log "创建管理员账号"
ADMIN_INFO="$(DORM_DATA_DIR="$DATA_DIR" "$APP_DIR/.venv/bin/python" - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal, init_db
from backend.security import ensure_owner_account
from backend.services import settings_service as ss

init_db()
db = SessionLocal()
ss.ensure_settings(db)
owner, initial = ensure_owner_account(db)
if not initial:
    initial = ss.get_setting(db, 'admin_code')
print(f"{owner.username}	{initial}")
db.close()
PY
)"
ADMIN_USER="$(printf '%s' "$ADMIN_INFO" | cut -f1)"
ADMIN_CODE="$(printf '%s' "$ADMIN_INFO" | cut -f2)"

# 校验这个密码真的能登录，避免打印出无效密码
if DORM_DATA_DIR="$DATA_DIR" "$APP_DIR/.venv/bin/python" - "$ADMIN_USER" "$ADMIN_CODE" <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.security import authenticate_account

db = SessionLocal()
account, _reason = authenticate_account(db, sys.argv[1], sys.argv[2])
db.close()
sys.exit(0 if account is not None else 1)
PY
then
  log "管理员密码校验通过"
else
  warn "打印出来的密码验证不通过，改为重置成新的随机密码"
  ADMIN_CODE="$(DORM_DATA_DIR="$DATA_DIR" "$APP_DIR/.venv/bin/python" scripts/admin_account.py --reset 2>/dev/null | sed -n 's/^新密码：//p')"
fi

# ---------- 8. 自检（打管理端口，管理接口只在管理端口开放） ----------
log "接口自检（管理端口 ${ADMIN_PORT}）"
if DORM_DATA_DIR="$DATA_DIR" "$APP_DIR/.venv/bin/python" scripts/selftest.py "http://127.0.0.1:${ADMIN_PORT}" > /tmp/dorm_selftest.log 2>&1; then
  tail -3 /tmp/dorm_selftest.log
else
  warn "自检未全部通过，日志：/tmp/dorm_selftest.log"
  tail -20 /tmp/dorm_selftest.log
fi

# ---------- 9. 清空自检产生的数据，交付一个干净库 ----------
log "清空自检产生的数据（保留系统配置与管理访问码）"
if DORM_DATA_DIR="$DATA_DIR" "$APP_DIR/.venv/bin/python" scripts/reset_server_data.py >/tmp/dorm_reset.log 2>&1; then
  tail -3 /tmp/dorm_reset.log
  systemctl restart "$SERVICE_NAME"
  sleep 3
  log "服务已重启，数据库是干净的"
else
  warn "清空数据失败，请看 /tmp/dorm_reset.log"
  tail -10 /tmp/dorm_reset.log
fi

cat <<EOF

============================================================
 部署完成
------------------------------------------------------------
 同学/寝室长 : http://$(curl -s -m 5 ifconfig.me 2>/dev/null || echo '服务器IP'):${PORT}/
 管理员      : http://$(curl -s -m 5 ifconfig.me 2>/dev/null || echo '服务器IP'):${ADMIN_PORT}/
 服务状态    : systemctl status ${SERVICE_NAME}
 实时日志    : journalctl -u ${SERVICE_NAME} -f
 数据目录    : ${DATA_DIR}
 管理员账号  : ${ADMIN_USER}
 初始密码    : ${ADMIN_CODE}
------------------------------------------------------------
 下一步：
 1. 云服务器安全组放行 ${PORT} 端口（不放 80）；管理端口 ${ADMIN_PORT} 建议只对固定 IP 放行，或干脆不放行、用 SSH 隧道访问
 2. 浏览器打开管理端 → 用上面账号密码登录 → 立刻到「账号管理 → 修改密码」换成自己的密码
 3. 「账号管理」里给需要登录的寝室建寝室长账号（用户名=宿舍号），把账号密码发到宿舍群
 4. 「宿舍与人员 → 导入人员信息」导入名单；「班费管理」导入班费收支明细表
 5. 以后要走域名 + HTTPS：WITH_NGINX=1 DOMAIN=你的域名 sudo bash deploy/install.sh 再执行一次
============================================================
EOF
