#!/usr/bin/env python3
# [Define404]
"""데모 페이지 만들기: web/index.html 에 demo/demo.js 를 끼워 demo/dist 에 정적 사이트로 내보낸다.

사용: python3 tools/build_demo.py  ->  demo/dist (Cloudflare Pages 등에 그대로 올린다)
"""
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
OUT = os.path.join(ROOT, "demo", "dist")

shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(os.path.join(OUT, "vendor"))
html = open(os.path.join(WEB, "index.html"), encoding="utf-8").read()
anchor = '<script src="/vendor/lottie_light.min.js"></script>'
assert anchor in html, "web/index.html 구조가 바뀌었습니다"
meta = ('<meta name="description" content="화상 미팅 중 상대 말의 요지와 내가 할 다음 한마디, 모르는 용어를 폰에 띄워 주는 오픈소스. 설치 없이 예시 미팅을 재생해 볼 수 있어요.">\n'
        '<meta property="og:title" content="미팅냥 데모">\n'
        '<meta property="og:description" content="미팅 중 요지와 다음 한마디를 폰에 띄워 드려요. 예시 미팅을 재생해 보세요.">\n'
        '<meta property="og:image" content="/og.png">\n')
html = html.replace("<title>미팅냥</title>", "<title>미팅냥 데모</title>\n" + meta)
html = html.replace(anchor, anchor + '\n<script src="/demo.js"></script>')
open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(html)
for f in ("logo.svg", "logo.json"):
    shutil.copy(os.path.join(WEB, f), OUT)
shutil.copy(os.path.join(WEB, "vendor", "lottie_light.min.js"), os.path.join(OUT, "vendor"))
shutil.copy(os.path.join(ROOT, "demo", "demo.js"), OUT)
og = os.path.join(ROOT, "docs", "og.png")
if os.path.exists(og):
    shutil.copy(og, OUT)
print("저장:", os.path.relpath(OUT, ROOT))
