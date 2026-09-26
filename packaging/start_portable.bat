@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0Zhilian.exe" (
  echo [ERROR] Zhilian.exe was not found.
  echo Extract the complete Windows portable package first.
  pause
  exit /b 1
)
start "Zhilian" /D "%~dp0" "%~dp0Zhilian.exe"
exit /b 0
