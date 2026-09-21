@echo off
REM 在 Windows 上预取 GitHub 依赖并构建。须在本机执行，不能从 Linux 交叉编译。
setlocal
cd /d "%~dp0\.."
uv run python scripts\prefetch_flet_runtime.py
if errorlevel 1 exit /b 1
uv run flet build windows --skip-flutter-doctor --yes
if errorlevel 1 exit /b 1
echo ==^> Windows 构建目录: build\windows
