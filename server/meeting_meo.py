# [Define404]
"""미팅냥: 화상 미팅 중 상대 말을 맥에서 받아쓰고, 요지·다음 한마디·용어 풀이·결정·할 일을 폰 화면에 띄운다.

실행은 저장소 루트의 ./meeting-meo 스크립트로 한다.
받아쓰기는 맥 안에서만 돌고, 요약은 사용자가 고른 AI(Claude·ChatGPT·Gemini)에 본인 키로 보낸다.
"""
import argparse
import array
import base64
import html as htmllib
import io
import json
import math
import os
import queue
import re
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
TAP = ROOT / "mac" / "tap" / "meet-tap"
PDF = ROOT / "mac" / "pdf" / "meet-pdf"
DATA = Path(os.environ.get("MEETING_MEO_DATA") or Path.home() / "Library" / "Application Support" / "meeting-meo").expanduser()
MODEL_FILE = "ggml-large-v3-turbo-q5_0.bin"
MODEL_URL = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{MODEL_FILE}"
ALT_MODEL = Path.home() / "Library/Application Support/alt/models/whisper-cpp" / MODEL_FILE
WHISPER_PORT = int(os.environ.get("MEETING_MEO_WHISPER_PORT") or 8178)

# AI 회사별 기본 모델. live = 미팅 중 실시간 요약(빠르고 짧게), deep = 미팅 전 준비·미팅 후 정리(한 번만 돈다)
PROVIDERS = {
    "claude": {"name": "Claude", "live": "claude-sonnet-5-5", "deep": "claude-opus-5-5", "keys": "https://platform.claude.com/"},
    "openai": {"name": "ChatGPT", "live": "gpt-6.1-sol", "deep": "gpt-6.1-sol", "keys": "https://platform.openai.com/api-keys"},
    "gemini": {"name": "Gemini", "live": "gemini-3.8-flash", "deep": "gemini-3.8-flash", "keys": "https://aistudio.google.com/apikey"},
}

LIVE_GAP = 15.0  # 실시간 요약 최소 간격(초). 상대가 질문하면 기다리지 않는다
RATE = 16000
FRAME = 480
BASE_HINT = "B2B, B2C, SaaS, ARR, MRR, CAC, LTV, PMF, KPI, OKR, API, MCP, RAG, LLM, SDK, UI, UX, MVP, ROI, GMV, NDA, MOU, SLA, PoC"
JUNK = ("시청해 주셔서 감사합니다", "시청해주셔서 감사합니다", "구독과 좋아요", "MBC 뉴스", "자막 제공", "다음 영상에서 만나요")
QUESTION_ENDS = ("까요", "나요", "가요", "세요", "습니까", "니까", "는지", "은지", "을지", "신가요", "있으세요", "어떠세요",
                 "궁금합니다", "궁금해요", "듣고 싶습니다", "말씀해 주세요", "어떻게 보세요", "가능할까요")

MODES = {
    "interview": {
        "name": "면접",
        "reply": "상대가 '나'에게 질문했을 때만, 내가 소리 내어 말할 답을 한 문장으로. 첫 마디로 결론을 말한다.",
        "hints": "상대가 '나'에게 경험·생각·이유를 직접 물을 때만, 그 질문에 바로 답이 되는 내 경험을 배경 자료에서 최대 2개.",
        "focus": "질문 의도 파악, 내 경험과의 연결.",
    },
    "sales": {
        "name": "영업·제안",
        "reply": "상대가 질문·반론·망설임·조건 제시를 하면, 그에 대응할 내 다음 한마디를 한 문장으로. 반론이면 인정하고 근거로 답한다. 다음 단계(시연, 견적, 다음 미팅)를 제안할 때가 되면 그 문장을 준다.",
        "hints": "상대 말에 바로 쓸 수 있는 우리 제품·회사의 강점이나 사례를 배경 자료에서 최대 2개. 연결이 약하면 비운다.",
        "focus": "상대의 진짜 걱정(가격, 위험, 일정, 결정권자) 파악, 가격·조건 숫자 기록, 지켜야 할 선 위반 경고.",
    },
    "meeting": {
        "name": "내부·파트너 회의",
        "reply": "논의가 모호하게 넘어가거나 담당자·기한이 빠졌을 때, 내가 던질 확인 질문 한 문장. 정리가 필요할 때는 결정을 확인하는 문장. 필요 없으면 빈 문자열.",
        "hints": "빈 배열로 둔다.",
        "focus": "결정 사항, 할 일(누가·무엇을·언제까지), 미결 쟁점.",
    },
}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


# ---------- 저장소 ----------

def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path, data, private=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    if private:
        os.chmod(tmp, 0o600)
    tmp.replace(path)


def config():
    return read_json(DATA / "config.json", {})


ENV_KEYS = {"claude": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}


def provider():
    p = config().get("provider") or os.environ.get("MEETING_MEO_PROVIDER") or "claude"
    return p if p in PROVIDERS else "claude"


def key_for(p):
    cfg = config()
    keys = cfg.get("keys", {})
    if p == "claude" and cfg.get("api_key"):  # 예전 설정 파일 호환
        keys.setdefault("claude", cfg["api_key"])
    return os.environ.get(ENV_KEYS[p]) or keys.get(p, "")


def model_for(p, kind):
    return os.environ.get(f"MEETING_MEO_{kind.upper()}_MODEL") or PROVIDERS[p][kind]


# ---------- AI 호출 (Claude · ChatGPT · Gemini 공용) ----------

class LLMError(RuntimeError):
    def __init__(self, msg, retry=False):
        super().__init__(msg)
        self.retry = retry


def strip_additional(schema):
    """Gemini는 additionalProperties를 받지 않는 경우가 있어 뺀다."""
    if isinstance(schema, dict):
        return {k: strip_additional(v) for k, v in schema.items() if k != "additionalProperties"}
    if isinstance(schema, list):
        return [strip_additional(x) for x in schema]
    return schema


def http_json(url, body, headers):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        if e.code in (401, 403) or "API_KEY_INVALID" in detail or "invalid_api_key" in detail:
            raise LLMError("AI 키가 맞지 않습니다. 설정에서 다시 넣어 주십시오.")
        if e.code == 429:
            raise LLMError("AI 요청 한도에 걸렸습니다. 잠시 뒤 다시 시도합니다.", retry=True)
        raise LLMError(f"AI 오류 {e.code}: {detail}", retry=e.code >= 500)
    except urllib.error.URLError as e:
        raise LLMError(f"네트워크 오류: {e.reason}", retry=True)


