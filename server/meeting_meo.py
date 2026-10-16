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
DATA = Path.home() / "Library" / "Application Support" / "meeting-meo"
MODEL_FILE = "ggml-large-v3-turbo-q5_0.bin"
MODEL_URL = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{MODEL_FILE}"
ALT_MODEL = Path.home() / "Library/Application Support/alt/models/whisper-cpp" / MODEL_FILE
WHISPER_PORT = 8178

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
    model = model_for(p, kind)
    live = kind == "live"

    if p == "claude":
        content = []
        for x in parts:
            if "pdf" in x:
                content.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": x["pdf"]}})
            else:
                content.append({"type": "text", "text": x["text"]})
        kw = dict(model=model, max_tokens=1000 if live else 8000,
                  system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                  messages=[{"role": "user", "content": content}],
                  output_config={"effort": "low" if live else "medium", "format": {"type": "json_schema", "schema": schema}})
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
                "reasoning": {"effort": "low" if live else "medium"},
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
            "meeting": {k: m.get(k) for k in ("id", "mode", "title", "goals", "started", "minutes", "prep")} if m else None,
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

    @staticmethod
    def transcribe(pcm, hint):
        out = io.BytesIO()
        w = wave.open(out, "wb")
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
        w.close()
        boundary = uuid.uuid4().hex
        parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
                 for k, v in (("response_format", "json"), ("temperature", "0"), ("prompt", hint))]
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\n'
                     f"Content-Type: audio/wav\r\n\r\n".encode() + out.getvalue() + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        req = urllib.request.Request(
            f"http://127.0.0.1:{WHISPER_PORT}/inference", data=b"".join(parts),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=30) as r:
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
        lines = hub.lines[-30:]
        convo = "\n".join(f"[{who_label(l)}] {l['text']}" + (f" (한국어: {l['ko']})" if l.get("ko") else "") for l in lines)
        them = [l["text"] for l in lines if l["who"] == "them"]
        them_lines = [l for l in lines if l["who"] == "them"]
        latest = them[-1] if them else ""
        if len(them) >= 2 and len(latest) < 15:
            latest = them[-2] + " " + latest
        known = ", ".join(t["term"] for t in hub.terms) or "없음"
        t0 = time.time()
        done = json.dumps({"결정": hub.decisions, "할 일": [x["what"] for x in hub.actions], "숫자": [f"{x['what']} {x['value']}" for x in hub.numbers]}, ensure_ascii=False)
        d = llm_json("live", system, [{"text": f"이미 풀이한 용어: {known}\n이미 기록한 것(같은 뜻이면 다시 넣지 않는다): {done}\n\n대화:\n{convo}\n\n지금 gist·reply로 다룰 상대의 가장 최근 말:\n{latest}"}], LIVE_SCHEMA)
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
        if d["alert"]:
            hub.alerts.append({"t": time.strftime("%H:%M"), "text": d["alert"]})
        if d["flow"]:
            hub.flow = d["flow"]
        card = {k: d[k] for k in ("kind", "gist", "intent", "reply", "hints", "alert")}
        card["speaker"] = who_label(them_lines[-1]) if them_lines else ""
        card["ms"] = int((time.time() - t0) * 1000)
        hub.card = card
        snap = hub.snapshot()
        hub.send({"type": "card", "card": card, **{k: snap[k] for k in ("terms", "flow", "decisions", "actions", "numbers", "covered", "alerts")}})
        log(f"요약 {card['ms']}ms ({provider()})")


