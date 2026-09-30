@echo off
REM 在 Windows x64 上把 flet build windows 目录打成 Inno Setup 安装包。
REM 须在本机执行，不能从 Linux 交叉编译。缺少 Inno Setup 6 时会尝试 winget 安装。
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0\.."

set "REBUILD=0"
if /I "%~1"=="--rebuild" set "REBUILD=1"

set "BUNDLE=build\windows"
set "EXE=%BUNDLE%\markitdown-gui.exe"
set "OUT_DIR=dist\windows"

if not exist "%EXE%" set "REBUILD=1"
if "%REBUILD%"=="1" (
  echo ==^> Building Windows bundle...
  call scripts\build-windows.cmd
  if errorlevel 1 exit /b 1
) else (
  echo ==^> Using existing Windows bundle: %BUNDLE%
)

if not exist "%EXE%" (
  echo Missing %EXE% after build. >&2
  exit /b 1
)

echo ==^> Ensuring Pandoc in bundle...
uv run python scripts\ensure_pandoc_windows.py
if errorlevel 1 exit /b 1

REM 从 pyproject.toml 读 project.version
for /f "usebackq delims=" %%V in (`uv run python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"`) do set "APP_VERSION=%%V"
if not defined APP_VERSION (
  echo Failed to read version from pyproject.toml. >&2
  exit /b 1
)
echo ==^> Version: %APP_VERSION%

call :find_iscc
if defined ISCC goto :have_iscc

echo ==^> Inno Setup 6 ^(ISCC.exe^) not found. Trying winget install...
where winget >nul 2>&1
if errorlevel 1 (
  echo winget not found. Install Inno Setup 6 manually: >&2
  echo   https://jrsoftware.org/isinfo.php >&2
  echo Or install winget, then: winget install JRSoftware.InnoSetup >&2
  exit /b 1
)
winget install --id JRSoftware.InnoSetup -e --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
  echo winget install JRSoftware.InnoSetup failed. >&2
  echo Install manually from https://jrsoftware.org/isinfo.php then re-run this script. >&2
  exit /b 1
)

REM winget 安装后当前会话 PATH 可能未刷新；直接扫常见路径
call :find_iscc
if not defined ISCC (
  echo Inno Setup installed but ISCC.exe still not found. >&2
  echo Close this terminal, open a new one, and re-run: scripts\build-windows-setup.cmd >&2
  echo Or open "Inno Setup Compiler" once from the Start menu, then retry. >&2
  exit /b 1
)

:have_iscc
echo ==^> Using ISCC: %ISCC%
if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"

"%ISCC%" /DMyAppVersion=%APP_VERSION% "scripts\markitdown-gui.iss"
if errorlevel 1 exit /b 1

set "SETUP=%OUT_DIR%\MarkItDown_GUI-%APP_VERSION%-x64-setup.exe"
if not exist "%SETUP%" (
  echo Expected installer missing: %SETUP% >&2
  exit /b 1
)
echo ==^> Windows installer: %SETUP%
exit /b 0

:find_iscc
set "ISCC="
where iscc >nul 2>&1
if not errorlevel 1 (
  for /f "delims=" %%I in ('where iscc 2^>nul') do (
    set "ISCC=%%I"
    goto :eof
  )
)
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
  set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
  goto :eof
)
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
  set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  goto :eof
)
if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" (
  set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
  goto :eof
)
goto :eof
