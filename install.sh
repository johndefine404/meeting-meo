#!/bin/bash
# [Define404] 미팅냥 설치: 받아쓰기 엔진, 소리 받기 프로그램, 파이썬 환경
set -e
cd "$(dirname "$0")"

if [ "$(uname)" != "Darwin" ]; then echo "지금은 맥만 지원합니다."; exit 1; fi
if ! command -v whisper-server >/dev/null; then
  if command -v brew >/dev/null; then brew install whisper-cpp; else echo "Homebrew(https://brew.sh)를 먼저 설치하십시오."; exit 1; fi
fi
if ! command -v swiftc >/dev/null; then echo "xcode-select --install 로 개발 도구를 먼저 설치하십시오."; exit 1; fi

echo "소리 받기 프로그램 만드는 중"
swiftc -O -o mac/tap/meet-tap mac/tap/main.swift
echo "PDF 만들기 프로그램 만드는 중"
swiftc -O -o mac/pdf/meet-pdf mac/pdf/main.swift

echo "파이썬 환경 만드는 중"
python3 -m venv .venv
.venv/bin/pip install -q -r server/requirements.txt

echo "미팅냥 앱 만드는 중"
./tools/make_app.sh

echo "설치 끝. 응용 프로그램 폴더의 미팅냥을 누르거나 ./meeting-meo 로 실행하십시오."
echo "처음 실행 때 받아쓰기 모델(약 570MB)을 받고, 화면 기록·마이크 권한을 물어봅니다."