def llm_json(kind, system, parts, schema):
    """parts = [{"text": ...} | {"pdf": base64}]. 스키마에 맞는 JSON을 돌려준다."""
    p = provider()
    key = key_for(p)
    if not key:
        raise LLMError(f"{PROVIDERS[p]['name']} 키가 없습니다. 준비 화면 맨 위 'AI 연결'에서 넣어 주십시오.")
    coach = kind == "coach"   # 연습 채점: 빠른 모델로, 조금 더 길게
    model = model_for(p, "live" if coach else kind)
    live = kind == "live"

    if p == "claude":
        content = []
        for x in parts:
            if "pdf" in x:
                content.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": x["pdf"]}})
            else:
                content.append({"type": "text", "text": x["text"]})
        kw = dict(model=model, max_tokens=1000 if live else 3000 if coach else 16000,
                  system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                  messages=[{"role": "user", "content": content}],
                  output_config={"effort": "low" if live or coach else "medium", "format": {"type": "json_schema", "schema": schema}})
        if live:
            kw["thinking"] = {"type": "between_tools"} if "sonnet" in model else {"type": "disabled"}
        try:
            resp = anthropic.Anthropic(api_key=key).messages.create(**kw)
        except anthropic.AuthenticationError:
            raise LLMError("Claude 키가 맞지 않습니다. 설정에서 다시 넣어 주십시오.")
        except anthropic.RateLimitError:
            raise LLMError("Claude 요청 한도에 걸렸습니다.", retry=True)
        except anthropic.APIStatusError as e:
            raise LLMError(f"Claude 오류 {e.status_code}: {e.message}", retry=e.status_code >= 500)
        except anthropic.APIConnectionError:
            raise LLMError("네트워크 오류", retry=True)
        if resp.stop_reason == "refusal":
            raise LLMError("AI가 이 요청에 답하지 않았습니다.")
        return json.loads(next((b.text for b in resp.content if b.type == "text"), "{}"))

    if p == "openai":
        content = []
        for x in parts:
            if "pdf" in x:
                content.append({"type": "input_file", "filename": "me.pdf", "file_data": "data:application/pdf;base64," + x["pdf"]})
            else:
                content.append({"type": "input_text", "text": x["text"]})
        body = {"model": model, "instructions": system, "input": [{"role": "user", "content": content}],
                "reasoning": {"effort": "low" if live or coach else "medium"},
                "text": {"format": {"type": "json_schema", "name": "result", "schema": schema, "strict": True}}}
        d = http_json("https://api.openai.com/v1/responses", body, {"Authorization": f"Bearer {key}"})
        for item in d.get("output", []):
            for c in item.get("content", []) or []:
                if c.get("type") == "output_text":
                    return json.loads(c["text"])
                if c.get("type") == "refusal":
                    raise LLMError("AI가 이 요청에 답하지 않았습니다.")
        raise LLMError("ChatGPT 응답을 읽지 못했습니다.")

    # gemini
    gparts = []
    for x in parts:
        if "pdf" in x:
            gparts.append({"inline_data": {"mime_type": "application/pdf", "data": x["pdf"]}})
        else:
            gparts.append({"text": x["text"]})
    body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": gparts}],
            "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": strip_additional(schema)}}
    d = http_json(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", body, {"x-goog-api-key": key})
    try:
        text = "".join(pt.get("text", "") for pt in d["candidates"][0]["content"]["parts"] if not pt.get("thought"))
        return json.loads(text)
    except (KeyError, IndexError, ValueError):
        raise LLMError("Gemini 응답을 읽지 못했습니다.")


# ---------- 화면으로 보내기 ----------

class Hub:
    def __init__(self):
        self.lock = threading.Lock()
        self.clients = []
        self.reset()

    def reset(self):
        self.meeting = None
        self.lines = []
        self.card = None
        self.terms = []
        self.decisions = []
        self.actions = []
        self.numbers = []
        self.covered = set()
        self.alerts = []
        self.flow = []
        self.pins = []
        self.speakers = {}   # id -> {"name", "segs", "secs"}
        self.next_line = 0
        self.status = "idle"

    def snapshot(self):
        m = self.meeting
        return {
            "type": "state",
            "meeting": {k: m.get(k) for k in ("id", "mode", "title", "goals", "started", "minutes", "prep", "cards")} if m else None,
            "speakers": self.speakers,
            "lines": self.lines[-60:], "card": self.card, "terms": self.terms, "flow": self.flow,
            "decisions": self.decisions, "actions": self.actions, "numbers": self.numbers,
            "covered": sorted(self.covered), "alerts": self.alerts[-5:], "status": self.status, "pins": self.pins,
        }

    def subscribe(self):
        q = queue.Queue()
        with self.lock:
            self.clients.append(q)
            q.put(self.snapshot())
        return q

    def unsubscribe(self, q):
        with self.lock:
            if q in self.clients:
                self.clients.remove(q)

    def send(self, msg):
        with self.lock:
            for q in self.clients:
                q.put(msg)


hub = Hub()


# ---------- 받아쓰기 ----------

def model_path():
    own = DATA / "models" / MODEL_FILE
    if own.exists():
        return own
    if ALT_MODEL.exists():
        return ALT_MODEL
    return own


def ensure_model():
    path = model_path()
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    log(f"받아쓰기 모델을 처음 한 번 받습니다 (약 570MB): {MODEL_URL}")
    tmp = path.with_suffix(".part")
    with urllib.request.urlopen(MODEL_URL) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        done, last = 0, 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            if total and done - last > total // 20:
                last = done
                log(f"  {done * 100 // total}%")
    tmp.replace(path)
    return path


def whisper_up():
    try:
        socket.create_connection(("127.0.0.1", WHISPER_PORT), timeout=1).close()
        return True
    except OSError:
        return False


class Whisper:
    def __init__(self):
        self.proc = None
        self.lang = None

    def start(self, lang):
        if self.proc and self.lang == lang and whisper_up():
            return
        self.stop()
        exe = shutil.which("whisper-server")
        if not exe:
            raise RuntimeError("whisper-server가 없습니다. 터미널에서 brew install whisper-cpp 를 실행하십시오.")
        self.proc = subprocess.Popen(
            [exe, "-m", str(ensure_model()), "--port", str(WHISPER_PORT), "-l", lang, "-t", "6"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.lang = lang
        for _ in range(80):
            if whisper_up():
                return
            time.sleep(0.5)
        raise RuntimeError("받아쓰기 서버가 뜨지 않았습니다")

    def stop(self):
        if self.proc:
            self.proc.terminate()
            self.proc = None

    def transcribe(self, pcm, hint, lang=None):
        out = io.BytesIO()
        w = wave.open(out, "wb")
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
        w.close()
        boundary = uuid.uuid4().hex
        parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
                 for k, v in (("response_format", "json"), ("temperature", "0"), ("prompt", hint), ("language", lang or self.lang or "auto"))]
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\n'
                     f"Content-Type: audio/wav\r\n\r\n".encode() + out.getvalue() + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        # 이미 떠 있던 받아쓰기 서버가 다른 언어로 켜져 있어도 요청마다 언어를 고정한다
        req = urllib.request.Request(
            f"http://127.0.0.1:{WHISPER_PORT}/inference", data=b"".join(parts),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read()).get("text", "").strip()


whisper = Whisper()


class Segmenter:
    """에너지로 말 구간을 자른다."""

    def __init__(self, name, callback):
        self.name = name
        self.cb = callback
        self.buf = bytearray()
        self.pre = []
        self.noise = 300.0
        self.speaking = False
        self.loud = 0
        self.quiet = 0
        self.start_ts = 0.0
        self.pending = bytearray()

    def feed(self, data):
        self.pending += data
        step = FRAME * 2
        while len(self.pending) >= step:
            frame = bytes(self.pending[:step])
            del self.pending[:step]
            self._frame(frame)

    def _frame(self, frame):
        a = array.array("h", frame)
        rms = math.sqrt(sum(x * x for x in a) / len(a)) if a else 0
        thr = max(500.0, self.noise * 3)
        now = time.time()
        if not self.speaking:
            self.noise = 0.95 * self.noise + 0.05 * min(rms, 3000)
            self.pre.append(frame)
            if len(self.pre) > 10:
                self.pre.pop(0)
            self.loud = self.loud + 1 if rms > thr else 0
            if self.loud >= 3:
                self.speaking = True
                self.quiet = 0
                self.start_ts = now - 0.3
                self.buf = bytearray(b"".join(self.pre))
                self.pre = []
                if self.name == "them":
                    set_status("them")
            return
        self.buf += frame
        self.quiet = self.quiet + 1 if rms < thr else 0
        dur = len(self.buf) / (RATE * 2)
        if self.quiet >= 17 or dur >= 10:
            self.speaking = False
            self.loud = 0
            if self.name == "them":
                set_status("idle")
            if dur >= 0.8:
                self.cb(bytes(self.buf), self.start_ts, now)
            self.buf = bytearray()


def set_status(s):
    hub.status = s
    hub.send({"type": "status", "state": s})


def is_question(text):
    t = text.strip().rstrip(".!… ")
    return "?" in text or t.endswith(QUESTION_ENDS)


# ---------- 실시간 요약 ----------

LIVE_SYSTEM = """너는 화상 미팅 중인 사용자 옆에서 폰 화면 한 장으로 돕는 보조자다.
사용자는 아래 배경 자료의 '나'다. 상대 말을 받아쓴 글을 보고, 사용자가 3초 안에 읽을 수 있게 정리한다.
미팅 종류: {mode_name}. 이번 미팅에서 특히 볼 것: {focus}

필드 규칙:
- kind: 상대의 가장 최근 말의 성격. 질문, 요청, 반론, 제안, 결정, 설명 중 하나.
- 상대는 여러 명일 수 있다. 대화의 [ ] 안이 말한 사람이다. 사람마다 입장이 다를 수 있으니 섞지 않는다. 상대 말이 한국어가 아니면 괄호 안 한국어 번역을 참고한다.
- gist: 상대가 가장 마지막에 한 말 하나의 요지를 한국어 한 줄로. 앞선 말과 합치지 않는다. '상대가 ~라고 함' 같은 설명 투 없이 요지만.
- intent: 상대가 그 말로 무엇을 확인하거나 얻으려는지 한 줄. 모르면 빈 문자열.
- reply: {reply} 한 문장, 50자 이내, 말하듯 쓰는 존댓말.
  배경 자료에 적힌 사실·숫자만 쓴다. 느낌·어려움·이유·동기·계획처럼 내 속마음에 해당하는 내용은 배경 자료에 그 말이 그대로 없으면 반드시 ○○로 비운다.
  좋은 예: '가장 어려웠던 건 ○○였고, 작업 규정 13종으로 기준을 맞췄습니다.' 나쁜 예: '가장 어려웠던 건 개발자들의 불안이었습니다.'(자료에 없는 속마음을 지어냄)
- hints: {hints} exp는 낱말 묶음, link는 상대 말의 어느 대목과 이어지는지 12자 안팎. 억지로 채우지 않는다.
- terms: 처음 나온 용어 중 IT·개발·프로덕트·회계·재무·법무·비즈니스 용어와 영어 약어만, 최대 4개. 일상어·사람 이름은 넣지 않는다. '이미 풀이한 용어'는 넣지 않는다.
  term은 바로잡은 표기, heard는 받아쓴 글에 실제로 나온 표기 그대로. short는 괄호 주석 10자 이내, meaning은 25자 안팎 한 줄.
  받아쓰기는 영어 약어를 한글 소리로 잘못 적는 일이 잦다(예: 어레인기드→ARR, 레그로→RAG). 확신이 없으면 넣지 않는다.
- flow: 지금까지 대화 흐름 최대 4줄, 짧은 구절.
- covered: '이번 미팅 목표' 중 대화에서 그 주제를 누군가 직접 말로 꺼낸 항목 번호만. 비슷한 낱말이 스쳤거나 배경 자료에만 있는 것은 넣지 않는다. 확실하지 않으면 넣지 않는다. 이미 다룬 목표 번호는 다시 넣지 않아도 된다.
- decisions: 이번 말에서 새로 확정된 결정. 없으면 빈 배열.
- actions: 새로 생긴 할 일. who(모르면 빈 문자열), what, when(모르면 빈 문자열).
- numbers: 새로 나온 금액·날짜·수량·비율. what(무엇의 숫자), value.
- alert: '지켜야 할 선'을 넘는 말이 나왔거나 넘을 위험이 보이면 한 줄 경고. 없으면 빈 문자열.
- 받아쓰기 오류로 보이는 낱말은 gist·intent·flow에서 문맥으로 바로잡는다.
- 한국어로 쓴다. 긴 줄표(엠대시) 문장부호를 쓰지 않는다.

배경 자료:
{brief}

이번 미팅 목표:
{goals}

지켜야 할 선:
{guardrails}
"""

LIVE_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["질문", "요청", "반론", "제안", "결정", "설명"]},
        "gist": {"type": "string"},
        "intent": {"type": "string"},
        "reply": {"type": "string"},
        "hints": {"type": "array", "items": {"type": "object", "properties": {"exp": {"type": "string"}, "link": {"type": "string"}},
                                             "required": ["exp", "link"], "additionalProperties": False}},
        "terms": {"type": "array", "items": {"type": "object", "properties": {
            "term": {"type": "string"}, "heard": {"type": "string"}, "short": {"type": "string"}, "meaning": {"type": "string"}},
            "required": ["term", "heard", "short", "meaning"], "additionalProperties": False}},
        "flow": {"type": "array", "items": {"type": "string"}},
        "covered": {"type": "array", "items": {"type": "integer"}},
        "decisions": {"type": "array", "items": {"type": "string"}},
        "actions": {"type": "array", "items": {"type": "object", "properties": {
            "who": {"type": "string"}, "what": {"type": "string"}, "when": {"type": "string"}},
            "required": ["who", "what", "when"], "additionalProperties": False}},
        "numbers": {"type": "array", "items": {"type": "object", "properties": {
            "what": {"type": "string"}, "value": {"type": "string"}},
            "required": ["what", "value"], "additionalProperties": False}},
        "alert": {"type": "string"},
    },
    "required": ["kind", "gist", "intent", "reply", "hints", "terms", "flow", "covered", "decisions", "actions", "numbers", "alert"],
    "additionalProperties": False,
}


