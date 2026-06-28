#!/bin/bash
cd "$(dirname "$0")"

# Python 체크
if ! command -v python3 &> /dev/null; then
  osascript -e 'display dialog "파이썬이 설치되지 않았어요!\nhttps://python.org 에서 무료로 다운로드하세요." buttons {"확인"} default button "확인"'
  open https://www.python.org/downloads/
  exit 1
fi

# youtube-transcript-api 설치 (없으면 자동 설치)
if ! python3 -c "import youtube_transcript_api" 2>/dev/null; then
  echo "📦 youtube-transcript-api 설치 중..."
  pip3 install youtube-transcript-api --quiet
fi

# 브라우저 열기 (서버 뜨기 전에 살짝 대기)
sleep 1 && open http://localhost:8000 &

python3 server.py
