"""本地启动脚本：同时监听两个端口

- 主端口（DORM_PORT，默认 8090）：同学选寝室填写 + 寝室长界面，公开访问
- 管理端口（DORM_ADMIN_PORT，默认 8091）：管理员界面与全部管理接口，需要设备授权

用法：
    python run.py                     # 同时开 8090 和 8091
    python run.py --no-admin          # 只开主端口
    DORM_PORT=9000 DORM_ADMIN_PORT=9001 python run.py
"""
from __future__ import annotations

import asyncio
import os
import sys

import uvicorn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    host = os.environ.get("DORM_HOST", "0.0.0.0")
    main_port = int(os.environ.get("DORM_PORT", "8090"))
    admin_port = int(os.environ.get("DORM_ADMIN_PORT", "8091"))
    reload_flag = os.environ.get("DORM_RELOAD", "").strip().lower() in {"1", "true", "yes"}
    only_main = "--no-admin" in sys.argv or admin_port in (0, main_port)

    print("生活助手启动中……")
    print(f"  同学/寝室长界面：http://127.0.0.1:{main_port}")
    if not only_main:
        print(f"  管理员界面    ：http://127.0.0.1:{admin_port}")

    servers = [
        uvicorn.Server(
            uvicorn.Config(
                "backend.main:app",
                host=host,
                port=main_port,
                reload=reload_flag,
                log_level="info",
                access_log=True,
            )
        )
    ]
    if not only_main:
        servers.append(
            uvicorn.Server(
                uvicorn.Config(
                    "backend.main:app",
                    host=host,
                    port=admin_port,
                    log_level="info",
                    access_log=False,
                )
            )
        )

    async def serve_all() -> None:
        await asyncio.gather(*(server.serve() for server in servers))

    try:
        asyncio.run(serve_all())
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