LIVE_INTERVIEW_RULES = """
면접 추가 규칙:
- qtype: 상대의 가장 최근 말이 나에게 하는 질문이면 질문 종류를 정해진 목록 중 하나로. 질문이 아니면 빈 문자열.
- card: 아래 '답변 카드' 중 지금 질문과 같은 질문 의도인 카드 번호. 맞는 카드가 없으면 -1. 비슷한 낱말만 겹치면 -1.
- 맞는 카드가 있으면 reply는 그 카드 답의 첫 문장을 지금 질문 말투에 맞게 다듬는다. 카드에 ○○가 있으면 그대로 둔다.
- alert: 상대 말뿐 아니라 '나'가 방금 한 말이 지켜야 할 선이나 말하지 않을 것을 넘었으면 '방금 내 말: ' 로 시작하는 한 줄 경고.

답변 카드:
{cards}
"""


def live_schema(mode):
    if mode != "interview":
        return LIVE_SCHEMA
    sc = json.loads(json.dumps(LIVE_SCHEMA))
    sc["properties"]["qtype"] = {"type": "string", "enum": [""] + QTYPES}
    sc["properties"]["card"] = {"type": "integer"}
    sc["required"] = sc["required"] + ["qtype", "card"]
    return sc


class Analyst:
    def __init__(self):
        self.flag = threading.Event()
        self.urgent = False
        self.last = 0.0
        self.active = False
        threading.Thread(target=self._loop, daemon=True).start()

    def poke(self, urgent=False):
        self.urgent = self.urgent or urgent
        self.flag.set()

    def _loop(self):
        while True:
            self.flag.wait()
            self.flag.clear()
            # 질문이 아니면 LIVE_GAP 초를 다 채운 뒤 돈다. 중간에 새 말이 들어와도 기다림을 끊지 않는다
            while not self.urgent:
                gap = LIVE_GAP - (time.time() - self.last)
                if gap <= 0:
                    break
                self.flag.wait(gap)
                self.flag.clear()
            self.urgent = False
            self.last = time.time()
            if not hub.meeting:
                continue
            if not key_for(provider()):
                continue
            if not any(l["who"] == "them" for l in hub.lines[-30:]):
                continue  # 상대가 아직 말하지 않았으면 요약할 것이 없다
            set_status("thinking")
            try:
                self._run()
            except LLMError as e:
                log("요약 오류:", e)
                if e.retry:
                    time.sleep(3)
                    self.flag.set()
                else:
                    hub.send({"type": "error", "text": str(e)})
            except (ValueError, KeyError) as e:
                log("요약 응답 형식 오류:", e)
            finally:
                set_status("idle")

    def _run(self):
        m = hub.meeting
        mode = MODES[m["mode"]]
        system = LIVE_SYSTEM.format(
            mode_name=mode["name"], focus=mode["focus"], reply=mode["reply"], hints=mode["hints"],
            brief=m.get("brief", ""), guardrails=m.get("guardrails") or "없음",
            goals="\n".join(f"{i}. {g}" for i, g in enumerate(m.get("goals", []))) or "없음")
        cards = m.get("cards") or []
        if m["mode"] == "interview":
            system += LIVE_INTERVIEW_RULES.format(cards="\n".join(
                f"{i}. [{c['qtype']}] {c['question']}" + (" (곤란한 질문)" if c.get("risk") else "") for i, c in enumerate(cards)) or "없음")
        lines = hub.lines[-30:]
        convo = "\n".join(f"[{who_label(l)}] {l['text']}" + (f" (한국어: {l['ko']})" if l.get("ko") else "") for l in lines)
        them = [l["text"] for l in lines if l["who"] == "them"]
        them_lines = [l for l in lines if l["who"] == "them"]
        if not them:
            return
        latest = them[-1]
        if len(them) >= 2 and len(latest) < 15:
            latest = them[-2] + " " + latest
        known = ", ".join(t["term"] for t in hub.terms) or "없음"
        t0 = time.time()
        done = json.dumps({"결정": hub.decisions, "할 일": [x["what"] for x in hub.actions], "숫자": [f"{x['what']} {x['value']}" for x in hub.numbers]}, ensure_ascii=False)
        d = llm_json("live", system, [{"text": f"이미 풀이한 용어: {known}\n이미 기록한 것(같은 뜻이면 다시 넣지 않는다): {done}\n\n대화:\n{convo}\n\n지금 gist·reply로 다룰 상대의 가장 최근 말:\n{latest}"}], live_schema(m["mode"]))
        known_set = {t["term"].lower() for t in hub.terms}
        new_terms = [t for t in d["terms"][:4] if t["term"].lower() not in known_set]
        hub.terms = (new_terms + hub.terms)[:40]
        for x in d["decisions"]:
            if x and x not in hub.decisions:
                hub.decisions.append(x)
        for a in d["actions"]:
            if a["what"] and all(a["what"] != b["what"] for b in hub.actions):
                hub.actions.append(a)
        for n in d["numbers"]:
            if n["value"] and all(n["value"] != b["value"] or n["what"] != b["what"] for b in hub.numbers):
                hub.numbers.append(n)
        hub.covered |= {i for i in d["covered"] if 0 <= i < len(m.get("goals", []))}
        if m["mode"] == "interview":
            d["reply"] = mask_private(d["reply"], secret_src(m))
            d["alert"] = mask_private(d["alert"], secret_src(m))
        if d["alert"]:
            hub.alerts.append({"t": time.strftime("%H:%M"), "text": d["alert"]})
        if d["flow"]:
            hub.flow = d["flow"]
        card = {k: d[k] for k in ("kind", "gist", "intent", "reply", "hints", "alert")}
        card["speaker"] = who_label(them_lines[-1]) if them_lines else ""
        if m["mode"] == "interview":
            card["qtype"] = d.get("qtype", "")
            n = d.get("card", -1)
            card["card"] = n if isinstance(n, int) and 0 <= n < len(cards) else -1
        card["ms"] = int((time.time() - t0) * 1000)
        hub.card = card
        snap = hub.snapshot()
        hub.send({"type": "card", "card": card, **{k: snap[k] for k in ("terms", "flow", "decisions", "actions", "numbers", "covered", "alerts")}})
        log(f"요약 {card['ms']}ms ({provider()})")


analyst = Analyst()


GUARD_SYSTEM = """너는 면접 중인 사용자의 말을 지켜본다. '나'가 방금 한 말이 아래 '지켜야 할 선'이나 '말하지 않을 것'을 넘었는지만 본다.
넘었으면 alert에 '방금 내 말: '으로 시작하는 한 줄 경고, 아니면 빈 문자열. 확실하지 않으면 빈 문자열.
경고에 하한 금액 같은 숫자를 다시 적지 않는다. 한국어로 쓰고 긴 줄표 문장부호를 쓰지 않는다.

지켜야 할 선:
{guardrails}"""
GUARD_SCHEMA = {"type": "object", "properties": {"alert": {"type": "string"}}, "required": ["alert"], "additionalProperties": False}


class Guard:
    """내 말이 선을 넘었는지 가볍게 본다. 추천 답 카드와 '정리하는 중' 표시는 건드리지 않는다."""

    def __init__(self):
        self.jobs = queue.Queue()
        self.last = 0.0
        threading.Thread(target=self._loop, daemon=True).start()

    def check(self, line):
        m = hub.meeting
        if not m:
            return
        # 지켜야 할 선에 적은 숫자(예: 하한 금액)를 내가 입 밖에 냈으면 AI를 부르지 않고 바로 알린다
        for n in private_numbers(secret_src(m)):
            if re.search(rf"(?<![\d,]){re.escape(n)}(?![\d,])", line["text"].replace(" ", "")):
                self._alert("방금 내 말: 지켜야 할 선에 적은 숫자를 말했어요")
                return
        if len(line["text"]) >= 15:
            self.jobs.put(line)

    def _alert(self, text):
        hub.alerts.append({"t": time.strftime("%H:%M"), "text": text})
        hub.send({"type": "alerts", "alerts": hub.alerts[-5:]})

    def _loop(self):
        while True:
            line = self.jobs.get()
            gap = 6.0 - (time.time() - self.last)
            if gap > 0:
                time.sleep(gap)
            batch = [line]
            while not self.jobs.empty():   # 그 사이 쌓인 내 말을 한 번에 본다
                batch.append(self.jobs.get())
            self.last = time.time()
            m = hub.meeting
            if not m or not key_for(provider()):
                continue
            try:
                d = llm_json("live", GUARD_SYSTEM.format(guardrails=m.get("guardrails") or "없음"),
                             [{"text": "방금 내가 한 말:\n" + "\n".join(l["text"] for l in batch)}], GUARD_SCHEMA)
            except (LLMError, ValueError, KeyError) as ex:
                log("내 말 점검 오류:", ex)
                continue
            if hub.meeting is m and d.get("alert"):
                self._alert(mask_private(d["alert"], secret_src(m)))


guard = Guard()


# ---------- 화자 구분 (상대 쪽 목소리를 사람별로 묶는다) ----------

SPEAKER_FILE = "speaker.onnx"
SPEAKER_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
               "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx")
SAME_SPEAKER = 0.62   # 사람 목소리 묶음 기준 (코사인 유사도)


class Diarizer:
    def __init__(self):
        self.ex = None
        self.centroids = {}   # id -> [합계 벡터, 개수]
        self.last = None

    def ready(self):
        if self.ex:
            return True
        try:
            import numpy  # noqa: F401
            import sherpa_onnx
        except ImportError:
            return False
        path = DATA / "models" / SPEAKER_FILE
        if not path.exists():
            try:
                log("화자 구분 모델을 처음 한 번 받습니다 (약 28MB)")
                path.parent.mkdir(parents=True, exist_ok=True)
                urllib.request.urlretrieve(SPEAKER_URL, path.with_suffix(".part"))
                path.with_suffix(".part").replace(path)
            except Exception as ex:
                log("화자 구분 모델을 받지 못했습니다:", ex)
                return False
        self.ex = sherpa_onnx.SpeakerEmbeddingExtractor(sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(path), num_threads=2))
        return True

    def reset(self):
        self.centroids = {}
        self.last = None

    def assign(self, pcm):
        """말 구간 하나를 받아 화자 번호를 돌려준다. 1초보다 짧으면 앞 사람으로 본다."""
        import numpy as np
        secs = len(pcm) / (RATE * 2)
        if not self.ready():
            return 1
        if secs < 1.0 and self.last is not None:
            return self.last
        st = self.ex.create_stream()
        st.accept_waveform(RATE, np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768)
        st.input_finished()
        e = np.array(self.ex.compute(st))
        e /= (np.linalg.norm(e) or 1)
        best, score = None, -1.0
        for sid, (total, n) in self.centroids.items():
            c = total / (np.linalg.norm(total) or 1)
            sc = float(c @ e)
            if sc > score:
                best, score = sid, sc
        if best is None or (score < SAME_SPEAKER and len(self.centroids) < 9):
            best = max(self.centroids, default=0) + 1
            self.centroids[best] = [e.copy(), 1]
        else:
            self.centroids[best][0] += e
            self.centroids[best][1] += 1
        self.last = best
        return best

    def merge(self, src, dst):
        if src in self.centroids and dst in self.centroids:
            self.centroids[dst][0] += self.centroids[src][0]
            self.centroids[dst][1] += self.centroids[src][1]
            del self.centroids[src]
        if self.last == src:
            self.last = dst


