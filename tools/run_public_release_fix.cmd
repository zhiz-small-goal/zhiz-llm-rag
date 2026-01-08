@echo off
setlocal enabledelayedexpansion

REM One-click wrapper for fix script (dry-run by default).
REM Usage:
REM   tools\run_public_release_fix.cmd
REM   tools\run_public_release_fix.cmd --apply

set "REPO=%~dp0.."
set "PY=python"

%PY% "%REPO%\tools\fix_public_release_hygiene.py" --repo "%REPO%" %*
set "EC=%ERRORLEVEL%"

echo ExitCode=%EC%
exit /b %EC%
