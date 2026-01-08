@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Ensure we run from repo root (this script's directory)
cd /d "%~dp0"

rem Choose python: prefer venv if present
set PY=python
if exist ".venv_rag\Scripts\python.exe" (
  set PY=.venv_rag\Scripts\python.exe
)

rem Ensure output dirs exist
if not exist "data_processed" mkdir "data_processed"
if not exist "data_processed\build_reports" mkdir "data_processed\build_reports"

echo [1/2] Capture environment report...
%PY% tools\capture_rag_env.py --out data_processed\env_report.json
if errorlevel 1 (
  echo [FAIL] capture_rag_env.py
  exit /b 2
)

echo [2/2] Run profile with timing (smoke)...
%PY% tools\run_profile_with_timing.py --profile build_profile_schemeB.json --smoke
set RC=%ERRORLEVEL%
if not "%RC%"=="0" (
  echo [FAIL] run_profile_with_timing.py rc=%RC%
  exit /b %RC%
)

echo [OK] smoke run finished.
exit /b 0
