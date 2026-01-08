@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM =============================================================
REM CI/PR Lite gates runner for Windows CMD
REM
REM Design goals
REM - Make the gate workflow hard to misuse for beginners.
REM - Fail-fast: any failure stops the remaining steps.
REM - Dependency-free: only Python + pip.
REM
REM Usage:
REM   tools\run_ci_gates.cmd
REM   tools\run_ci_gates.cmd --with-embed
REM   tools\run_ci_gates.cmd --no-install
REM   tools\run_ci_gates.cmd --venv .venv_ci

set "ROOT=%~dp0.."
cd /d "%ROOT%" || exit /b 1

set "VENV=.venv_ci"
set "WITH_EMBED=0"
set "NO_INSTALL=0"

:parse
if "%~1"=="" goto parsed
if /I "%~1"=="--with-embed" (
  set "WITH_EMBED=1"
  shift
  goto parse
)
if /I "%~1"=="--no-install" (
  set "NO_INSTALL=1"
  shift
  goto parse
)
if /I "%~1"=="--venv" (
  set "VENV=%~2"
  shift
  shift
  goto parse
)
echo [FATAL] unknown arg: %~1
echo Usage: tools\run_ci_gates.cmd [--venv .venv_ci] [--no-install] [--with-embed]
exit /b 2

:parsed

set "PY=%VENV%\Scripts\python.exe"

if not exist "%PY%" (
  call :find_base_python
  if not defined BASEPY (
    echo [FATAL] cannot find a base Python to create venv.
    echo        Install Python 3.11+ and ensure 'py' or 'python' is on PATH.
    exit /b 2
  )
  echo [INFO] creating venv %VENV% using: %BASEPY%
  %BASEPY% -m venv "%VENV%"
  if errorlevel 1 exit /b 1
)

set "PY=%VENV%\Scripts\python.exe"
echo [INFO] python = %PY%

REM 1) Preflight gate (stops before any pip install)
"%PY%" tools\check_pyproject_preflight.py --ascii-only
if errorlevel 1 (
  echo [STOP] preflight gate failed; skip remaining steps.
  exit /b 2
)

REM 2) (Optional) install/update deps
if "%NO_INSTALL%"=="0" (
  "%PY%" -m pip install -U pip
  if errorlevel 1 exit /b 1

  "%PY%" -m pip install -e ".[ci]"
  if errorlevel 1 exit /b 1

  if "%WITH_EMBED%"=="1" (
    "%PY%" -m pip install -e ".[embed]"
    if errorlevel 1 exit /b 1
  )
) else (
  echo [INFO] --no-install: skip pip install steps
)

REM 3) Run PR/CI Lite gates
"%PY%" tools\check_cli_entrypoints.py
if errorlevel 1 exit /b 1

"%PY%" tools\check_md_refs_contract.py
if errorlevel 1 exit /b 1

"%PY%" -m pytest -q
if errorlevel 1 exit /b 1

echo [PASS] CI/PR Lite gates OK
exit /b 0


:find_base_python
set "BASEPY="

where py >nul 2>nul
if not errorlevel 1 (
  py -3.12 -V >nul 2>nul && (set "BASEPY=py -3.12" & exit /b 0)
  py -3.11 -V >nul 2>nul && (set "BASEPY=py -3.11" & exit /b 0)
  py -3 -V    >nul 2>nul && (set "BASEPY=py -3"    & exit /b 0)
)

where python >nul 2>nul
if not errorlevel 1 (
  set "BASEPY=python"
  exit /b 0
)

exit /b 0
