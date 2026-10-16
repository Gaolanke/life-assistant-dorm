"""生活助手 · FastAPI 应用入口。

启动： python run.py     或     uvicorn backend.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from . import config, scheduler
from .database import SessionLocal, init_db
from .models import Account, Dorm, Member, Report
from .routers import access, auth, classes, dorms, fund, qqbot, reports, settings
from .security import (
    client_context,
    current_account,
    ensure_owner_account,
    is_admin_only_request,
    is_admin_port,
    new_access_code,
    request_port,
    require_admin,
    set_current_device,
)
from .util import client_device
from .services import class_service, qqbot_gateway, report_service, settings_service as ss
from .util import AppError, now_local

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("dorm")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.ensure_dirs()
    init_db()
    db = SessionLocal()
    try:
        ss.ensure_settings(db)
        # 多班级：确保至少有一个班级，老数据（class_id=0）全部归入默认班级
        default_class = class_service.ensure_default_class(db)
        log.info("默认班级：%s（id=%s）", default_class.name, default_class.id)
        # 确保有一个可登录的超级管理员账号（首次安装时自动创建 admin，初始密码就是访问码）
        owner, initial_password = ensure_owner_account(db)
        if initial_password:
            log.warning("=" * 58)
            log.warning("已创建超级管理员账号：%s", owner.username)
            log.warning("初始密码：%s", initial_password)
            log.warning("登录地址：http://127.0.0.1:%s  （管理端口）", config.ADMIN_PORT)
            log.warning("登录后请到「账号管理」里修改密码。", )
            log.warning("=" * 58)
    finally:
        db.close()
    try:
        scheduler.start_scheduler()
    except Exception:  # noqa: BLE001
        log.exception("定时任务启动失败（不影响网页使用）")
    try:
        qqbot_gateway.start_gateway(SessionLocal)
    except Exception:  # noqa: BLE001
        log.exception("QQ 机器人长连接启动失败（不影响网页使用）")
    log.info("%s 已启动：http://127.0.0.1:%s", config.APP_NAME, config.PORT)
    yield
    scheduler.shutdown_scheduler()
    try:
        await qqbot_gateway.stop_gateway()
    except Exception:  # noqa: BLE001
        pass


app = FastAPI(title=config.APP_NAME, version=config.VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 管理端口上不需要登录就能访问的接口（登录页本身要用）
# 注意 /api/access/status 只返回"调用者自己的"登录状态（匿名时 account 为 null），
# 登录页靠它判断该显示登录框还是管理界面，必须放行。
ADMIN_PORT_OPEN_API = (
    "/api/health",
    "/api/system/mode",
    "/api/system/info",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/me",
    "/api/auth/ping",
    "/api/access/status",
    "/api/access/leader/login",
    "/api/access/leader/me",
    # QQ 官方机器人的事件回调：由腾讯服务器调用，不可能带登录会话。
    # 它自己用 Ed25519 签名校验来源，所以两个域名都放行，
    # 这样 Webhook 回调地址填哪个域名都能用。
    "/api/qqbot/events",
)


@app.middleware("http")
async def split_ports(request: Request, call_next):
    """端口分流 + 管理端口鉴权。

    主端口（DORM_PORT，默认 8090）：同学选寝室填写 + 寝室长界面。
    管理端口（DORM_ADMIN_PORT，默认 8091）：管理员界面与所有管理接口。

    管理端口上，除了登录相关的极少数接口，**其余 /api/ 一律要求管理员会话**。
    前端登录页只是页面级跳转，挡不住直接调接口，所以必须在这里拦住。
    """
    path = request.url.path
    method = request.method
    # 记录当前请求的设备描述，写日志时自动带上（谁用什么设备操作的）
    set_current_device(client_device(request))
    if is_admin_only_request(method, path) and not is_admin_port(request):
        return JSONResponse(
            status_code=404,
            content={
                "ok": False,
                "message": f"管理接口只在管理端口（{config.ADMIN_PORT}）开放，当前访问的是公开端口（{config.PORT}）",
            },
        )

    # 管理端口：统一要求管理员登录
    if is_admin_port(request) and path.startswith("/api/"):
        if path not in ADMIN_PORT_OPEN_API:
            db = SessionLocal()
            try:
                account = current_account(db, request)
            finally:
                db.close()
            if account is None:
                return JSONResponse(
                    status_code=401,
                    content={"ok": False, "message": "请先用管理员账号登录管理端"},
                )
            if account.role != "admin":
                return JSONResponse(
                    status_code=403,
                    content={"ok": False, "message": "这个账号不是管理员，没有管理权限"},
                )

    response = await call_next(request)
    # 前端文件（html/js/css）每次都让浏览器回来校验一次：
    # 有改动立刻生效，没改动用 304，不会拿到旧页面
    if not path.startswith("/api/") and (
        path.endswith((".js", ".css", ".html")) or path in ("/", "")
    ):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"ok": False, "message": exc.message})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):  # pragma: no cover
    log.exception("未处理异常：%s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"ok": False, "message": f"服务器错误：{exc}"})


app.include_router(auth.router)
app.include_router(access.router)
app.include_router(classes.router)
app.include_router(dorms.router)
app.include_router(reports.router)
app.include_router(fund.router)
app.include_router(qqbot.router)
app.include_router(settings.router)


def resolve_site_urls(request: Request, *, public_url: str = "", admin_url: str = "") -> dict:
    """算出对外的公开端 / 管理端地址。

    优先级：
      1. 系统配置里手填的 site_public_url / site_admin_url
      2. 自动识别：如果请求是「用域名」进来的（Host 不是 IP），
         就把当前 origin 当公开端，把最左边那段换成 admin 当管理端（反之亦然）
      3. 都没有则退回 IP + 端口
    """
    import ipaddress

    host_header = request.headers.get("host", "")
    hostname = host_header.split(":")[0].strip()
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme) or "http"

    def is_ip(value: str) -> bool:
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            return False

    admin_here = is_admin_port(request) or hostname.startswith("admin.")
    via_domain = bool(hostname) and not is_ip(hostname) and "." in hostname

    # 1. 手填优先
    if public_url.strip() and admin_url.strip():
        return {
            "public": public_url.strip().rstrip("/"),
            "admin": admin_url.strip().rstrip("/"),
            "via_domain": True,
        }

    if via_domain:
        parts = hostname.split(".")
        if admin_here:
            # 当前在管理端：当前 origin 就是管理端，去掉 admin. 前缀当公开端
            admin_base = f"{scheme}://{hostname}"
            public_host = ".".join(parts[1:]) if parts and parts[0] == "admin" else hostname
            public_base = f"{scheme}://{public_host}"
        else:
            public_base = f"{scheme}://{hostname}"
            admin_base = f"{scheme}://admin.{hostname}"
        return {
            "public": public_url.strip().rstrip("/") or public_base,
            "admin": admin_url.strip().rstrip("/") or admin_base,
            "via_domain": True,
        }

    # 3. IP + 端口
    return {
        "public": public_url.strip().rstrip("/") or f"{scheme}://{hostname}:{config.PORT}",
        "admin": admin_url.strip().rstrip("/") or f"{scheme}://{hostname}:{config.ADMIN_PORT}",
        "via_domain": False,
    }


@app.get("/api/system/info")
def system_info(request: Request):
    db = SessionLocal()
    try:
        dorm_count = db.execute(select(func.count(Dorm.id))).scalar() or 0
        member_count = db.execute(select(func.count(Member.id))).scalar() or 0
        report_count = db.execute(select(func.count(Report.id))).scalar() or 0
        account_count = db.execute(select(func.count(Account.id))).scalar() or 0
        today_stats = report_service.day_stats(db, now_local().date())
        urls = resolve_site_urls(
            request,
            public_url=ss.get_setting(db, "site_public_url"),
            admin_url=ss.get_setting(db, "site_admin_url"),
        )
        return {
            "ok": True,
            "app": config.APP_NAME,
            "version": config.VERSION,
            "timezone": config.TIMEZONE,
            "server_time": now_local().strftime("%Y-%m-%d %H:%M:%S"),
            "data_dir": str(config.DATA_DIR),
            "db_path": str(config.DB_PATH),
            "public_base": urls["public"],
            "admin_base": urls["admin"],
            "via_domain": urls["via_domain"],
            "counts": {
                "dorms": dorm_count,
                "members": member_count,
                "reports": report_count,
                "accounts": account_count,
            },
            "today": today_stats,
            "jobs": scheduler.job_status(),
            "settings": {
                "qq_report_time": ss.get_setting(db, "qq_report_time"),
                "auto_export_time": ss.get_setting(db, "auto_export_time"),
            },
        }
    finally:
        db.close()


@app.get("/api/system/backup")
def backup_database():
    """下载一份数据库备份文件（用 SQLite 官方备份接口，WAL 数据不会丢）。"""
    import sqlite3

    config.ensure_dirs()
    timestamp = now_local().strftime("%Y%m%d_%H%M%S")
    backup_path = config.BACKUP_DIR / f"app_{timestamp}.db"
    if backup_path.exists():
        backup_path.unlink()
    # 先把 WAL 日志合并进主库，再复制，保证备份包含最新数据
    source = sqlite3.connect(str(config.DB_PATH))
    try:
        source.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        target = sqlite3.connect(str(backup_path))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()
    return FileResponse(
        path=backup_path,
        filename=backup_path.name,
        media_type="application/octet-stream",
    )


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "app": config.APP_NAME,
        "version": config.VERSION,
        "time": now_local().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get("/api/system/mode")
def system_mode(request: Request):
    """告诉前端：当前这个端口是公开端口还是管理端口，以及对外网址。"""
    admin = is_admin_port(request)
    db = SessionLocal()
    try:
        urls = resolve_site_urls(
            request,
            public_url=ss.get_setting(db, "site_public_url"),
            admin_url=ss.get_setting(db, "site_admin_url"),
        )
    finally:
        db.close()
    return {
        "ok": True,
        "port": request_port(request),
        "mode": "admin" if admin else "public",
        "is_admin_port": admin,
        "main_port": config.PORT,
        "admin_port": config.ADMIN_PORT,
        "public_base": urls["public"],
        "admin_base": urls["admin"],
        "via_domain": urls["via_domain"],
        "message": "管理员端口" if admin else "公开端口（同学填报 / 寝室长）",
    }


@app.post("/api/system/reset-data")
def reset_data(payload: dict | None = None, request: Request = None, _: dict = Depends(require_admin)):
    """清空业务数据（宿舍、人员、填报、推送日志）。

    需要已授权的管理设备；界面上还要求输入“清空”两个字才提交。
    """
    from sqlalchemy import delete as sql_delete

    from .models import AuditLog, PushLog, ReportCheckin

    payload = payload or {}
    keep_accounts = bool(payload.get("keep_accounts", True))
    keep_settings = bool(payload.get("keep_settings", True))
    context = client_context(request) if request is not None else {"display_name": "服务器脚本", "ip": ""}

    db = SessionLocal()
    try:
        counters = {}
        for model, name in (
            (ReportCheckin, "checkins"),
            (Report, "reports"),
            (Member, "members"),
            (Dorm, "dorms"),
            (PushLog, "push_logs"),
            (AuditLog, "audits"),
        ):
            counters[name] = db.execute(sql_delete(model)).rowcount or 0
        if not keep_accounts:
            counters["users"] = db.execute(sql_delete(User)).rowcount or 0
        if not keep_settings:
            from .models import Setting

            counters["settings"] = db.execute(sql_delete(Setting)).rowcount or 0
        db.commit()
        ss.write_audit(
            db,
            actor=context["display_name"],
            role="public",
            action="清空全部业务数据",
            detail=str(counters),
            ip=context.get("ip", ""),
        )
        db.commit()
        log.warning("业务数据已清空：%s（操作人 %s）", counters, context["display_name"])
        return {
            "ok": True,
            "message": "已清空全部宿舍、人员和填报数据"
            + ("，系统配置保留" if keep_settings else "，系统配置也已清空"),
            "counters": counters,
        }
    finally:
        db.close()


@app.get("/api/system/qrcode")
def qrcode_image(text: str, scale: int = 6):
    """生成二维码 PNG（离线生成，不依赖外部服务）。"""
    import io

    from fastapi.responses import Response

    text = (text or "").strip()
    if not text:
        return JSONResponse(status_code=400, content={"ok": False, "message": "缺少 text 参数"})
    try:
        import segno

        qr = segno.make(text, error="m")
        buffer = io.BytesIO()
        qr.save(buffer, kind="png", scale=max(2, min(int(scale), 12)), border=2, dark="#16233c", light="#ffffff")
        return Response(content=buffer.getvalue(), media_type="image/png", headers={"Cache-Control": "max-age=86400"})
    except Exception as exc:  # noqa: BLE001
        log.warning("二维码生成失败：%s", exc)
        return JSONResponse(status_code=500, content={"ok": False, "message": f"二维码生成失败：{exc}"})


# 前端静态文件
app.mount("/", StaticFiles(directory=config.STATIC_DIR, html=True), name="static")
