@echo off
setlocal enabledelayedexpansion

REM One-click wrapper for Public Release Hygiene Audit.
REM Usage:
REM   tools\run_public_release_audit.cmd
REM   tools\run_public_release_audit.cmd --history 1

set "REPO=%~dp0.."
set "PY=python"

REM If you want to force a venv python, set PY like:
REM set "PY=%REPO%\.venv_ci\Scripts\python.exe"

%PY% "%REPO%\tools\check_public_release_hygiene.py" --repo "%REPO%" %*
set "EC=%ERRORLEVEL%"

echo ExitCode=%EC%
exit /b %EC%
