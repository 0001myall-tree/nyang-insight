@echo off
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel% neq 0 (
  echo 파이썬이 설치되지 않았어요!
  echo https://python.org 에서 무료로 다운로드하세요.
  start https://www.python.org/downloads/
  pause
  exit
)
start "" "http://localhost:8000"
python server.py
pause