diarizer = Diarizer()


def speaker_name(sid):
    sp = hub.speakers.get(str(sid)) or hub.speakers.get(sid)
    return sp["name"] if sp else "상대"


def who_label(line):
    return speaker_name(line["spk"]) if line["who"] == "them" and line.get("spk") else ("상대" if line["who"] == "them" else "나")


# ---------- 다른 언어 번역 ----------

def needs_translation(text):
    letters = [ch for ch in text if ch.isalpha()]
    if len(letters) < 4:
        return False
    hangul = sum(1 for ch in letters if "\uac00" <= ch <= "\ud7a3")
    return hangul / len(letters) < 0.3


TR_SCHEMA = {"type": "object", "properties": {"ko": {"type": "string"}}, "required": ["ko"], "additionalProperties": False}
tr_jobs = queue.Queue()


def translator():
    while True:
        line = tr_jobs.get()
        if not hub.meeting:
            continue
        try:
            d = llm_json("live", "받아쓴 말을 자연스러운 한국어로 옮긴다. 받아쓰기 오류는 문맥으로 바로잡는다. 뜻만 옮기고 덧붙이지 않는다.",
                         [{"text": line["text"]}], TR_SCHEMA)
        except (LLMError, ValueError, KeyError) as ex:
            log("번역 오류:", ex)
            continue
        line["ko"] = d.get("ko", "")
        hub.send({"type": "tr", "id": line["id"], "ko": line["ko"]})


threading.Thread(target=translator, daemon=True).start()


# ---------- 소리 받기 ----------

class CallWatch:
    """화상 통화가 실제로 열려 있는지 2초마다 본다: 크롬의 구글 미트 회의 탭, 또는 줌·팀즈·웹엑스 앱."""

    TABS = 'if application "Google Chrome" is running then tell application "Google Chrome" to get URL of tabs of windows'
    MEET = re.compile(r"meet\.google\.com/(?:[\w-]+/)*[a-z]{3,4}-[a-z]{4}-[a-z]{3,4}")
    APPS = ("CptHost", "MSTeams", "Microsoft Teams", "Webex")  # CptHost = 줌 회의 중에만 뜨는 프로세스

    def __init__(self):
        self.in_call = False
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            try:
                tabs = subprocess.run(["osascript", "-e", self.TABS], capture_output=True, text=True, timeout=5).stdout
                apps = subprocess.run(["pgrep", "-lx", "|".join(self.APPS)], capture_output=True, text=True, timeout=5).stdout
                self.in_call = bool(self.MEET.search(tabs)) or any(a in apps for a in self.APPS)
            except (subprocess.TimeoutExpired, OSError):
                pass
            time.sleep(2)


