@echo off
setlocal
set "PY=%RAG_PYTHON%"
if "%PY%"=="" set "PY=python"
"%PY%" %*
set "RC=%ERRORLEVEL%"
endlocal & exit /b %RC%
