@echo off
rem build.cmd - one-command build of the offline APK on Windows (no WSL needed).
rem
rem   build.cmd                       (uses original\*.apk, output in out\)
rem   build.cmd BASE.apk SPLIT.apk    (explicit inputs)
rem   set BRANCH=0x14c00a8=0x14c6498
rem   set NO_RENAME=1 & set OUT=out-native & build.cmd   (native-code variant)
rem
rem Requirements: Python 3.9+ (https://www.python.org/downloads/, tick "Add to
rem PATH") and internet access on the first run (installs `cryptography`).
rem OpenSSL is not needed.

setlocal
cd /d "%~dp0"

set "PY=.tools\venv\Scripts\python.exe"
set "OUT=out"
set "BASE="
set "SPLIT="
set "MODE=--single"

:parse
if "%~1"=="" goto :parsed
if /i "%~1"=="--pair" (set "MODE=" & shift & goto :parse)
if "%~2"=="" goto :parsed
set "BASE=%~1"
set "SPLIT=%~2"
shift
shift
goto :parse
:parsed

if "%BASE%"=="" (
  for %%f in (original\*base*.apk) do if not defined BASE set "BASE=%%~ff"
  for %%f in (original\*split*arm64*.apk) do if not defined SPLIT set "SPLIT=%%~ff"
)

if "%BASE%"=="" (
  echo !! base APK not found. Put the two Cafe Bazaar 3.4.2 files in original\:
  echo    pesarkhande-3.4.2-base.apk
  echo    pesarkhande-3.4.2-split_config.arm64_v8a.apk
  exit /b 1
)
if "%SPLIT%"=="" (
  echo !! split APK not found (it carries libil2cpp.so and the other native libs^).
  exit /b 1
)

if not exist "%PY%" (
  echo [deps] creating virtualenv in .tools\venv
  python -m venv .tools\venv || goto :error
  "%PY%" -m pip install -q --upgrade pip || goto :error
)

"%PY%" -c "import cryptography" 2>nul || "%PY%" -m pip install -q cryptography || goto :error
echo [deps] ok

if not exist "%OUT%" mkdir "%OUT%"

set "RENAME_ARGS=--rename ConnectionScreen=MainMenu"
if defined NO_RENAME set "RENAME_ARGS="
set "BRANCH_ARGS="
if defined BRANCH set "BRANCH_ARGS=--branch %BRANCH%"
"%PY%" tools\patch.py build --base "%BASE%" --split "%SPLIT%" %MODE% %RENAME_ARGS% %BRANCH_ARGS% --key keys\release.key.pem --cert keys\release.cert.pem --out "%OUT%" || goto :error

echo.
echo Build finished -^> %OUT%\pesarkhande-offline-arm64.apk
echo Install:  adb install %OUT%\pesarkhande-offline-arm64.apk
echo Guide:    docs\04-install-guide.md
exit /b 0

:error
echo Build failed.
exit /b 1
