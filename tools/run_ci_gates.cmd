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
REM Exit codes (aligned with docs/reference/REFERENCE.md)
REM - 0: PASS
REM - 2: FAIL  (contract/gate violation, test failures)
REM - 3: ERROR (environment/setup failure)
REM
REM Usage:
REM   tools\run_ci_gates.cmd
REM   tools\run_ci_gates.cmd --with-embed
REM   tools\run_ci_gates.cmd --no-install
REM   tools\run_ci_gates.cmd --venv .venv_ci

set "ROOT=%~dp0.."
cd /d "%ROOT%" || exit /b 3

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
echo [FAIL] unknown arg: %~1
echo Usage: tools\run_ci_gates.cmd [--venv .venv_ci] [--no-install] [--with-embed]
exit /b 2

:parsed

set "PY=%VENV%\Scripts\python.exe"

if not exist "%PY%" (
  call :find_base_python
  if not defined BASEPY (
    echo [ERROR] cannot find a base Python to create venv.
    echo         Install Python 3.11+ and ensure 'py' or 'python' is on PATH.
    exit /b 3
  )
  echo [INFO] creating venv %VENV% using: !BASEPY!
  !BASEPY! -m venv "%VENV%"
  if errorlevel 1 exit /b 3
)

set "PY=%VENV%\Scripts\python.exe"
echo [INFO] python = %PY%

REM 1) Preflight + repo-structure gates (stop before any pip install)
call :gate "%PY%" tools\check_pyproject_preflight.py --ascii-only
if errorlevel 1 exit /b !ERRORLEVEL!

call :gate "%PY%" tools\gen_tools_wrappers.py --check
if errorlevel 1 exit /b !ERRORLEVEL!

call :gate "%PY%" tools\check_tools_layout.py --mode fail
if errorlevel 1 exit /b !ERRORLEVEL!

call :gate "%PY%" tools\check_exit_code_contract.py --root .
if errorlevel 1 exit /b !ERRORLEVEL!

call :gate "%PY%" tools\validate_review_spec.py --root .
if errorlevel 1 exit /b !ERRORLEVEL!

REM 2) (Optional) install/update deps
if "%NO_INSTALL%"=="0" (
  "%PY%" -m pip install -U pip
  if errorlevel 1 exit /b 3

  "%PY%" -m pip install -e ".[ci]"
  if errorlevel 1 exit /b 3

  if "%WITH_EMBED%"=="1" (
    "%PY%" -m pip install -e ".[embed]"
    if errorlevel 1 exit /b 3
  )
) else (
  echo [INFO] --no-install: skip pip install steps
)

REM 3) Run PR/CI Lite gates
call :gate "%PY%" tools\check_cli_entrypoints.py
if errorlevel 1 exit /b !ERRORLEVEL!

call :gate "%PY%" tools\check_md_refs_contract.py
if errorlevel 1 exit /b !ERRORLEVEL!

call :gate "%PY%" tools\check_readme_code_sync.py --root .
if errorlevel 1 exit /b !ERRORLEVEL!

call :gate "%PY%" -m pytest -q
if errorlevel 1 exit /b !ERRORLEVEL!

echo [PASS] CI/PR Lite gates OK
exit /b 0


:gate
REM Run a gate command and normalize exit codes to {0,2,3}.
REM - rc=0 => 0
REM - rc=2/3 => propagate
REM - rc=1 => map to FAIL (2) (common for tools like pytest)
REM - rc>=4 => map to ERROR (3)
%*
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" exit /b 0
if "%RC%"=="2" exit /b 2
if "%RC%"=="3" exit /b 3
if "%RC%"=="1" exit /b 2
REM Best-effort numeric compare: treat rc>=4 as ERROR
set /a "RC_NUM=%RC%" >nul 2>nul
if not errorlevel 1 (
  if !RC_NUM! GEQ 4 exit /b 3
)
exit /b 2


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
