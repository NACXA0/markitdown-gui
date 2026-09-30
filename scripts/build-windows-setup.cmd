@echo off
REM 在 Windows x64 上把 flet build windows 目录打成 Inno Setup 安装包。
REM 须在本机执行，不能从 Linux 交叉编译。需要已安装 Inno Setup 6。
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

set "ISCC="
where iscc >nul 2>&1
if not errorlevel 1 (
  for /f "delims=" %%I in ('where iscc') do (
    set "ISCC=%%I"
    goto :found_iscc
  )
)
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
  set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
  goto :found_iscc
)
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
  set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  goto :found_iscc
)

echo Inno Setup 6 ^(ISCC.exe^) not found. >&2
echo Install with: winget install JRSoftware.InnoSetup >&2
exit /b 1

:found_iscc
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
