#!/bin/bash
# [Define404] 화면 나누기: 왼쪽 = 구글 미트 창, 오른쪽 = 미팅냥 화면(요지·다음 한마디 | 준비 자료·정리).
# 쓰는 법: 미트 회의에 들어간 뒤 ./tools/layout.sh  (미트 쪽 폭을 바꾸려면 ./tools/layout.sh 40)
# 미트 탭이 있는 크롬 창을 왼쪽에, 미팅냥 화면을 오른쪽 새 창에 둡니다.
LEFT_PCT=${1:-33}
ASSIST_URL="http://localhost:8790/"

osascript <<EOF
tell application "Finder" to set b to bounds of window of desktop
set screenW to item 3 of b
set screenH to item 4 of b
set topY to 25
set splitX to (screenW * $LEFT_PCT / 100) as integer

tell application "Google Chrome"
  activate
  -- 미트 탭 찾기
  set meetWin to missing value
  set meetIdx to 0
  repeat with w in windows
    set i to 0
    repeat with t in tabs of w
      set i to i + 1
      set u to URL of t
      set code to ""
      if u contains "meet.google.com/" then set code to text ((offset of "meet.google.com/" in u) + 16) thru -1 of u
      -- 회의 주소만 고른다 (abc-defg-hij 꼴). 미트 첫 화면(/home 등)은 건너뛴다
      if code contains "-" then
        set meetWin to w
        set meetIdx to i
        exit repeat
      end if
    end repeat
    if meetWin is not missing value then exit repeat
  end repeat
  if meetWin is missing value then error "열린 구글 미트 회의 탭이 없습니다. 미트에 먼저 들어가 주세요."

  -- 미트 탭이 다른 탭과 같이 있으면 자기 창으로 떼어 낸다
  if (count of tabs of meetWin) > 1 then
    set meetURL to URL of tab meetIdx of meetWin
    set active tab index of meetWin to meetIdx
  end if
  set bounds of meetWin to {0, topY, splitX, screenH}

  -- 미팅냥 창: 이미 열린 탭이 있으면 그 창, 없으면 새 창
  set assistWin to missing value
  repeat with w in windows
    repeat with t in tabs of w
      if URL of t contains ":8790" then set assistWin to w
    end repeat
  end repeat
  if assistWin is missing value or assistWin is meetWin then
    set assistWin to make new window
    set URL of active tab of assistWin to "$ASSIST_URL"
  end if
  set bounds of assistWin to {splitX, topY, screenW, screenH}
end tell
EOF
