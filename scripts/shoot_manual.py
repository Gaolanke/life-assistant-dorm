#!/usr/bin/env python3
"""从线上站点批量截取各功能页面，用于软著《操作手册》。"""
import os
import socket
import subprocess
import tempfile
import shutil
import urllib.parse
from pathlib import Path

import httpx

CF_IP = "104.21.39.197"
OUT = Path(r"E:\Document\code\宿舍管理系统\软著申请\screenshots")
OUT.mkdir(parents=True, exist_ok=True)

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

# 让本机把域名解析到 Cloudflare
_real = socket.getaddrinfo


def _fake(host, *a, **k):
    if host.endswith("xiaoaiyun.top"):
        host = CF_IP
    return _real(host, *a, **k)


socket.getaddrinfo = _fake

# 登录拿 token
c = httpx.Client(base_url="https://admin.xiaoaiyun.top", timeout=40)
r = c.post("/api/auth/login", json={"username": "admin", "password": "344940"})
token = r.json().get("token", "")
print("登录:", r.status_code, "token 长度", len(token))

ADMIN = "https://admin.xiaoaiyun.top"
PUBLIC = "https://xiaoaiyun.top"

PAGES = [
    ("01-登录页", f"{PUBLIC}/#/login", "xiaoaiyun.top"),
    ("02-选择寝室", f"{PUBLIC}/", "xiaoaiyun.top"),
    ("03-每日填报", f"{PUBLIC}/#/report", "xiaoaiyun.top"),
    ("04-数据看板", f"{PUBLIC}/#/dashboard", "xiaoaiyun.top"),
    ("05-统计图表", f"{PUBLIC}/#/stats", "xiaoaiyun.top"),
    ("06-填报记录", f"{PUBLIC}/#/records", "xiaoaiyun.top"),
    ("07-管理端登录", f"{ADMIN}/", "admin.xiaoaiyun.top"),
    (
        "08-管理端总览",
        f"{ADMIN}/?token={urllib.parse.quote(token)}#/overview",
        "admin.xiaoaiyun.top",
    ),
    (
        "09-宿舍与人员",
        f"{ADMIN}/?token={urllib.parse.quote(token)}#/dorms",
        "admin.xiaoaiyun.top",
    ),
    (
        "10-账号管理",
        f"{ADMIN}/?token={urllib.parse.quote(token)}#/accounts",
        "admin.xiaoaiyun.top",
    ),
    (
        "11-班费管理",
        f"{ADMIN}/?token={urllib.parse.quote(token)}#/fund",
        "admin.xiaoaiyun.top",
    ),
    (
        "12-提醒推送",
        f"{ADMIN}/?token={urllib.parse.quote(token)}#/push",
        "admin.xiaoaiyun.top",
    ),
    (
        "13-管理控制台",
        f"{ADMIN}/?token={urllib.parse.quote(token)}#/console",
        "admin.xiaoaiyun.top",
    ),
    (
        "14-填写日志",
        f"{ADMIN}/?token={urllib.parse.quote(token)}#/logs",
        "admin.xiaoaiyun.top",
    ),
    (
        "15-系统配置-基本",
        f"{ADMIN}/?token={urllib.parse.quote(token)}#/config",
        "admin.xiaoaiyun.top",
    ),
    (
        "16-系统配置-QQ机器人",
        f"{ADMIN}/?token={urllib.parse.quote(token)}#/config/qqbot",
        "admin.xiaoaiyun.top",
    ),
]

for name, url, host in PAGES:
    out = OUT / f"{name}.png"
    prof = os.path.join(tempfile.gettempdir(), "edge-cy-" + name)
    shutil.rmtree(prof, ignore_errors=True)
    try:
        subprocess.run(
            [
                EDGE,
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                "--hide-scrollbars",
                "--user-data-dir=" + prof,
                "--window-size=1440,1000",
                "--screenshot=" + str(out),
                "--virtual-time-budget=20000",
                f"--host-resolver-rules=MAP {host} {CF_IP}",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=150,
            errors="replace",
        )
        size = out.stat().st_size if out.exists() else 0
        print(f"  {name:<26} {size / 1024:>7.1f} KB")
    except Exception as exc:
        print(f"  {name:<26} 失败 {exc}")

print("\n完成，输出目录:", OUT)
