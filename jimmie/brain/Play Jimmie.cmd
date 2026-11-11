@echo off
title Jimmie 64 - with the brain
pushd "%~dp0" || exit /b 1
"..\.venv\Scripts\python.exe" -B play.py %*
set "result=%errorlevel%"
popd
if not "%result%"=="0" pause
exit /b %result%
