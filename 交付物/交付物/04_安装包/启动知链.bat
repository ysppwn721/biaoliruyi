@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo.
echo  ============================================================
echo   知链 · 跨文档结论验证与增量修复   v0.2.0   （Windows 免安装）
echo  ============================================================
echo.

REM --- 1. 确认 Python ---
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo  [错误] 未找到 Python。请先安装 Python 3.11 及以上版本：
  echo        https://www.python.org/downloads/
  echo        安装时请勾选 "Add Python to PATH"。
  pause
  exit /b 1
)

REM --- 2. 首次运行：创建虚拟环境并安装依赖 ---
if not exist ".venv\Scripts\python.exe" (
  echo  [1/3] 首次运行：创建虚拟环境 .venv ...
  %PY% -m venv .venv
  if errorlevel 1 ( echo  [错误] 创建虚拟环境失败。 & pause & exit /b 1 )
  echo  [2/3] 安装依赖（需联网，约 1-2 分钟）...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 ( echo  [错误] 依赖安装失败，请检查网络后重试。 & pause & exit /b 1 )
) else (
  echo  [提示] 检测到已有虚拟环境，跳过安装。
)

REM --- 3. 启动服务并打开浏览器 ---
echo  [3/3] 启动服务：http://127.0.0.1:8765
start "" "http://127.0.0.1:8765"
".venv\Scripts\python.exe" run.py

echo.
echo  服务已停止。按任意键关闭窗口。
pause >nul