analyst = Analyst()


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
            threading.Thread(target=self._feed_file, args=(feed,), daemon=True).start()
            return
        if not TAP.exists():
            raise RuntimeError("소리 받기 프로그램이 없습니다. ./install.sh 를 먼저 실행하십시오.")
        self.proc = subprocess.Popen([str(TAP)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()
        threading.Thread(target=lambda p=self.proc: [log("소리 받기:", l.decode().strip()) for l in p.stderr], daemon=True).start()

    def stop(self):
        if self.proc:
            self.proc.terminate()
            self.proc = None

    def _feed_file(self, path):
        tmp = DATA / "feed.wav"
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", path, str(tmp)], check=True)
        with wave.open(str(tmp)) as w:
            pcm = w.readframes(w.getnframes())
        tmp.unlink()
        step = RATE * 2 // 10
        for i in range(0, len(pcm), step):
            if not hub.meeting:
                return
            self.them.feed(pcm[i:i + step])
            self.me.feed(b"\x00" * len(pcm[i:i + step]))
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
            (self.them if head[0] == 0 else self.me).feed(data)

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
        "stt_hint": {"type": "string"},
    },
    "required": ["title", "counterpart", "me", "talk", "watch", "goals", "stt_hint"],
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
    mode = MODES[body.get("mode", "meeting")]
    content = [{"pdf": profile["pdf_b64"]}] if profile.get("pdf_b64") else []
    pages = "\n\n".join(f"[{u}]\n{fetch_page(u)}" for u in body.get("urls", []) if u.strip())
    content.append({"text": "\n\n".join([
        f"미팅 종류: {mode['name']}",
        f"내 정보(직접 쓴 글):\n{profile.get('text', '') or '없음'}" + ("\n(첨부 PDF도 내 정보다)" if profile.get("pdf_b64") else ""),
        f"상대 정보(직접 쓴 글):\n{body.get('counterpart', '') or '없음'}",
        f"상대 관련 웹 페이지:\n{pages or '없음'}",
        f"목표·물어볼 것:\n{body.get('goals_text', '') or '없음'}",
        f"지켜야 할 선:\n{body.get('guardrails', '') or '없음'}",
    ])})
    return llm_json("deep", PREP_SYSTEM, content, PREP_SCHEMA)


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
        result = llm_json("deep", AFTER_SYSTEM, [{"text": "\n\n".join([
                f"미팅 종류: {MODES[m['mode']]['name']}", f"배경 자료:\n{m.get('brief', '')}",
                f"실시간으로 뽑아 둔 목록: {json.dumps({'decisions': hub.decisions, 'actions': hub.actions, 'numbers': hub.numbers}, ensure_ascii=False)}",
                f"사용자가 핀 고정한 것: {json.dumps([p['text'] for p in pins], ensure_ascii=False)}",
                f"받아쓴 대화:\n{convo}"])}], AFTER_SCHEMA)
    result["goals"] = [{"text": g, "done": i in hub.covered} for i, g in enumerate(m.get("goals", []))]
    result["pins"] = pins
    result["ended"] = time.strftime("%Y-%m-%d %H:%M")
    write_json(folder / "after.json", result)
    return result


# ---------- 미팅 시작·끝 ----------

state_lock = threading.Lock()


def start_meeting(body):
    with state_lock:
        if hub.meeting:
            raise RuntimeError("이미 진행 중인 미팅이 있습니다")
        mid = time.strftime("%Y%m%d-%H%M%S")
        m = {
            "id": mid, "mode": body.get("mode", "meeting"), "title": body.get("title") or "미팅",
            "brief": compose_brief(body.get("prep")) or body.get("brief", ""), "prep": body.get("prep"), "goals": [g for g in body.get("goals", []) if g.strip()],
            "guardrails": body.get("guardrails", ""), "stt_hint": body.get("stt_hint", ""),
            "lang": body.get("lang", "ko"), "minutes": int(body.get("minutes") or 0),
            "started": time.time(),
        }
        if m["mode"] not in MODES:
            raise RuntimeError("알 수 없는 미팅 종류입니다")
        (DATA / "meetings" / mid).mkdir(parents=True, exist_ok=True)
        write_json(DATA / "meetings" / mid / "meeting.json", m)
        whisper.start(m["lang"])
        hub.reset()
        diarizer.reset()
        hub.meeting = m
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
        except (RuntimeError, ValueError, KeyError, subprocess.TimeoutExpired) as ex:
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
