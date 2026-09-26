@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0Zhilian\Zhilian.exe" (
  start "知链" /D "%~dp0Zhilian" "%~dp0Zhilian\Zhilian.exe"
  exit /b 0
)
if exist "%~dp0Zhilian.exe" (
  start "知链" /D "%~dp0" "%~dp0Zhilian.exe"
  exit /b 0
)
echo [错误] 未找到免安装包中的 Zhilian.exe。
echo 请先解压完整安装包，再运行本文件。
pause
exit /b 1
