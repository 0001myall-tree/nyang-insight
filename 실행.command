#!/bin/bash
# Clear Insight 실행 파일 (맥용)
cd "$(dirname "$0")"

# 파이썬 확인
if ! command -v python3 &> /dev/null; then
  osascript -e 'display dialog "파이썬이 설치되지 않았어요!\n\nhttps://python.org 에서 무료로 다운로드할 수 있어요." buttons {"확인"} default button "확인" with icon caution'
  open "https://www.python.org/downloads/"
  exit 1
fi

# 브라우저 열기 (서버 시작 후 1.5초 뒤)
sleep 1.5 && open "http://localhost:8000" &

# 서버 시작
python3 server.py
