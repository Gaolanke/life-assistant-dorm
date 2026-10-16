"""简易 SSH 助手：用密码登录远程服务器执行命令 / 上传文件。

用法：
    python scripts/ssh_run.py exec "uname -a"
    python scripts/ssh_run.py exec --sudo "apt-get update -y"
    python scripts/ssh_run.py put 本地文件 远程路径
    python scripts/ssh_run.py shell                     # 交互式

默认连接 root@111.228.38.170，可通过环境变量覆盖：
    DORM_SSH_HOST / DORM_SSH_PORT / DORM_SSH_USER / DORM_SSH_PASSWORD
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import paramiko

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

HOST = os.environ.get("DORM_SSH_HOST", "111.228.38.170")
PORT = int(os.environ.get("DORM_SSH_PORT", "22"))
USER = os.environ.get("DORM_SSH_USER", "root")
PASSWORD = os.environ.get("DORM_SSH_PASSWORD", "Xiaoai@947422")


def connect() -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=HOST,
        port=PORT,
        username=USER,
        password=PASSWORD,
        timeout=25,
        banner_timeout=40,
        auth_timeout=40,
        look_for_keys=False,
        allow_agent=False,
    )
    return client


def run(client: paramiko.SSHClient, command: str, *, sudo: bool = False, timeout: int = 1800) -> tuple[int, str]:
    if sudo:
        command = f"sudo -S -p '' bash -lc {shell_quote(command)}"
    channel = client.get_transport().open_session()
    channel.settimeout(timeout)
    if sudo:
        # 需要管道把密码喂给 sudo -S
        channel.exec_command(f"echo {shell_quote(PASSWORD)} | {command}")
    else:
        channel.exec_command(command)
    output: list[str] = []

    def pump(stream, writer) -> None:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                break
            if isinstance(chunk, bytes):
                text = chunk.decode("utf-8", "replace")
            else:
                text = chunk
            writer.write(text)
            writer.flush()
            output.append(text)
        stream.close()

    import threading

    threads = [
        threading.Thread(target=pump, args=(channel.makefile("rb"), sys.stdout)),
        threading.Thread(target=pump, args=(channel.makefile_stderr("rb"), sys.stderr)),
    ]
    for thread in threads:
        thread.daemon = True
        thread.start()
    exit_status = channel.recv_exit_status()
    for thread in threads:
        thread.join(timeout=5)
    return exit_status, "".join(output)


def shell_quote(text: str) -> str:
    return "'" + text.replace("'", "'\"'\"'") + "'"


def put(client: paramiko.SSHClient, local: str, remote: str) -> None:
    sftp = client.open_sftp()
    local_path = Path(local)
    size = local_path.stat().st_size
    print(f"上传 {local_path.name}（{size / 1024 / 1024:.1f} MB）→ {remote}")
    start = time.time()
    last = [0.0]

    def progress(done: int, total: int) -> None:
        now = time.time()
        if now - last[0] < 1:
            return
        last[0] = now
        percent = done / total * 100 if total else 0
        speed = done / 1024 / 1024 / max(now - start, 0.001)
        print(f"  {percent:5.1f}%  {done / 1024 / 1024:.1f}/{total / 1024 / 1024:.1f} MB  {speed:.1f} MB/s")

    sftp.put(local, remote, callback=progress)
    sftp.close()
    print(f"上传完成，用时 {time.time() - start:.1f} 秒")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["exec", "put", "shell", "check"])
    parser.add_argument("args", nargs="*")
    parser.add_argument("--sudo", action="store_true", help="用 sudo 执行（会喂密码）")
    parser.add_argument("--timeout", type=int, default=1800)
    parsed, extra = parser.parse_known_args()
    parsed.args = list(parsed.args) + [item for item in extra if item != "--"]
    args = parsed

    client = connect()
    print(f"已连接 {USER}@{HOST}:{PORT}")
    try:
        if args.action == "check":
            for command in (
                "cat /etc/os-release | head -3",
                "uname -r && uname -m",
                "nproc && free -m | head -2 && df -h / | tail -1",
                "python3 --version 2>&1; which python3",
                "systemctl --version | head -1",
                "nginx -v 2>&1 | head -1; which nginx",
                "ss -lntp 2>/dev/null | head -20 || netstat -lntp | head -20",
                "curl -s -m 5 ifconfig.me; echo",
            ):
                print(f"\n$ {command}")
                code, _ = run(client, command)
                if code != 0:
                    print(f"  （退出码 {code}）")
            return 0
        if args.action == "exec":
            command = " ".join(args.args)
            print(f"$ {command}")
            code, _ = run(client, command, sudo=args.sudo, timeout=args.timeout)
            print(f"\n[退出码 {code}]")
            return code
        if args.action == "put":
            if len(args.args) < 2:
                print("用法：put 本地文件 远程路径")
                return 2
            put(client, args.args[0], args.args[1])
            return 0
        if args.action == "shell":
            channel = client.invoke_shell()
            import select

            while True:
                if channel.recv_ready():
                    sys.stdout.write(channel.recv(4096).decode("utf-8", "replace"))
                    sys.stdout.flush()
                if channel.exit_status_ready():
                    break
                if sys.stdin in select.select([sys.stdin], [], [], 0.1)[0]:
                    line = sys.stdin.readline()
                    if not line:
                        break
                    channel.send(line)
            return 0
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
