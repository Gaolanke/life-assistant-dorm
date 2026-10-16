"""在服务器上后台执行部署脚本并轮询进度。

用法： python scripts/deploy_remote.py [--tail]
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.ssh_run import connect, run  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8")

LOG = "/root/deploy.log"
MARK = "/root/deploy.done"


def main() -> int:
    client = connect()
    print("已连接服务器")
    try:
        run(client, f"rm -f {LOG} {MARK}")
        start = (
            "cd /www/dorm && "
            "nohup env APP_DIR=/www/dorm DATA_DIR=/www/dorm-data PORT=8090 ADMIN_PORT=8091 "
            f"bash deploy/install.sh > {LOG} 2>&1; echo $? > {MARK} &"
        )
        print("已在后台启动部署脚本")
        run(client, start)

        deadline = time.time() + 1800
        last_size = 0
        while time.time() < deadline:
            time.sleep(15)
            code, out = run(client, f"cat {MARK} 2>/dev/null || echo RUNNING")
            status = out.strip().splitlines()[-1] if out.strip() else "RUNNING"
            size_out = run(client, f"wc -c < {LOG} 2>/dev/null || echo 0")[1].strip()
            size = int(size_out or 0)
            if size != last_size:
                print(f"  …… 部署进行中（日志 {size} 字节）")
                last_size = size
            if status != "RUNNING":
                print(f"\n部署脚本结束，退出码 {status}")
                break
        else:
            print("等待超时，请看下面的日志")
            status = "TIMEOUT"

        print("\n===== 部署日志 =====")
        run(client, f"tail -60 {LOG}")
        print(f"\n最终退出码：{status}")
        return 0 if status == "0" else 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
