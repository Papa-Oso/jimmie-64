@echo off
title Jimmie 64 - writing and voicing new lines
pushd "%~dp0" || exit /b 1
"..\.venv\Scripts\python.exe" -B bake_all.py %*
set "result=%errorlevel%"
popd
pause
exit /b %result%
