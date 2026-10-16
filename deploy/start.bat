@echo off
chcp 65001 >nul
rem ============================================================
rem  生活助手 · Windows 本地/服务器启动脚本
rem  第一次运行会自动创建虚拟环境并安装依赖
rem ============================================================
setlocal
cd /d "%~dp0.."

set DORM_PORT=8090
if not "%1"=="" set DORM_PORT=%1

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] 创建虚拟环境……
  python -m venv .venv
  if errorlevel 1 (
    echo 创建虚拟环境失败，请先安装 Python 3.9 以上版本并加入 PATH
    pause
    exit /b 1
  )
  echo [2/3] 安装依赖……
  .venv\Scripts\python.exe -m pip install --upgrade pip
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 (
    echo 依赖安装失败，尝试使用阿里云镜像重试……
    .venv\Scripts\python.exe -m pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
  )
) else (
  echo [1/3] 虚拟环境已存在
  echo [2/3] 检查依赖……
  .venv\Scripts\python.exe -m pip install -q -r requirements.txt
)

echo [3/3] 启动服务……
echo.
echo   本机访问：http://127.0.0.1:%DORM_PORT%
echo   局域网访问：http://本机IP:%DORM_PORT%  （手机连同一个 WiFi 即可）
echo   管理员账号：admin / admin123
echo.
set DORM_PORT=%DORM_PORT%
.venv\Scripts\python.exe run.py

pause