class Capture:
    def __init__(self):
        self.proc = None
        self.jobs = queue.Queue()
        self.them_spans = []
        self.hint = BASE_HINT
        self.hint_words = set()
        self.them = Segmenter("them", lambda p, s, e: self._segment("them", p, s, e))
        self.me = Segmenter("me", lambda p, s, e: self._segment("me", p, s, e))
        threading.Thread(target=self._worker, daemon=True).start()

    def start(self, hint):
        self.stop()
        self.hint = f"{hint}, {BASE_HINT}" if hint else BASE_HINT
        self.hint_words = {w.strip().lower() for w in self.hint.split(",") if w.strip()}
        feed = os.environ.get("MEETING_MEO_FEED")  # 시험용: 이 음성 파일을 상대 목소리로 흘려 넣는다
        if feed:
            threading.Thread(target=self._feed_file, args=(feed, os.environ.get("MEETING_MEO_FEED_ME")), daemon=True).start()
            return
        if not TAP.exists():
            raise RuntimeError("소리 받기 프로그램이 없습니다. ./install.sh 를 먼저 실행하십시오.")
        self.live = os.environ.get("MEETING_MEO_WAIT_CALL") == "0"
        self.loud_s = 0.0
        if not self.live:
            set_status("waiting")
        self.proc = subprocess.Popen([str(TAP)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()
        threading.Thread(target=lambda p=self.proc: [log("소리 받기:", l.decode().strip()) for l in p.stderr], daemon=True).start()

    def stop(self):
        if self.proc:
            self.proc.terminate()
            self.proc = None

    def _feed_file(self, path, me_path=None):
        """시험용: 음성 파일을 상대 목소리로, me_path가 있으면 그 파일을 내 마이크로 흘려 넣는다."""
        def load(src):
            tmp = DATA / f"feed-{uuid.uuid4().hex[:6]}.wav"
            subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", src, str(tmp)], check=True)
            with wave.open(str(tmp)) as w:
                data = w.readframes(w.getnframes())
            tmp.unlink()
            return data
        pcm = load(path)
        mine = load(me_path) if me_path else b""
        step = RATE * 2 // 10
        for i in range(0, max(len(pcm), len(mine)), step):
            if not hub.meeting:
                return
            a, b = pcm[i:i + step], mine[i:i + step]
            n = max(len(a), len(b))
            self.them.feed(a.ljust(n, b"\x00"))
            self.me.feed(b.ljust(n, b"\x00"))
            time.sleep(0.1)
        self.them.feed(b"\x00" * RATE * 2)

    def _read(self, proc):
        out = proc.stdout
        while True:
            head = out.read(5)
            if len(head) < 5:
                if self.proc is proc:
                    hub.send({"type": "error", "text": "소리 받기가 멈췄습니다. 화면 기록·마이크 권한을 확인하십시오."})
                return
            n = struct.unpack("<I", head[1:])[0]
            data = out.read(n)
            if not self._gate(head[0], data):
                continue
            (self.them if head[0] == 0 else self.me).feed(data)

    def _gate(self, src, data):
        """통화가 시작되기 전 소리(개인 통화, 영상 등)는 받아쓰지 않는다."""
        if os.environ.get("MEETING_MEO_WAIT_CALL") == "0":
            return True
        if not call_watch.in_call:
            if self.live:
                self.live = False
                set_status("waiting")
                log("받아쓰기 멈춤: 화상 통화가 닫혔습니다")
            self.loud_s = 0.0
            return False
        if self.live:
            return True
        # 대기실에서는 상대 소리가 오지 않는다. 상대 소리가 0.5초 넘게 들려야 통화가 시작된 것으로 본다
        if src == 0:
            a = array.array("h", data[: len(data) // 2 * 2])
            if a and math.sqrt(sum(x * x for x in a) / len(a)) > 800:
                self.loud_s += len(a) / RATE
        if self.loud_s < 0.5:
            return False
        self.live = True
        set_status("idle")
        log("받아쓰기 시작: 통화 상대 소리 감지")
        return True

    def _segment(self, who, pcm, s, e):
        if who == "them":
            self.them_spans = (self.them_spans + [(s, e)])[-20:]
        else:
            overlap = sum(max(0, min(e, te) - max(s, ts)) for ts, te in self.them_spans)
            if self.them.speaking:
                overlap += max(0, e - max(s, self.them.start_ts))
            if overlap > 0.5 * (e - s):
                return
        self.jobs.put((who, pcm, s))

    def _worker(self):
        while True:
            who, pcm, s = self.jobs.get()
            if not hub.meeting:
                continue
            try:
                text = whisper.transcribe(pcm, self.hint)
            except Exception as ex:  # 받아쓰기 서버가 잠깐 끊겨도 계속 간다
                log("받아쓰기 오류", ex)
                continue
            short = len(pcm) / (RATE * 2) < 2.0
            core = text.strip(" .,!?*-~…").lower()
            # *cough*, [음악], (웃음) 처럼 말이 아닌 소리 표시는 버린다
            if re.fullmatch(r"\s*[\*\[\(（].*[\*\]\)）]\s*[.!]?\s*", text):
                continue
            if not text or any(j in text for j in JUNK) or core in self.hint_words:
                continue
            if short and (len(core) <= 3 or core in ("감사합니다", "네", "고맙습니다", "thanks", "thank you", "you", "bye")):
                continue
            line = {"id": hub.next_line, "who": who, "text": text, "t": time.strftime("%H:%M:%S", time.localtime(s))}
            hub.next_line += 1
            if who == "them":
                try:
                    sid = diarizer.assign(pcm)
                except Exception as ex:
                    log("화자 구분 오류:", ex)
                    sid = 1
                line["spk"] = sid
                sp = hub.speakers.setdefault(str(sid), {"name": f"상대 {sid}", "segs": 0, "secs": 0.0})
                sp["segs"] += 1
                sp["secs"] = round(sp["secs"] + len(pcm) / (RATE * 2), 1)
                hub.send({"type": "speakers", "speakers": hub.speakers})
            hub.lines.append(line)
            hub.send({"type": "line", "line": line})
            m = hub.meeting
            if m:
                with open(DATA / "meetings" / m["id"] / "transcript.jsonl", "a", encoding="utf-8") as f:
                    f.write(json.dumps(line, ensure_ascii=False) + "\n")
            if needs_translation(text):
                tr_jobs.put(line)
            if who == "them":
                analyst.poke(urgent=is_question(text))
            elif m and m["mode"] == "interview" and m.get("guardrails"):
                guard.check(line)  # 내 말은 선을 넘었는지만 본다. 추천 답 카드는 건드리지 않는다


call_watch = CallWatch()
capture = Capture()


# ---------- 미팅 전: 준비 자료 ----------

PREP_SYSTEM = """너는 미팅 준비를 돕는다. 사용자가 준 '내 정보', '상대 정보', '목표'로 미팅 중 참고할 배경 자료를 만든다.
규칙:
- 받은 자료에 있는 사실만 쓴다. 추측은 쓰지 않는다. 숫자·이름·연도는 원문 그대로.
- 일반인이 읽는 문서다. 마크다운 기호(#, *, **, 백틱)를 쓰지 않는다. 각 항목은 평문 한 줄, 60자 이내. 한 항목에 사실 하나만.
- counterpart.who: 상대를 한 줄로(누구, 어떤 회사, 이번 미팅이 무엇인지). counterpart.points: 상대에 대해 알아 둘 사실 최대 10개.
- me.headline: 이번 미팅에서 나를 한 줄로 소개하는 문장. me.points: 미팅 종류에 맞는 내 경험·강점·숫자 최대 10개. 관련 없는 경력은 뺀다.
- talk: 이번 미팅에서 꺼내면 좋을 이야기 최대 6개. 상대가 원하는 것과 내 강점이 만나는 지점.
- watch: 조심하거나 꼭 확인할 것 최대 5개(상대 조건과 내 상황이 어긋나는 곳, 지켜야 할 선 등). 없으면 빈 배열.
- goals는 사용자가 적은 목표·물어볼 것을 한 줄씩 다듬어 그대로 옮긴다. 새로 만들지 않는다. 사용자가 비웠으면 미팅 종류에 맞는 기본 목표 3개를 제안한다.
- pins: 미팅 중 바로 꺼내 읽을 정해 둔 답 최대 8개(희망 조건, 시작일, 소개 한 줄, 물어볼 것 등). 받은 자료에 있는 것만. 없으면 빈 배열.
- terms: 상대 쪽에서 나올 고유명사·업계 용어 최대 10개. '용어: 뜻' 꼴로 뜻은 25자 이내. 없으면 빈 배열.
- stt_hint는 받아쓰기가 틀리기 쉬운 고유명사·제품명·약어를 쉼표로 20개 이내.
- title은 '상대 이름 · 미팅 종류' 형태로 짧게.
- 한국어로 쓴다. 긴 줄표(엠대시) 문장부호를 쓰지 않는다."""

PREP_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "counterpart": {"type": "object", "properties": {"who": {"type": "string"}, "points": {"type": "array", "items": {"type": "string"}}},
                        "required": ["who", "points"], "additionalProperties": False},
        "me": {"type": "object", "properties": {"headline": {"type": "string"}, "points": {"type": "array", "items": {"type": "string"}}},
               "required": ["headline", "points"], "additionalProperties": False},
        "talk": {"type": "array", "items": {"type": "string"}},
        "watch": {"type": "array", "items": {"type": "string"}},
        "goals": {"type": "array", "items": {"type": "string"}},
        "pins": {"type": "array", "items": {"type": "string"}},
        "terms": {"type": "array", "items": {"type": "string"}},
        "stt_hint": {"type": "string"},
    },
    "required": ["title", "counterpart", "me", "talk", "watch", "goals", "pins", "terms", "stt_hint"],
    "additionalProperties": False,
}


def fetch_page(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 meeting-meo"})
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read(3_000_000).decode("utf-8", "replace")
    except Exception as ex:
        return f"(주소를 읽지 못했습니다: {ex})"
    raw = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    text = htmllib.unescape(re.sub(r"<[^>]+>", "\n", raw))
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text[:20000]


def prepare(body):
    profile = read_json(DATA / "profile.json", {})
    mode_key = body.get("mode", "meeting")
    mode = MODES[mode_key]
    content = [{"pdf": profile["pdf_b64"]}] if profile.get("pdf_b64") else []
    pages = "\n\n".join(f"[{u}]\n{fetch_page(u)}" for u in body.get("urls", []) if u.strip())
    texts = [
        f"미팅 종류: {mode['name']}",
        f"내 정보(직접 쓴 글):\n{profile.get('text', '') or '없음'}" + ("\n(첨부 PDF도 내 정보다)" if profile.get("pdf_b64") else ""),
        f"상대 정보(직접 쓴 글):\n{body.get('counterpart', '') or '없음'}",
        f"상대 관련 웹 페이지:\n{pages or '없음'}",
        f"목표·물어볼 것:\n{body.get('goals_text', '') or '없음'}",
        f"지켜야 할 선:\n{body.get('guardrails', '') or '없음'}",
    ]
    if mode_key != "interview":
        content.append({"text": "\n\n".join(texts)})
        return llm_json("deep", PREP_SYSTEM, content, PREP_SCHEMA)
    bank = load_bank()
    if bank["answers"]:
        texts.append("답변 은행(지난 면접에서 사용자가 다듬은 답):\n" + "\n".join(
            f"- [{a['qtype']}]" + (f" ({a['company']} 면접용)" if a.get("company") else "") + f" {a['question']}\n  답: {a['answer']}\n  핵심어: {a.get('cue', '')}"
            for a in bank["answers"][:30]))
    if bank["lessons"]:
        texts.append("지난 면접에서 배운 점:\n" + "\n".join(f"- {x['text']}" for x in bank["lessons"][-15:]))
    content.append({"text": "\n\n".join(texts)})
    d = llm_json("deep", PREP_SYSTEM + "\n\n" + INTERVIEW_PREP_SYSTEM, content, INTERVIEW_PREP_SCHEMA)
    iv = d.get("interview", {})
    for a in iv.get("answers", []) + iv.get("risks", []):
        if a.get("qtype") not in QTYPES:
            a["qtype"] = "기타"
    return mask_kit(d, body.get("guardrails", ""))


# ---------- 면접: 준비 키트 · 답변 은행 ----------

QTYPES = ["자기소개", "지원 동기", "이직 사유", "강점", "약점", "성공 경험", "실패 경험", "갈등·협업", "리더십", "직무 역량",
          "기술 질문", "처우", "입사 시기", "근무 형태", "공백·경력 전환", "마지막 한마디", "기타"]
COMPANY_QTYPES = {"지원 동기", "마지막 한마디"}   # 회사마다 답이 달라지는 질문
SINGLE_QTYPES = {"자기소개", "지원 동기", "이직 사유", "강점", "약점", "처우", "입사 시기", "근무 형태", "마지막 한마디"}

INTERVIEW_PREP_SYSTEM = """이번 미팅은 면접이다. 위 항목에 더해 interview 묶음을 만든다. 목표는 면접 합격이다.
- message: 면접 내내 돌아올 나를 한 문장으로. 이 회사가 찾는 사람과 내 사실이 만나는 지점.
- criteria: 공고·회사 자료로 볼 때 면접관이 채점할 기준 최대 6개. 짧은 명사구(예: AI 도구 실무 활용, 원격 협업 신뢰).
- answers: 이 면접에서 나올 가능성이 큰 질문 최대 9개와 내 답. 자기소개와 지원 동기는 꼭 넣는다.
  qtype은 정해진 목록 중 하나. question은 면접관이 실제로 할 말투로.
  answer는 소리 내어 말할 답, 2~5문장, 첫 문장에 결론. 경험을 말할 때는 상황, 내가 한 일, 결과 순서로.
  answer에는 내 정보에 적힌 사실·숫자만 쓴다. 자료에 없는 경험, 숫자, 느낌, 동기, 계획은 지어내지 않고 ○○로 비운다.
  cue는 면접 중 화면에 띄울 핵심어 3~5개를 ' · '로 이은 한 줄, 25자 안팎. 문장으로 쓰지 않는다.
  facts는 answer에 쓴 내 정보 속 사실을 원문에 가깝게 최대 3개. gaps는 ○○ 자리에 사용자가 채울 것을 한 줄로, 없으면 빈 문자열.
- risks: 이 지원자에게 곤란할 질문 최대 6개. 경력 공백, 직함과 지원 직무 차이, 거주지·비자·원격, 처우, 이직 사유처럼 내 정보와 공고가 어긋나는 곳에서 고른다.
  answer는 사실을 인정하고 강점으로 돌리는 방어 답 2~4문장. dont는 이 질문에서 하면 안 되는 말 한 줄.
  cue, facts, gaps는 answers와 같은 규칙.
- 지켜야 할 선에 적힌 하한 금액, 내부 기준, 말하지 않을 것은 어떤 answer에도 그대로 쓰지 않는다. 처우 답은 범위를 먼저 묻거나 내가 정한 '말할 범위'만 쓴다.
- dont, cue, gaps에도 지켜야 할 선에 적힌 금액이나 숫자를 절대 쓰지 않는다. '하한 금액을 말하지 않는다'처럼 숫자 없이 쓴다. 이 글은 면접 중 화면에 뜬다.
- ask: 내가 면접관에게 할 질문 최대 5개, 우선순위 순. 회사 자료를 읽은 티가 나고 이 자리에서 일하는 모습이 그려지는 질문.
- dont: 이 면접에서 하지 말 말 최대 6개(검증 안 된 숫자, 써 보지 않은 도구, 지켜야 할 선 등).
- timeplan: 면접 시간을 알면 구간별 배분 최대 5줄, 모르면 빈 배열.
- 답변 은행이 주어지면 같은 qtype의 답을 바탕으로 이번 회사에 맞게 고친다. 사실과 숫자는 바꾸지 않는다. 지난 면접에서 배운 점을 반영한다.
- 이 면접에서 goals가 비었으면 기본 목표 대신 ask 앞 3개를 goals로 쓴다."""

_ANSWER = {"type": "object", "properties": {
    "qtype": {"type": "string", "enum": QTYPES}, "question": {"type": "string"}, "answer": {"type": "string"},
    "cue": {"type": "string"}, "facts": {"type": "array", "items": {"type": "string"}}, "gaps": {"type": "string"}},
    "required": ["qtype", "question", "answer", "cue", "facts", "gaps"], "additionalProperties": False}
_RISK = {"type": "object", "properties": {**_ANSWER["properties"], "dont": {"type": "string"}},
         "required": _ANSWER["required"] + ["dont"], "additionalProperties": False}
INTERVIEW_PREP_SCHEMA = json.loads(json.dumps(PREP_SCHEMA))
INTERVIEW_PREP_SCHEMA["properties"]["interview"] = {"type": "object", "properties": {
    "message": {"type": "string"}, "criteria": {"type": "array", "items": {"type": "string"}},
    "answers": {"type": "array", "items": _ANSWER}, "risks": {"type": "array", "items": _RISK},
    "ask": {"type": "array", "items": {"type": "string"}}, "dont": {"type": "array", "items": {"type": "string"}},
    "timeplan": {"type": "array", "items": {"type": "string"}}},
    "required": ["message", "criteria", "answers", "risks", "ask", "dont", "timeplan"], "additionalProperties": False}
INTERVIEW_PREP_SCHEMA["required"] = PREP_SCHEMA["required"] + ["interview"]

def secret_src(m):
    """가릴 숫자는 사용자가 직접 적은 '지켜야 할 선'에서만 뽑는다. 곤란한 질문 문장에서 붙은 숫자(연도 등)는 제외한다."""
    return m.get("secret_src", m.get("guardrails")) or ""


def private_numbers(guardrails):
    """지켜야 할 선에 적은 숫자 중 금액·기준처럼 드러나면 안 되는 것. 한 자리 숫자는 '주 1회'처럼 흔해 빼고, 단위가 붙은 것은 넣는다."""
    out = set()
    for mt in re.finditer(r"(\d[\d,]*(?:\.\d+)?)\s*(만|억|천|원|%|달러|불|k|K)?", guardrails or ""):
        num, unit = mt.group(1).rstrip(","), mt.group(2)
        if len(num.replace(",", "")) >= 2 or unit:
            out.add(num)
    return sorted(out, key=len, reverse=True)


def mask_private(text, guardrails):
    """지켜야 할 선의 숫자가 화면에 나갈 글에 섞이면 ○○로 가린다."""
    if not text:
        return text
    for n in private_numbers(guardrails):
        text = re.sub(rf"(?<![\d,]){re.escape(n)}(?![\d,])", "○○", text)
    return text


def mask_kit(prep, guardrails):
    iv = (prep or {}).get("interview")
    if not iv or not guardrails:
        return prep
    for a in iv.get("answers", []) + iv.get("risks", []):
        for k in ("question", "answer", "cue", "gaps", "dont"):
            if a.get(k):
                a[k] = mask_private(a[k], guardrails)
    for k in ("dont", "ask", "timeplan", "criteria"):
        iv[k] = [mask_private(x, guardrails) for x in iv.get(k, [])]
    iv["message"] = mask_private(iv.get("message", ""), guardrails)
    prep["watch"] = [mask_private(x, guardrails) for x in prep.get("watch", [])]
    return prep


BANK_LOCK = threading.Lock()


def bank_path():
    return DATA / "interview" / "bank.json"


def load_bank():
    b = read_json(bank_path(), {})
    return {"answers": b.get("answers", []), "lessons": b.get("lessons", []), "history": b.get("history", [])}


def save_bank(b):
    write_json(bank_path(), b, private=True)


def bank_upsert(b, item, source, company=""):
    """id가 오면 id로만 찾는다. id가 없으면 질문 글, 그다음 하나만 두는 질문 종류로 찾는다.
    회사마다 달라지는 답(지원 동기 등)은 같은 회사 것만 덮어쓰고, 다른 회사 답은 따로 남긴다.
    빈 값으로 기존 값을 지우지 않는다."""
    q = (item.get("question") or "").strip()
    qtype = item.get("qtype") if item.get("qtype") in QTYPES else "기타"
    company = (item.get("company") or company or "").strip()[:40]
    if not q and not (item.get("answer") or "").strip():
        return None
    hit = None
    if item.get("id"):
        hit = next((a for a in b["answers"] if a["id"] == item["id"]), None)
    else:
        same_co = lambda a: qtype not in COMPANY_QTYPES or (a.get("company") or "") == company
        hit = next((a for a in b["answers"] if a["question"].strip() == q and same_co(a)), None) or \
            next((a for a in b["answers"] if qtype in SINGLE_QTYPES and a["qtype"] == qtype and same_co(a)), None)
    if not hit:
        hit = {"id": uuid.uuid4().hex[:8], "scores": [], "company": company if qtype in COMPANY_QTYPES else ""}
        b["answers"].append(hit)
    new = {"qtype": qtype, "question": q, "answer": (item.get("answer") or "").strip(), "cue": (item.get("cue") or "").strip(),
           "facts": [f for f in item.get("facts", []) or [] if f][:5], "gaps": (item.get("gaps") or "").strip(),
           "dont": (item.get("dont") or "").strip()}
    hit.update({k: v for k, v in new.items() if v})
    for k in ("facts", "gaps", "dont", "cue"):
        hit.setdefault(k, [] if k == "facts" else "")
    hit.update({"source": source, "updated": time.strftime("%Y-%m-%d %H:%M")})
    return hit


def bank_op(body):
    op = body.get("op")
    with BANK_LOCK:
        b = load_bank()
        if op == "upsert":
            saved = [bank_upsert(b, x, body.get("source", "준비"), body.get("company", "")) for x in body.get("answers", [])]
            save_bank(b)
            return {"ok": True, "saved": len([x for x in saved if x]), "bank": b}
        if op == "delete":
            b["answers"] = [a for a in b["answers"] if a["id"] != body.get("id")]
        elif op == "edit":
            for a in b["answers"]:
                if a["id"] == body.get("id"):
                    for k in ("question", "answer", "cue"):
                        if k in body:
                            a[k] = str(body[k]).strip()
                    a["updated"] = time.strftime("%Y-%m-%d %H:%M")
        elif op == "score":
            for a in b["answers"]:
                if a["id"] == body.get("id"):
                    a.setdefault("scores", []).append({"date": time.strftime("%Y-%m-%d"), "total": int(body.get("total") or 0)})
                    a["scores"] = a["scores"][-10:]
        elif op == "lesson_delete":
            i = int(body.get("index", -1))
            if 0 <= i < len(b["lessons"]):
                b["lessons"].pop(i)
        elif op == "result":
            for h in b["history"]:
                if h["id"] == body.get("id"):
                    h["result"] = str(body.get("result", "대기"))[:20]
        elif op == "carry":
            mid = str(body.get("id", ""))
            folder = DATA / "meetings" / mid
            m, after = read_json(folder / "meeting.json", None), read_json(folder / "after.json", None)
            if not m or not after or not after.get("debrief"):
                raise RuntimeError("가져갈 면접 정리가 없어요")
            deb = after["debrief"]
            picks = set(body.get("picks", []))
            for i, x in enumerate(deb.get("answers", [])):
                if i in picks and x.get("better"):
                    bank_upsert(b, {"qtype": x.get("qtype"), "question": x.get("question"), "answer": mask_private(x["better"], secret_src(m)),
                                    "cue": mask_private(x.get("cue", ""), secret_src(m))}, "복기", company_of(m.get("title", "")))
            known = {x["text"] for x in b["lessons"]}
            for t in deb.get("lessons", []):
                if t and t not in known:
                    b["lessons"].append({"text": t, "date": time.strftime("%Y-%m-%d"), "from": m.get("title", "")})
            b["lessons"] = b["lessons"][-40:]
            if all(h["id"] != mid for h in b["history"]):
                b["history"].insert(0, {"id": mid, "company": m.get("title", ""), "date": mid[:8], "result": "대기"})
            after["carried"] = True
            write_json(folder / "after.json", after)
        else:
            raise RuntimeError("알 수 없는 요청이에요")
        save_bank(b)
        return {"ok": True, "bank": b}


def company_of(title):
    """'회사 · 면접' 꼴 제목에서 회사 부분만."""
    return (title or "").split(" · ")[0].strip()[:40]


def interview_cards(prep):
    """면접 키트의 예상 질문과 곤란한 질문을 미팅 중 찾아 쓸 카드 목록으로 만든다."""
    iv = (prep or {}).get("interview") or {}
    cards = [{**a, "risk": False, "dont": ""} for a in iv.get("answers", [])]
    cards += [{**a, "risk": True} for a in iv.get("risks", [])]
    return [{k: c.get(k, "") for k in ("qtype", "question", "answer", "cue", "dont", "risk")} for c in cards if c.get("question")]


# ---------- 면접 연습: 채점 ----------

REHEARSE_SYSTEM = """너는 면접 코치다. 사용자가 예상 질문에 연습으로 한 답을 채점하고 더 나은 답을 준다.
- 말로 한 답을 받아쓴 글일 수 있다. 받아쓰기 오류와 말버릇은 감점하지 않는다.
- scores: 아래 4개 기준을 이 순서로, 각 1~5점과 이유 한 줄.
  결론 먼저(첫 문장이 질문에 바로 답하나), 구체성(내 사실·숫자·사례가 있나), 질문 적합(묻는 것에 답하고 회사·직무와 이어지나), 위험 관리(말하지 말 것, 검증 안 된 주장, 내부 기준 노출이 없나).
- total: 0~100 종합 점수. 말한 시간이 주어지면 2분을 넘을 때 감점한다.
- good: 잘한 점 최대 3개. fix: 고칠 점 최대 3개, 바로 따라 할 수 있게 구체적으로.
- better: 같은 질문에 대한 더 나은 답, 2~5문장, 말하듯 존댓말. 사용자의 답과 '내 정보'에 있는 사실·숫자만 쓴다. 없는 경험, 숫자, 느낌, 동기는 지어내지 않고 ○○로 비운다.
- cue: better를 떠올리게 할 핵심어 3~5개를 ' · '로 이은 한 줄.
- followup_q: 이 답을 들은 면접관이 이어서 할 꼬리 질문 한 문장.
- 한국어로 쓴다. 긴 줄표(엠대시) 문장부호를 쓰지 않는다."""

REHEARSE_SCHEMA = {"type": "object", "properties": {
    "scores": {"type": "array", "items": {"type": "object", "properties": {
        "name": {"type": "string"}, "score": {"type": "integer"}, "why": {"type": "string"}},
        "required": ["name", "score", "why"], "additionalProperties": False}},
    "total": {"type": "integer"}, "good": {"type": "array", "items": {"type": "string"}},
    "fix": {"type": "array", "items": {"type": "string"}}, "better": {"type": "string"},
    "cue": {"type": "string"}, "followup_q": {"type": "string"}},
    "required": ["scores", "total", "good", "fix", "better", "cue", "followup_q"], "additionalProperties": False}


def rehearse(body):
    answer = (body.get("answer") or "").strip()
    if len(answer) < 5:
        raise RuntimeError("답이 너무 짧아요. 한두 문장 이상 말하거나 적어 주세요.")
    profile = read_json(DATA / "profile.json", {})
    content = []
    facts = (body.get("facts") or "").strip()  # 준비 자료에서 뽑은 내 사실. 있으면 PDF를 다시 보내지 않아 비용이 준다
    if not profile.get("text") and not facts and profile.get("pdf_b64"):
        content.append({"pdf": profile["pdf_b64"]})
    content.append({"text": "\n\n".join([
        f"내 정보:\n{profile.get('text', '') or ''}\n{facts}".strip() or "내 정보:\n(첨부 PDF)",
        f"면접 맥락:\n{body.get('context', '') or '없음'}",
        f"지켜야 할 선·말하지 말 것:\n{body.get('guardrails', '') or '없음'}",
        f"질문 종류: {body.get('qtype', '기타')}",
        f"질문: {body.get('question', '')}",
        f"미리 준비한 모범 답(참고): {body.get('ref', '') or '없음'}",
        f"말한 시간: {int(body.get('secs') or 0)}초" if body.get("secs") else "말한 시간: 모름(글로 씀)",
        f"사용자의 연습 답:\n{answer[:4000]}"])})
    d = llm_json("coach", REHEARSE_SYSTEM, content, REHEARSE_SCHEMA)
    d["total"] = max(0, min(100, int(d.get("total", 0))))
    for k in ("better", "cue"):
        d[k] = mask_private(d.get(k, ""), body.get("guardrails"))
    for x in d.get("scores", []):
        x["score"] = max(1, min(5, int(x.get("score", 1))))
    return d


def transcribe_practice(body):
    """연습 답 음성(16kHz 모노 16비트)을 맥 안에서 받아쓴다. 소리는 남기지 않는다."""
    pcm = base64.b64decode(body.get("pcm_b64", ""), validate=True)
    if len(pcm) < RATE * 2 // 2:
        raise RuntimeError("녹음이 너무 짧아요")
    lang = body.get("lang") if body.get("lang") in ("ko", "en", "auto") else "ko"
    if not whisper_up():
        whisper.start(lang)
    # 받아쓰기 엔진이 미팅용으로 다른 언어로 떠 있어도, 요청마다 언어를 넘겨 이번 연습 언어로 받아쓴다
    text = whisper.transcribe(pcm[: RATE * 2 * 240], "", lang)
    return {"text": text, "secs": round(len(pcm) / (RATE * 2))}


def compose_brief(prep):
    """구조화된 준비 자료를 실시간 요약용 글로 바꾼다."""
    if not prep:
        return ""
    cp, me = prep.get("counterpart", {}), prep.get("me", {})
    parts = ["상대: " + cp.get("who", "")] + [f"- {x}" for x in cp.get("points", [])]
    parts += ["", "나: " + me.get("headline", "")] + [f"- {x}" for x in me.get("points", [])]
    if prep.get("talk"):
        parts += ["", "이번 미팅에서 꺼낼 것:"] + [f"- {x}" for x in prep["talk"]]
    if prep.get("watch"):
        parts += ["", "조심하거나 확인할 것:"] + [f"- {x}" for x in prep["watch"]]
    iv = prep.get("interview") or {}
    if iv.get("message"):
        parts += ["", "면접에서 계속 돌아올 한 줄: " + iv["message"]]
    if iv.get("criteria"):
        parts += ["", "면접관이 볼 기준:"] + [f"- {x}" for x in iv["criteria"]]
    return "\n".join(parts)


# ---------- PDF ----------

def doc_html(title, subtitle, sections):
    """sections = [{title, items:[str], lead:str?, pre:str?}] 를 A4 문서 HTML로 만든다."""
    e = htmllib.escape
    body = []
    for sec in sections:
        items = [i for i in sec.get("items", []) if str(i).strip()]
        if not items and not sec.get("lead") and not sec.get("pre"):
            continue
        body.append(f'<section><h2>{e(sec["title"])}</h2>')
        if sec.get("lead"):
            body.append(f'<p class="lead">{e(sec["lead"])}</p>')
        if items:
            body.append("<ul>" + "".join(f"<li>{e(str(i))}</li>" for i in items) + "</ul>")
        if sec.get("pre"):
            body.append(f'<div class="pre">{e(sec["pre"])}</div>')
        body.append("</section>")
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, "Apple SD Gothic Neo", sans-serif; color: #1b1c1e; margin: 0; padding: 0 44px;
  word-break: keep-all; overflow-wrap: anywhere; font-size: 11pt; line-height: 1.6; }}
header {{ border-bottom: 2px solid #1b1c1e; padding-bottom: 10px; margin-bottom: 18px; }}
.brand {{ font-size: 8.5pt; letter-spacing: .08em; color: #8a6d1d; font-weight: 700; }}
h1 {{ font-size: 19pt; margin: 4px 0 2px; line-height: 1.3; }}
.sub {{ color: #6b6e73; font-size: 9.5pt; }}
section {{ margin-bottom: 16px; }}
h2 {{ break-after: avoid; }} li, .lead {{ break-inside: avoid; }}
h2 {{ font-size: 11.5pt; margin: 0 0 6px; padding-left: 8px; border-left: 3px solid #e0b43c; }}
.lead {{ margin: 0 0 6px; font-weight: 600; }}
ul {{ margin: 0; padding-left: 18px; }}
li {{ margin-bottom: 3px; }}
.pre {{ white-space: pre-wrap; background: #f5f3ee; border-radius: 6px; padding: 10px 12px; font-size: 10.5pt; }}
footer {{ margin-top: 24px; color: #7d8086; font-size: 8pt; }}
</style></head><body><header><div class="brand">미팅냥</div><h1>{e(title)}</h1><div class="sub">{e(subtitle)}</div></header>
{"".join(body)}<footer>미팅냥으로 만든 문서입니다. 자료에 없는 내용은 적지 않았습니다.</footer></body></html>"""


def render_pdf(title, subtitle, sections):
    if not PDF.exists():
        raise RuntimeError("PDF 프로그램이 없습니다. ./install.sh 를 다시 실행하십시오.")
    out = DATA / f"render-{uuid.uuid4().hex}.pdf"
    r = subprocess.run([str(PDF), str(out)], input=doc_html(title, subtitle, sections).encode(), capture_output=True, timeout=60)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError("PDF를 만들지 못했습니다: " + r.stderr.decode(errors="replace").strip())
    data = out.read_bytes()
    out.unlink()
    return data


# ---------- 미팅 후: 정리 ----------

AFTER_SYSTEM = """너는 끝난 미팅을 정리한다. 받아쓴 글은 받아쓰기 오류가 섞여 있으니 문맥으로 바로잡아 읽는다.
규칙:
- 대화에 나온 사실만 쓴다. 나오지 않은 결정·약속·숫자를 만들지 않는다.
- summary: 5줄 이내 불릿 문장 배열.
- decisions, actions(who·what·when), numbers(what·value), open_questions(풀리지 않은 쟁점)를 뽑는다. 실시간으로 뽑아 둔 목록이 주어지면 대조해 틀린 것은 고치고 빠진 것은 더한다.
- followup: 상대에게 보낼 후속 메일 초안. 순수 텍스트(마크다운 기호 금지). 첫 줄 인사, 오늘 나눈 핵심, 합의한 다음 단계, 맺음. 12줄 이내. 미팅 종류가 내부 회의면 참석자에게 보내는 정리 메시지로 쓴다.
- 한국어로 쓴다. 긴 줄표(엠대시) 문장부호를 쓰지 않는다."""

AFTER_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "array", "items": {"type": "string"}},
        "decisions": {"type": "array", "items": {"type": "string"}},
        "actions": LIVE_SCHEMA["properties"]["actions"],
        "numbers": LIVE_SCHEMA["properties"]["numbers"],
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "followup": {"type": "string"},
    },
    "required": ["summary", "decisions", "actions", "numbers", "open_questions", "followup"],
    "additionalProperties": False,
}


INTERVIEW_AFTER_SYSTEM = """이번 미팅은 면접이었다. 위 항목에 더해 debrief 묶음을 만든다. 목적은 다음 면접 합격률을 올리는 복기다.
- followup은 면접관에게 보낼 짧은 감사 메일로 쓴다. 오늘 대화에서 실제로 나온 내용 하나를 짚고, 다음 단계를 기다린다는 말로 맺는다. 8줄 이내.
- scores: '면접관이 볼 기준' 각각에 대해 오늘 대화로 본 1~5점과 근거 한 줄. 기준이 없으면 면접 일반 기준 4개(결론 먼저, 구체성, 직무 적합, 태도)로.
- answers: 면접관이 나에게 한 주요 질문마다 하나, 최대 10개. question(질문 요지), qtype(정해진 목록 중), mine(내가 실제로 한 답 요약 한 줄), verdict(좋음, 보통, 아쉬움 중 하나), better(더 나은 답 2~4문장), cue(핵심어 3~5개 ' · ').
  better에는 내가 대화에서 말한 사실과 배경 자료의 사실만 쓴다. 없는 경험, 숫자, 느낌은 ○○로 비운다.
- went_well: 잘한 것 최대 3개. to_fix: 고칠 것 최대 3개, 구체적으로.
- lessons: 다음 면접에도 그대로 쓸 수 있는 배운 점 최대 4개. 회사 이름 없이 일반 문장으로.
- signals: 면접관이 보인 관심·우려 신호 최대 3개(대화 근거가 있을 때만).
- 받아쓴 대화에 나오지 않은 질문을 만들지 않는다."""

INTERVIEW_AFTER_SCHEMA = json.loads(json.dumps(AFTER_SCHEMA))
INTERVIEW_AFTER_SCHEMA["properties"]["debrief"] = {"type": "object", "properties": {
    "scores": REHEARSE_SCHEMA["properties"]["scores"],
    "answers": {"type": "array", "items": {"type": "object", "properties": {
        "question": {"type": "string"}, "qtype": {"type": "string", "enum": QTYPES}, "mine": {"type": "string"},
        "verdict": {"type": "string", "enum": ["좋음", "보통", "아쉬움"]}, "better": {"type": "string"}, "cue": {"type": "string"}},
        "required": ["question", "qtype", "mine", "verdict", "better", "cue"], "additionalProperties": False}},
    "went_well": {"type": "array", "items": {"type": "string"}}, "to_fix": {"type": "array", "items": {"type": "string"}},
    "lessons": {"type": "array", "items": {"type": "string"}}, "signals": {"type": "array", "items": {"type": "string"}}},
    "required": ["scores", "answers", "went_well", "to_fix", "lessons", "signals"], "additionalProperties": False}
INTERVIEW_AFTER_SCHEMA["required"] = AFTER_SCHEMA["required"] + ["debrief"]


def wrap_up(m):
    folder = DATA / "meetings" / m["id"]
    lines = [json.loads(l) for l in (folder / "transcript.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()] \
        if (folder / "transcript.jsonl").exists() else []
    pins = read_json(folder / "pins.json", [])
    result = {"summary": [], "decisions": hub.decisions, "actions": hub.actions, "numbers": hub.numbers,
              "open_questions": [], "followup": ""}
    if key_for(provider()) and lines:
        names = read_json(folder / "speakers.json", {})
        lab = lambda l: (names.get(str(l.get("spk")), {}).get("name") or "상대") if l["who"] == "them" else "나"
        convo = "\n".join(f"[{l['t']}] [{lab(l)}] {l['text']}" for l in lines)
        iv = m["mode"] == "interview"
        crit = ((m.get("prep") or {}).get("interview") or {}).get("criteria") or []
        result = llm_json("deep", AFTER_SYSTEM + ("\n\n" + INTERVIEW_AFTER_SYSTEM if iv else ""), [{"text": "\n\n".join([
                f"미팅 종류: {MODES[m['mode']]['name']}", f"배경 자료:\n{m.get('brief', '')}",
                f"면접관이 볼 기준: {', '.join(crit) or '없음'}",
                f"실시간으로 뽑아 둔 목록: {json.dumps({'decisions': hub.decisions, 'actions': hub.actions, 'numbers': hub.numbers}, ensure_ascii=False)}",
                f"사용자가 핀 고정한 것: {json.dumps([p['text'] for p in pins], ensure_ascii=False)}",
                f"받아쓴 대화:\n{convo}"])}], INTERVIEW_AFTER_SCHEMA if iv else AFTER_SCHEMA)
    result["goals"] = [{"text": g, "done": i in hub.covered} for i, g in enumerate(m.get("goals", []))]
    result["pins"] = pins
    result["ended"] = time.strftime("%Y-%m-%d %H:%M")
    write_json(folder / "after.json", result)
    return result


# ---------- 미팅 시작·끝 ----------

state_lock = threading.Lock()


def seed_prep(prep):
    """준비 자료의 핀·용어를 시작 화면에 미리 깔아 둔다."""
    hub.pins = [{"text": x.strip(), "t": "준비"} for x in prep.get("pins", []) if x.strip()]
    for item in prep.get("terms", []):
        term, _, meaning = item.partition(":")
        if term.strip():
            hub.terms.append({"term": term.strip(), "heard": term.strip(), "short": meaning.strip()[:10], "meaning": meaning.strip()})


def start_meeting(body):
    with state_lock:
        if hub.meeting:
            raise RuntimeError("이미 진행 중인 미팅이 있습니다")
        mid = time.strftime("%Y%m%d-%H%M%S")
        m = {
            "id": mid, "mode": body.get("mode", "meeting"), "title": body.get("title") or "미팅",
            "brief": compose_brief(body.get("prep")) or body.get("brief", ""), "prep": body.get("prep"), "goals": [g for g in body.get("goals", []) if g.strip()],
            "guardrails": body.get("guardrails", ""), "secret_src": body.get("guardrails", ""), "stt_hint": body.get("stt_hint", ""),
            "lang": body.get("lang", "ko"), "minutes": int(body.get("minutes") or 0),
            "started": time.time(),
        }
        if m["mode"] not in MODES:
            raise RuntimeError("알 수 없는 미팅 종류입니다")
        if m["mode"] == "interview":
            m["prep"] = mask_kit(m["prep"], m["guardrails"])
            m["cards"] = interview_cards(m["prep"])
            iv = (m["prep"] or {}).get("interview") or {}
            donts = [x for x in iv.get("dont", []) if x] + [f"{c['question']}: {c['dont']}" for c in m["cards"] if c.get("dont")]
            if donts:
                m["guardrails"] = (m["guardrails"] + "\n" if m["guardrails"] else "") + "말하지 않을 것:\n" + "\n".join(f"- {x}" for x in donts)
        (DATA / "meetings" / mid).mkdir(parents=True, exist_ok=True)
        write_json(DATA / "meetings" / mid / "meeting.json", m)
        whisper.start(m["lang"])
        hub.reset()
        diarizer.reset()
        hub.meeting = m
        seed_prep(m.get("prep") or {})
        capture.start(m["stt_hint"])
        hub.send(hub.snapshot())
        return {"id": mid}


def stop_meeting():
    with state_lock:
        m = hub.meeting
        if not m:
            raise RuntimeError("진행 중인 미팅이 없습니다")
        capture.stop()
        write_json(DATA / "meetings" / m["id"] / "speakers.json", hub.speakers)
        hub.send({"type": "status", "state": "wrapping"})
        try:
            result = wrap_up(m)
        finally:
            hub.reset()
            hub.send(hub.snapshot())
        return {"id": m["id"], "after": result}


def list_meetings():
    out = []
    for d in sorted((DATA / "meetings").glob("*/"), reverse=True)[:30]:
        m = read_json(d / "meeting.json", None)
        if m:
            out.append({"id": m["id"], "title": m["title"], "mode": m["mode"], "has_after": (d / "after.json").exists()})
    return out


# ---------- 웹 ----------

def load_token():
    """폰·브라우저 주소의 열쇠. 한 번 만들어 두고 다시 켜도 같은 값을 쓴다."""
    cfg = config()
    if not cfg.get("token"):
        cfg["token"] = secrets.token_urlsafe(12)
        write_json(DATA / "config.json", cfg, private=True)
    return cfg["token"]


TOKEN = ""
STATIC = {"/logo.svg": "image/svg+xml", "/logo.json": "application/json", "/vendor/lottie_light.min.js": "text/javascript"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _authed(self):
        if self.client_address[0] in ("127.0.0.1", "::1"):  # 이 맥에서 연 화면은 열쇠 없이 통과
            return True
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        return self.headers.get("X-Key") == TOKEN or q.get("k", [""])[0] == TOKEN

    def _json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            body = (WEB / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if path in STATIC:
            body = (WEB / path.lstrip("/")).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", STATIC[path])
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if not self._authed():
            return self._json(401, {"error": "주소의 열쇠가 맞지 않습니다. 맥 화면의 QR 코드로 다시 여십시오."})
        if path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            q = hub.subscribe()
            try:
                while True:
                    try:
                        msg = q.get(timeout=15)
                        self.wfile.write(f"data: {json.dumps(msg, ensure_ascii=False)}\n\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                hub.unsubscribe(q)
            return
        if path == "/api/bank":
            return self._json(200, load_bank())
        if path == "/api/state":
            p = read_json(DATA / "profile.json", {})
            return self._json(200, {
                "provider": provider(), "has_key": bool(key_for(provider())),
                "providers": {k: {"name": v["name"], "keys": v["keys"], "has_key": bool(key_for(k)), "live": model_for(k, "live")} for k, v in PROVIDERS.items()}, "profile": {"text": p.get("text", ""), "pdf_name": p.get("pdf_name", "")},
                "meeting": hub.snapshot()["meeting"], "lan": f"http://{lan_ip()}:{self.server.server_port}/?k={TOKEN}",
                "meetings": list_meetings()})
        m = re.fullmatch(r"/api/meetings/([\w-]+)", path)
        if m:
            folder = DATA / "meetings" / m.group(1)
            return self._json(200, {"meeting": read_json(folder / "meeting.json", None), "after": read_json(folder / "after.json", None)})
        self._json(404, {"error": "없음"})

    def do_POST(self):
        if not self._authed():
            return self._json(401, {"error": "열쇠가 맞지 않습니다"})
        path = urllib.parse.urlparse(self.path).path
        try:
            body = self._body()
            if path == "/api/settings":
                cfg = config()
                if cfg.get("api_key"):
                    cfg.setdefault("keys", {}).setdefault("claude", cfg.pop("api_key"))
                p = body.get("provider")
                if p in PROVIDERS:
                    cfg["provider"] = p
                    if body.get("api_key"):
                        cfg.setdefault("keys", {})[p] = body["api_key"].strip()
                write_json(DATA / "config.json", cfg, private=True)
                return self._json(200, {"ok": True})
            if path == "/api/profile":
                p = read_json(DATA / "profile.json", {})
                if "text" in body:
                    p["text"] = body["text"]
                if body.get("pdf_b64"):
                    base64.b64decode(body["pdf_b64"], validate=True)
                    p["pdf_b64"], p["pdf_name"] = body["pdf_b64"], body.get("pdf_name", "이력서.pdf")
                if body.get("clear_pdf"):
                    p.pop("pdf_b64", None)
                    p.pop("pdf_name", None)
                write_json(DATA / "profile.json", p, private=True)
                return self._json(200, {"ok": True})
            if path == "/api/pdf":
                data = render_pdf(body.get("title", "미팅"), body.get("subtitle", ""), body.get("sections", []))
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if path == "/api/prepare":
                return self._json(200, prepare(body))
            if path == "/api/bank":
                return self._json(200, bank_op(body))
            if path == "/api/rehearse":
                return self._json(200, rehearse(body))
            if path == "/api/transcribe":
                return self._json(200, transcribe_practice(body))
            if path == "/api/start":
                r = start_meeting(body)
                log(f"미팅 시작 {r['id']} ({body.get('mode')})")
                return self._json(200, r)
            if path == "/api/stop":
                return self._json(200, stop_meeting())
            if path == "/api/speaker":
                sid = str(body.get("id"))
                if hub.meeting and sid in hub.speakers:
                    into = str(body.get("merge_into", ""))
                    if into and into in hub.speakers and into != sid:
                        for l in hub.lines:
                            if str(l.get("spk")) == sid:
                                l["spk"] = int(into)
                        hub.speakers[into]["segs"] += hub.speakers[sid]["segs"]
                        hub.speakers[into]["secs"] = round(hub.speakers[into]["secs"] + hub.speakers[sid]["secs"], 1)
                        del hub.speakers[sid]
                        diarizer.merge(int(sid), int(into))
                        hub.send(hub.snapshot())
                    elif body.get("name", "").strip():
                        hub.speakers[sid]["name"] = body["name"].strip()[:30]
                        hub.send({"type": "speakers", "speakers": hub.speakers})
                    write_json(DATA / "meetings" / hub.meeting["id"] / "speakers.json", hub.speakers)
                return self._json(200, {"ok": True})
            if path == "/api/pin":
                if hub.meeting:
                    hub.pins = body.get("pins", [])[:200]
                    write_json(DATA / "meetings" / hub.meeting["id"] / "pins.json", hub.pins)
                    hub.send({"type": "pins", "pins": hub.pins})  # 맥과 폰의 핀을 맞춘다
                return self._json(200, {"ok": True})
        except LLMError as ex:
            log(f"요청 실패 {path}: {ex}")
            return self._json(400, {"error": str(ex)})
        except (RuntimeError, ValueError, KeyError, subprocess.TimeoutExpired, urllib.error.URLError) as ex:
            msg = getattr(ex, "message", None) or str(ex)
            log(f"요청 실패 {path}: {msg}")
            return self._json(400, {"error": msg})
        self._json(404, {"error": "없음"})


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    ap = argparse.ArgumentParser(description="미팅냥")
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--no-open", action="store_true", help="맥 브라우저를 자동으로 열지 않는다")
    args = ap.parse_args()

    DATA.mkdir(parents=True, exist_ok=True)
    global TOKEN
    TOKEN = load_token()
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    local = f"http://localhost:{args.port}/?k={TOKEN}"
    log(f"맥에서 열기: {local}")
    log(f"폰에서 열기: http://{lan_ip()}:{args.port}/?k={TOKEN}  (맥 화면의 QR 코드를 찍어도 됩니다)")
    if not args.no_open:
        subprocess.Popen(["open", local])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        capture.stop()
        whisper.stop()


if __name__ == "__main__":
    main()
