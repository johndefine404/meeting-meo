#!/bin/bash
# [Define404] 미팅냥 앱에서 부르는 실행기: 켜져 있으면 화면만 열고, 꺼져 있으면 켠다.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$HOME/Library/Logs/meeting-meo.log"
if curl -s -o /dev/null --max-time 1 http://localhost:8790/; then
  open "http://localhost:8790/"
else
  cd "$ROOT" && nohup ./meeting-meo >> "$LOG" 2>&1 &
fi
