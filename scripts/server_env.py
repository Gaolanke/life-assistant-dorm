"""让命令行脚本自动找到服务的数据库。

服务是用 systemd 跑起来的，数据目录写在服务单元里（`DORM_DATA_DIR`）。
直接 `python scripts/xxx.py` 时当前 shell 没有这个环境变量，脚本会误读项目下的 `data/`，
导致「库里的访问码 / 数据」和服务里的对不上。

import 这个模块（必须在 import backend.* 之前）即可自动对齐：

    import server_env  # noqa: F401  （放在 sys.path 设置之后、backend 导入之前）
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _from_systemd(service: str) -> str:
    """从 systemctl show 里读 DORM_DATA_DIR。"""
    try:
        output = subprocess.run(
            ["systemctl", "show", service, "-p", "Environment", "--value"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except Exception:  # noqa: BLE001
        return ""
    match = re.search(r"DORM_DATA_DIR=(\S+)", output or "")
    return match.group(1) if match else ""


def _from_unit_file(service: str) -> str:
    for path in (f"/etc/systemd/system/{service}.service", f"/lib/systemd/system/{service}.service"):
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError:
            continue
        match = re.search(r"DORM_DATA_DIR=(\S+)", text)
        if match:
            return match.group(1)
    return ""


def resolve_data_dir(service: str = "dorm") -> str:
    """按优先级确定数据目录：环境变量 > systemd 单元 > 常见目录 > 项目下 data。"""
    env_value = os.environ.get("DORM_DATA_DIR")
    if env_value:
        return env_value
    for candidate in (_from_systemd(service), _from_unit_file(service)):
        if candidate:
            return candidate
    for candidate in ("/www/dorm-data", "/opt/dorm-data"):
        if Path(candidate).is_dir():
            return candidate
    return str(ROOT / "data")


def setup(service: str = "dorm") -> Path:
    """对齐数据目录，返回实际使用的路径。"""
    data_dir = Path(resolve_data_dir(service)).resolve()
    os.environ["DORM_DATA_DIR"] = str(data_dir)
    return data_dir


SYSTEMD_SERVICE = os.environ.get("DORM_SERVICE", "dorm")
DATA_DIR = setup(SYSTEMD_SERVICE)
