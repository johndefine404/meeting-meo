#!/usr/bin/env python3
# [Define404]
"""미팅냥 로고 로티 생성기 (표준 라이브러리만 사용).

냥 시리즈 공통 고양이(web/logo.svg)를 그대로 옮기고 구간 두 개를 한 컴포지션에 담는다.
  intro : 노란 원이 톡 튀어나오고, 고양이가 아래에서 솟아오르며, 귀가 쫑긋 선다.
  idle  : 눈 깜빡임, 한쪽 귀 쫑긋, 꼬리 살랑. 화면에서 이 구간만 반복한다.

사용: python3 tools/make_logo_lottie.py  -> web/logo.json
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "web", "logo.json")

FR = 60
SEG = {"intro": (0, 48), "idle": (60, 300)}
OP = 301

YELLOW = [0.949, 0.698, 0.0, 1]
WHITE = [1, 1, 1, 1]
INK = [0.078, 0.078, 0.078, 1]

OUTE = {"x": [0.16], "y": [1]}, {"x": [0.3], "y": [1]}
INOUT = {"x": [0.37], "y": [0]}, {"x": [0.63], "y": [1]}


def static(v):
    return {"a": 0, "k": v}


def anim(keys, ease=INOUT):
    """keys = [(frame, value), ...]"""
    out = []
    for n, (t, v) in enumerate(keys):
        k = {"t": t, "s": v if isinstance(v, list) else [v]}
        if n < len(keys) - 1:
            k["o"], k["i"] = ease
        out.append(k)
    return {"a": 1, "k": out}


def tr(p=(0, 0), a=(0, 0), s=(100, 100), r=0, o=100):
    return {"ty": "tr", "p": static(list(p)), "a": static(list(a)), "s": static(list(s)), "r": static(r), "o": static(o),
            "sk": static(0), "sa": static(0)}


def path(vs, ins=None, outs=None, closed=True):
    n = len(vs)
    return {"ty": "sh", "ks": static({"v": vs, "i": ins or [[0, 0]] * n, "o": outs or [[0, 0]] * n, "c": closed})}


def fill(c):
    return {"ty": "fl", "c": static(c), "o": static(100), "r": 1}


def stroke(c, w):
    return {"ty": "st", "c": static(c), "o": static(100), "w": static(w), "lc": 2, "lj": 2}


def group(items):
    return {"ty": "gr", "it": items + [tr()]}


def layer(ind, name, shapes, p, a, s=None, r=None, o=None, parent=None):
    ks = {"o": o or static(100), "r": r or static(0), "p": p if isinstance(p, dict) else static(list(p) + [0]),
          "a": static(list(a) + [0]), "s": s or static([100, 100, 100])}
    lay = {"ddd": 0, "ind": ind, "ty": 4, "nm": name, "sr": 1, "ks": ks, "ao": 0, "shapes": shapes,
           "ip": 0, "op": OP, "st": 0, "bm": 0}
    if parent:
        lay["parent"] = parent
    return lay


I0, I1 = SEG["intro"]
L0, L1 = SEG["idle"]

# 눈 깜빡임: idle 구간에 두 번 (한 번은 두 번 연달아)
def blink_keys():
    keys = [(0, [100, 100, 100])]
    for t in (L0 + 30, L0 + 150, L0 + 162):
        keys += [(t, [100, 100, 100]), (t + 4, [100, 10, 100]), (t + 9, [100, 100, 100])]
    return anim(keys)


# 몸통 묶음: 아래에서 솟아오른다 (부모 레이어)
body_rise = anim([(0, [60, 88, 0]), (10, [60, 88, 0]), (34, [60, 66, 0]), (44, [60, 69, 0]), (52, [60, 69, 0])], OUTE)
body = layer(2, "cat", [], body_rise, (60, 69))
body["ty"] = 3  # 널 레이어: 고양이 전체를 함께 움직인다
del body["shapes"]
# 널 레이어의 투명도는 자식에게 안 넘어가므로, 크기로 나타나게 한다
body["ks"]["s"] = anim([(0, [0, 0, 100]), (10, [0, 0, 100]), (30, [104, 104, 100]), (40, [100, 100, 100])], OUTE)

eyes = layer(3, "eyes", [
    group([{"ty": "el", "p": static([37, 72]), "s": static([6, 9])}, fill(INK)]),
    group([{"ty": "el", "p": static([57, 72]), "s": static([6, 9])}, fill(INK)]),
], (47, 72), (47, 72), s=blink_keys(), parent=2)

whiskers = layer(4, "whiskers", [
    group([path([[15, 74], [26, 73]], closed=False), stroke(INK, 1.8)]),
    group([path([[15, 80], [26, 78]], closed=False), stroke(INK, 1.8)]),
    group([path([[68, 73], [79, 74]], closed=False), stroke(INK, 1.8)]),
    group([path([[68, 78], [79, 80]], closed=False), stroke(INK, 1.8)]),
], (47, 76), (47, 76), parent=2)

face = layer(5, "face", [group([{"ty": "rc", "p": static([50, 69]), "s": static([68, 44]), "r": static(22)}, fill(WHITE)])],
             (50, 69), (50, 69), parent=2)

# 귀: intro 끝에 쫑긋, idle 중간에 오른쪽 귀만 한 번 더
ear_l = layer(6, "ear-left", [group([path([[20, 57], [25, 27], [44, 49]]), fill(WHITE)])], (30, 54), (30, 54),
              r=anim([(0, 0), (34, 0), (39, -10), (46, 0)]), parent=2)
ear_r = layer(7, "ear-right", [group([path([[58, 49], [74, 29], [80, 57]]), fill(WHITE)])], (70, 53), (70, 53),
              r=anim([(0, 0), (36, 0), (41, 10), (48, 0), (L0 + 90, 0), (L0 + 94, 12), (L0 + 100, -2), (L0 + 105, 0)]), parent=2)

# 꼬리: 뿌리(82,83)를 축으로 살랑
tail_path = path([[82, 83], [97, 51], [82, 37]], ins=[[0, 0], [3, 14], [6, -2]], outs=[[12, -4], [-2, -10], [0, 0]], closed=False)
tail = layer(8, "tail", [group([tail_path, stroke(WHITE, 10)])], (82, 83), (82, 83),
             r=anim([(0, 0), (28, 0), (40, -14), (52, 0), (L0 + 120, 0), (L0 + 140, -12), (L0 + 160, 6), (L0 + 180, -6), (L0 + 200, 0)]),
             parent=2)

# 노란 원: 톡 튀어나온다
circle = layer(9, "circle", [group([{"ty": "el", "p": static([60, 60]), "s": static([120, 120])}, fill(YELLOW)])], (60, 60), (60, 60),
               s=anim([(0, [0, 0, 100]), (14, [108, 108, 100]), (22, [97, 97, 100]), (28, [100, 100, 100])], OUTE))

data = {
    "v": "5.7.4", "fr": FR, "ip": 0, "op": OP, "w": 120, "h": 120, "nm": "meeting-meo logo", "ddd": 0, "assets": [],
    # 레이어 순서: 앞에 오는 것이 위에 그려진다
    "layers": [eyes, whiskers, face, ear_l, ear_r, tail, body, circle],
    "markers": [{"tm": a, "cm": name, "dr": b - a} for name, (a, b) in SEG.items()],
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
print("저장:", os.path.relpath(OUT))
