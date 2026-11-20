@echo off
setlocal EnableExtensions
title V50 Launcher
set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"

set "MODE="
if /i "%~1"=="--dry-run" set "MODE=dry"
if /i "%~1"=="--pick-client" set "MODE=pick"
if /i "%~1"=="-c" set "MODE=pick"
if /i "%~1"=="--set-client" set "MODE=set"

rem ---- client.exe: env TFD_CLIENT > client.txt > auto-detect ----
set "CLIENT="
if defined TFD_CLIENT if exist "%TFD_CLIENT%" set "CLIENT=%TFD_CLIENT%"
if not defined CLIENT if exist "%DIR%\client.txt" for /f "usebackq delims=" %%C in ("%DIR%\client.txt") do if not defined CLIENT set "CLIENT=%%C"
if defined CLIENT if not exist "%CLIENT%" set "CLIENT="

if "%MODE%"=="set" (
  call :pick_client "%~2"
  call :show_client
  exit /b 0
)
if "%MODE%"=="pick" (
  call :pick_client
  call :show_client
  exit /b 0
)

call :find_python
if not defined PY (
  echo [ERROR] No usable 64-bit Python 3.7+ found.
  echo         Option 1: install Python 3.x
  echo         Option 2: set TFD_PY=C:\path\to\python.exe
  pause
  exit /b 9
)
echo [python] "%PY%"

if defined CLIENT (
  echo [client] "%CLIENT%"
  set "TFD_CLIENT=%CLIENT%"
) else (
  echo [client] not set yet
)

if "%MODE%"=="dry" (
  call :check_client
  "%PY%" -B -c "import sys;print('  version:',sys.version.split()[0]);print('  64bit  :',sys.maxsize>2**32)"
  if exist "%DIR%\inject_v50.py" (
    "%PY%" -B -c "import sys;sys.path.insert(0,r'%DIR%');import inject_v50;print('  vendor :',inject_v50.VENDOR);print('  client :',inject_v50.CLIENT);print('  frida  :',inject_v50.frida.__version__)"
  )
  echo.
  echo dry run complete ^(nothing launched^).
  exit /b 0
)

rem ---- ask the user to pick the client once, if it is still unknown ----
if not defined CLIENT (
  echo [client] no client remembered, opening a picker...
  call :pick_client
)
if defined CLIENT (
  call :use_client
  call :show_client
  call :check_client
) else (
  echo [ERROR] client exe not specified.
  echo         Run: "%~nx0" --pick-client
  pause
  exit /b 8
)

echo [1/3] starting launcher...
if exist "%DIR%\TFDLauncher.exe" (
  start "" "%DIR%\TFDLauncher.exe"
) else (
  echo [warn] TFDLauncher.exe not found: "%DIR%\TFDLauncher.exe"
)

echo [2/3] waiting 8 seconds...
timeout /t 8 /nobreak >nul

echo [3/3] injecting patch...
if not exist "%DIR%\inject_v50.py" (
  echo [ERROR] inject_v50.py not found
  pause
  exit /b 2
)
"%PY%" -B "%DIR%\inject_v50.py"
set "RC=%ERRORLEVEL%"
echo.
echo done. ^(exit code %RC%^)
timeout /t 6 /nobreak >nul
exit /b %RC%


:pick_client
rem usage: call :pick_client [file-or-folder]   (no arg -> GUI dialog)
set "PICKED="
if "%~1"=="" (
  for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -STA -File "%DIR%\pick_client.ps1"`) do set "PICKED=%%P"
) else (
  for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -STA -File "%DIR%\pick_client.ps1" -Value "%~1"`) do set "PICKED=%%P"
)
if defined PICKED if not "%PICKED%"=="INVALID" set "CLIENT=%PICKED%"
exit /b 0


:show_client
if defined CLIENT echo [client] "%CLIENT%"
exit /b 0


:use_client
if defined CLIENT set "TFD_CLIENT=%CLIENT%"
exit /b 0


:check_client
rem warn when the selected exe is not the build this patch was made for
if not defined CLIENT exit /b 0
set "CK="
for /f "skip=1 tokens=* delims=" %%H in ('certutil -hashfile "%CLIENT%" SHA256 2^>nul') do if not defined CK set "CK=%%H"
if not defined CK exit /b 0
set "CK=%CK: =%"
rem 期望哈希 = 本补丁适配的 build 26722146。权威校验在 selfcheck.py（含完整 sha256 比对）。
set "CKOK=a601a30d"
echo [client] sha256: %CK:~0,8%...
if /i not "%CK:~0,8%"=="%CKOK%" (
  echo [warn] this exe is NOT the build this patch fits.
  echo        It usually closes right after launch ^(flash exit^).
  echo        Run "%~nx0" --pick-client to choose another client folder.
)
exit /b 0


:find_python
set "PY="

rem ---- 0) explicit override ----
if defined TFD_PY call :try_py "%TFD_PY%"

rem ---- 1) bundled runtime, located relative to this script (no hard-coded drive/path) ----
call :try_py "%DIR%\runtime\python.exe"
call :try_py "%DIR%\python.exe"
call :try_py "%DIR%\vendor\runtime\python.exe"
call :scan_tree "%DIR%"
call :scan_tree "%DIR%\.."
call :scan_tree "%DIR%\..\.."
call :scan_tree "%DIR%\..\..\.."
if defined PY goto :find_python_done

rem ---- 2) Windows launcher "py -3" knows where Python is installed ----
for /f "delims=" %%I in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do call :try_py "%%I"
if defined PY goto :find_python_done

rem ---- 3) python on PATH (Microsoft Store stub fails the self-test and is skipped) ----
for /f "delims=" %%I in ('where python 2^>nul') do call :try_py "%%I"
if defined PY goto :find_python_done

rem ---- 4) common install locations ----
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do call :try_py "%%~fD\python.exe"
for /d %%D in ("%ProgramFiles%\Python3*") do call :try_py "%%~fD\python.exe"
for /d %%D in ("%ProgramFiles(x86)%\Python3*") do call :try_py "%%~fD\python.exe"
for /d %%D in ("C:\Python3*") do call :try_py "%%~fD\python.exe"

:find_python_done
exit /b 0


:scan_tree
rem look for .tfd-patch\releases\*\runtime\python.exe in this dir and its direct subdirs
if defined PY exit /b 0
call :scan_patch "%~1"
if defined PY exit /b 0
if not exist "%~1" exit /b 0
for /d %%D in ("%~1\*") do call :scan_patch "%%~fD"
exit /b 0

:scan_patch
if defined PY exit /b 0
if not exist "%~1\.tfd-patch\releases" exit /b 0
for /d %%V in ("%~1\.tfd-patch\releases\*") do call :try_py "%%~fV\runtime\python.exe"
exit /b 0


:try_py
rem candidate must exist, run, be 64-bit and >= 3.7
if defined PY exit /b 0
if not exist "%~1" exit /b 0
"%~1" -B -c "import sys;raise SystemExit(0 if sys.maxsize>2**32 and sys.version_info>=(3,7) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=%~1"
exit /b 0
