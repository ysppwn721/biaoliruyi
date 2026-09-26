@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0Zhilian.exe" (
  echo [错误] 未找到 Zhilian.exe。
  echo 请先解压完整的 Windows 免安装包，再运行本文件。
  pause
  exit /b 1
)
start "知链" /D "%~dp0" "%~dp0Zhilian.exe"
exit /b 0
