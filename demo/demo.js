// [Define404]
// 미팅냥 데모: 서버 없이 화면만 열어 예시 미팅을 재생한다.
// 실제 화면 코드(web/index.html)는 그대로 두고, 서버와 주고받는 부분(fetch, EventSource)만 바꿔 끼운다.
(function () {
  window.MM_DEMO = true;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const now = () => new Date().toTimeString().slice(0, 8);
  const MODE_NAME = { interview: "면접", sales: "영업·제안", meeting: "회의" };

  // ---------- 예시 자료 ----------
  const PREP = {
    interview: {
      title: "○○랩 박 대표 · 면접",
      counterpart: { who: "B2B SaaS 스타트업 ○○랩 박 대표와 CTO, 프로덕트 디자이너 1차 면접 30분", points: [
        "○○랩은 작은 가게 사장님용 예약·고객 관리 서비스를 만든다", "고객사 약 1,200곳, 지난해 연간 반복 매출(ARR) 30% 성장",
        "팀 14명, 디자이너는 1명뿐이라 0에서 1을 혼자 끌 사람을 찾는다", "1차 면접은 지원 동기, 이전 제품 경험, 협업 방식을 본다"] },
      me: { headline: "기획부터 출시까지 직접 끝내는 프로덕트 디자이너", points: [
        "사내 출퇴근 앱을 1주 만에 앱스토어·플레이스토어 동시 출시", "자사 제품 10종 기획·디자인, 4종 스토어 출시",
        "디자인 토큰 140개로 디자인 체계 수립", "고객 인터뷰 20회로 예약 흐름을 다시 설계한 경험"] },
      talk: ["작은 가게용 제품을 직접 만들어 본 경험", "개발자와 같은 날 화면을 맞추는 협업 방식", "혼자서 0에서 1을 끌어 본 사례"],
      watch: ["디자이너 1명 구조라 업무 범위가 넓을 수 있으니 기대치 확인", "원격 근무 가능 여부"],
      goals: ["디자이너가 맡을 첫 과제 확인", "원격 근무 가능 여부 확인", "다음 단계 일정 확인"],
      stt_hint: "○○랩, ARR, B2B, SaaS",
    },
    sales: {
      title: "○○베이커리 김 사장님 · 영업·제안",
      counterpart: { who: "동네 빵집 3곳을 운영하는 ○○베이커리 김 사장님, 예약 챗봇 도입 상담", points: [
        "주말 예약 전화가 하루 40통 넘게 와서 직원이 빵을 못 굽는다", "지난번 다른 업체 챗봇은 엉뚱한 답을 해서 해지했다", "월 예산은 10만 원 안쪽으로 생각한다"] },
      me: { headline: "가게 정보대로만 답하는 상담 챗봇을 만드는 팀", points: [
        "가게 정보 파일에 없는 내용은 지어내지 않고 사장님께 넘긴다", "예약은 네이버 예약으로 바로 연결", "설치 하루, 첫 달 무료"] },
      talk: ["엉뚱한 답을 막는 방식", "전화 줄이는 효과를 보여 줄 숫자", "첫 달 무료로 부담 줄이기"],
      watch: ["월 8만 원 아래로는 안 됨", "다른 고객사 이름은 말하지 않기"],
      goals: ["가장 큰 불편 확인", "예산 범위 확인", "시범 사용 시작일 정하기"],
      stt_hint: "○○베이커리, 챗봇, 네이버 예약",
    },
    meeting: {
      title: "개발팀 주간 회의 · 회의",
      counterpart: { who: "개발팀 4명 주간 회의, 다음 배포 범위와 담당 정하기", points: [
        "지난주 결제 오류 2건이 남아 있다", "디자이너가 새 예약 화면 시안을 올렸다", "베트남 쪽 팀원은 영어와 베트남어를 섞어 쓴다"] },
      me: { headline: "회의를 이끌고 결정을 정리하는 팀장", points: ["배포는 매주 목요일", "결제 쪽은 보안 점검 6항목을 거쳐야 한다"] },
      talk: ["결제 오류 담당과 기한", "예약 화면 시안 반영 여부"],
      watch: ["담당자 없는 할 일이 남지 않게"],
      goals: ["결제 오류 담당 정하기", "예약 화면 반영 범위 정하기", "다음 배포일 확인"],
      stt_hint: "결제, 배포, 예약 화면",
    },
  };

  // 장면: [기다릴 ms, 할 일]
  const SCRIPT = {
    interview: {
      speakers: { 1: "박 대표", 2: "Emma (CTO)" },
      scenes: [
        [1500, { line: [1, "안녕하세요, 와 주셔서 감사해요. 저희는 B2B SaaS로 작은 가게용 예약 서비스를 만들고, 작년에 어레인기드가 30% 늘었어요."] }],
        [1800, { card: { kind: "설명", gist: "작은 가게용 예약 서비스, 작년 ARR 30% 성장", intent: "회사 상황 소개", reply: "", hints: [] },
          terms: [{ term: "ARR", heard: "어레인기드", short: "연간 반복 매출", meaning: "구독 계약을 1년 기준으로 환산한 반복 매출" }, { term: "B2B SaaS", heard: "B2B SaaS", short: "기업용 구독 서비스", meaning: "기업 고객에게 구독료를 받고 파는 온라인 서비스" }],
          numbers: [{ what: "작년 ARR 성장률", value: "30%" }], flow: ["회사 소개: 작은 가게용 예약 서비스"] }],
        [3500, { line: [1, "지원하신 이유랑, 혼자서 0에서 1로 제품을 만든 경험을 듣고 싶어요."] }],
        [1800, { card: { kind: "질문", gist: "지원 이유와 혼자 0에서 1로 만든 제품 경험은?", intent: "디자이너 1명 구조에서 혼자 끌 수 있는지 확인", reply: "○○ 때문에 지원했고, 사내 앱을 1주 만에 두 스토어에 출시한 경험이 있습니다.", hints: [{ exp: "사내 앱 1주 출시", link: "0에서 1 경험" }, { exp: "제품 10종 기획", link: "혼자 끈 경험" }] },
          flow: ["회사 소개", "지원 이유와 0→1 경험 질문"], covered: [0] }],
        [4000, { me: "네, 먼저 지원 이유부터 말씀드리면 작은 가게 사장님 문제를 직접 풀어 보고 싶었습니다." }],
        [4000, { line: [2, "How do you work with engineers when the spec keeps changing every week?"], ko: "스펙이 매주 바뀔 때 개발자와 어떻게 일하세요?" }],
        [1900, { card: { kind: "질문", gist: "스펙이 매주 바뀔 때 개발자와 일하는 방식은?", intent: "변화 속에서 협업을 유지하는 방법 확인", reply: "바뀐 부분은 그날 화면으로 다시 맞추고, 결정은 한 문서에 남깁니다.", hints: [{ exp: "디자인 토큰 140개", link: "바뀌어도 일관되게" }] },
          terms: [{ term: "스펙", heard: "spec", short: "만들 내용 명세", meaning: "무엇을 어떻게 만들지 적은 요구 사항 문서" }], flow: ["회사 소개", "0→1 경험 질문", "스펙 변경 시 협업 질문 (CTO)"] }],
        [4500, { line: [1, "좋네요. 그럼 다음 단계는 다음 주 화요일에 90분 직무 인터뷰로 잡을게요. 원격으로 해도 괜찮습니다."] }],
        [1900, { card: { kind: "결정", gist: "다음 주 화요일 90분 직무 인터뷰, 원격 가능", intent: "다음 단계 안내", reply: "네, 화요일 좋습니다. 준비할 자료가 있으면 알려 주세요.", hints: [] },
          decisions: ["다음 단계는 90분 직무 인터뷰"], actions: [{ who: "박 대표", what: "직무 인터뷰 일정 안내 메일", when: "다음 주 화요일 전" }],
          numbers: [{ what: "직무 인터뷰 시간", value: "90분" }], covered: [1, 2], flow: ["회사 소개", "0→1 경험 질문", "협업 방식 질문", "다음 단계: 화요일 직무 인터뷰"] }],
      ],
      after: {
        summary: ["박 대표가 회사(작은 가게용 예약 서비스, 작년 ARR 30% 성장)를 소개했습니다.", "지원 이유와 혼자 0에서 1로 만든 제품 경험을 물었습니다.", "CTO가 스펙이 자주 바뀔 때의 협업 방식을 물었습니다.", "다음 단계는 다음 주 화요일 90분 직무 인터뷰로, 원격으로 진행합니다."],
        decisions: ["다음 단계는 90분 직무 인터뷰(원격 가능)"], actions: [{ who: "박 대표", what: "직무 인터뷰 일정 안내 메일", when: "다음 주 화요일 전" }],
        numbers: [{ what: "작년 ARR 성장률", value: "30%" }, { what: "직무 인터뷰 시간", value: "90분" }],
        open_questions: ["디자이너가 맡을 첫 과제는 아직 구체적으로 듣지 못했습니다."],
        followup: "박 대표님, 안녕하세요.\n오늘 면접에 시간 내 주셔서 감사합니다.\n작은 가게 사장님의 예약 문제를 푸는 일이라 이야기 내내 반가웠습니다.\n말씀 주신 대로 다음 주 화요일 직무 인터뷰 준비하겠습니다.\n디자이너가 처음 맡게 될 과제를 미리 알려 주시면 그에 맞춰 준비해 가겠습니다.\n감사합니다.",
      },
    },
    sales: {
      speakers: { 1: "김 사장님", 2: "점장님" },
      scenes: [
        [1500, { line: [1, "주말엔 예약 전화가 하루 마흔 통 넘게 와요. 빵 굽다가 전화 받느라 정신이 없어요."] }],
        [1800, { card: { kind: "설명", gist: "주말 예약 전화가 하루 40통 넘어 일손이 모자람", intent: "가장 큰 불편을 털어놓음", reply: "전화 대신 챗봇이 예약을 받으면 주말 전화를 절반 넘게 줄일 수 있어요.", hints: [{ exp: "네이버 예약 바로 연결", link: "예약 전화 줄이기" }] },
          numbers: [{ what: "주말 예약 전화", value: "하루 40통 이상" }], covered: [0], flow: ["불편: 주말 예약 전화 폭주"] }],
        [4000, { line: [2, "근데 예전에 쓰던 챗봇은 없는 메뉴를 있다고 해서 손님이 화냈어요. 그런 건 안 되죠?"] }],
        [1800, { card: { kind: "반론", gist: "예전 챗봇이 없는 메뉴를 있다고 해서 문제가 됐음", intent: "엉뚱한 답에 대한 걱정", reply: "가게 정보 파일에 없는 건 지어내지 않고 사장님께 넘겨요. 그 부분은 직접 확인해 보시면 돼요.", hints: [{ exp: "모르는 건 사장님께 넘김", link: "엉뚱한 답 걱정" }] },
          terms: [{ term: "챗봇", heard: "챗봇", short: "자동 상담 프로그램", meaning: "손님 질문에 정해진 정보로 자동으로 답하는 프로그램" }], flow: ["불편: 예약 전화", "걱정: 엉뚱한 답"] }],
        [4000, { line: [1, "한 달에 오만 원이면 써 볼 만할 것 같은데요."] }],
        [1800, { card: { kind: "제안", gist: "월 5만 원이면 써 보겠다는 제안", intent: "가격 협상", reply: "첫 달은 무료로 써 보시고, 이후는 월 8만 원으로 맞춰 드릴게요.", hints: [] },
          alert: "월 8만 원 아래로는 안 된다고 정해 두셨어요", numbers: [{ what: "사장님 제안 가격", value: "월 5만 원" }], covered: [1], flow: ["불편: 예약 전화", "걱정: 엉뚱한 답", "가격: 월 5만 원 제안"] }],
      ],
      after: {
        summary: ["주말 예약 전화가 하루 40통 넘어 일손이 모자란 것이 가장 큰 불편이었습니다.", "예전 챗봇이 없는 메뉴를 안내한 경험 때문에 엉뚱한 답을 걱정했습니다.", "사장님이 월 5만 원을 제안했고, 정해 둔 하한(월 8만 원)보다 낮았습니다."],
        decisions: [], actions: [{ who: "나", what: "첫 달 무료 시범 제안서 보내기", when: "이번 주" }],
        numbers: [{ what: "주말 예약 전화", value: "하루 40통 이상" }, { what: "사장님 제안 가격", value: "월 5만 원" }],
        open_questions: ["가격 합의가 아직 안 됐습니다.", "시범 사용 시작일을 정하지 못했습니다."],
        followup: "김 사장님, 안녕하세요.\n오늘 바쁘신 중에 시간 내 주셔서 감사합니다.\n주말 예약 전화 때문에 빵 굽는 시간이 줄어드는 게 가장 큰 고민이라고 하셨지요.\n첫 달은 무료로 써 보시고 전화가 얼마나 줄었는지 숫자로 보여 드리겠습니다.\n시작하실 날짜만 알려 주시면 하루 안에 설치해 드릴게요.\n감사합니다.",
      },
    },
    meeting: {
      speakers: { 1: "민수", 2: "Linh", 3: "지은" },
      scenes: [
        [1500, { line: [1, "지난주 결제 오류 두 건 아직 남아 있어요. 이거 누가 볼지 정해야 할 것 같아요."] }],
        [1800, { card: { kind: "요청", gist: "남은 결제 오류 2건 담당 정하기", intent: "담당자 지정 요청", reply: "결제 오류는 누가, 언제까지 볼지 지금 정할까요?", hints: [] },
          numbers: [{ what: "남은 결제 오류", value: "2건" }], flow: ["결제 오류 2건 담당 논의"] }],
        [4000, { line: [2, "Mình sẽ xử lý lỗi thanh toán, chắc xong trước thứ Năm."], ko: "결제 오류는 제가 처리할게요. 목요일 전에는 끝날 것 같아요." }],
        [1800, { card: { kind: "결정", gist: "Linh이 결제 오류를 목요일 전까지 처리", intent: "담당 자청", reply: "", hints: [] },
          decisions: ["결제 오류 2건은 Linh이 맡음"], actions: [{ who: "Linh", what: "결제 오류 2건 수정", when: "목요일 전" }], covered: [0], flow: ["결제 오류: Linh, 목요일 전"] }],
        [4000, { line: [3, "새 예약 화면은 이번 배포에 넣어도 될까요? 시안은 올려 뒀어요."] }],
        [1800, { card: { kind: "질문", gist: "새 예약 화면을 이번 배포에 넣을지?", intent: "반영 범위 결정 요청", reply: "이번 배포에는 예약 화면 중 어디까지 넣을지, 누가 확인할지 정할까요?", hints: [] },
          terms: [{ term: "배포", heard: "배포", short: "실서비스 반영", meaning: "고친 내용을 실제 서비스에 올리는 일" }], flow: ["결제 오류: Linh", "예약 화면 반영 여부"] }],
      ],
      after: {
        summary: ["남은 결제 오류 2건은 Linh이 목요일 전까지 처리하기로 했습니다.", "새 예약 화면을 이번 배포에 넣을지 논의했지만 범위는 정하지 못했습니다."],
        decisions: ["결제 오류 2건은 Linh이 맡음"], actions: [{ who: "Linh", what: "결제 오류 2건 수정", when: "목요일 전" }],
        numbers: [{ what: "남은 결제 오류", value: "2건" }],
        open_questions: ["예약 화면 반영 범위와 확인 담당이 정해지지 않았습니다.", "다음 배포일을 확인하지 못했습니다."],
        followup: "팀원 여러분, 오늘 회의 정리입니다.\n1. 결제 오류 2건은 Linh이 목요일 전까지 처리합니다.\n2. 새 예약 화면 반영 범위는 내일 다시 정합니다. 지은님이 시안 기준으로 범위 안을 올려 주세요.\n3. 다음 배포일은 내일 확정해 공유하겠습니다.",
      },
    },
  };

  // ---------- 가짜 서버 ----------
  const S = { meeting: null, lines: [], speakers: {}, card: null, terms: [], flow: [], decisions: [], actions: [], numbers: [], covered: [], alerts: [], pins: [], status: "idle", last: null, run: 0 };
  let es = null;
  const emit = (msg) => { if (es && es.onmessage) es.onmessage({ data: JSON.stringify(msg) }); };
  const snapshot = () => ({ type: "state", meeting: S.meeting, speakers: S.speakers, lines: S.lines, card: S.card, terms: S.terms, flow: S.flow,
    decisions: S.decisions, actions: S.actions, numbers: S.numbers, covered: S.covered, alerts: S.alerts, status: S.status, pins: S.pins });

  class FakeEventSource {
    constructor() { es = this; setTimeout(() => { this.onopen && this.onopen(); emit(snapshot()); }, 30); }
    close() {}
  }
  window.EventSource = FakeEventSource;

  async function play(mode, run) {
    const sc = SCRIPT[mode];
    let id = 0;
    for (const [wait, act] of sc.scenes) {
      if (act.line) { emit({ type: "status", state: "them" }); }
      await sleep(wait);
      if (run !== S.run) return;
      if (act.line || act.me) {
        const l = act.me ? { id: id++, who: "me", text: act.me, t: now() } : { id: id++, who: "them", spk: act.line[0], text: act.line[1], t: now() };
        if (l.spk) {
          const k = String(l.spk);
          S.speakers[k] = S.speakers[k] || { name: sc.speakers[l.spk], segs: 0, secs: 0 };
          S.speakers[k].segs += 1; S.speakers[k].secs += Math.round(l.text.length / 4);
          emit({ type: "speakers", speakers: S.speakers });
        }
        S.lines.push(l); emit({ type: "line", line: l });
        if (act.ko) setTimeout(() => { l.ko = act.ko; emit({ type: "tr", id: l.id, ko: act.ko }); }, 900);
        if (act.line) { emit({ type: "status", state: "idle" }); setTimeout(() => emit({ type: "status", state: "thinking" }), 200); S.last = l; }
      }
      if (act.card) {
        const c = Object.assign({ alert: act.alert || "", speaker: S.last ? S.speakers[String(S.last.spk)].name : "", ms: 2400 }, act.card);
        S.card = c;
        if (act.terms) S.terms = act.terms.concat(S.terms);
        ["decisions", "actions", "numbers"].forEach((k) => { if (act[k]) S[k] = S[k].concat(act[k]); });
        if (act.flow) S.flow = act.flow;
        if (act.covered) S.covered = Array.from(new Set(S.covered.concat(act.covered)));
        if (act.alert) S.alerts.push({ t: now().slice(0, 5), text: act.alert });
        emit({ type: "card", card: c, terms: S.terms, flow: S.flow, decisions: S.decisions, actions: S.actions, numbers: S.numbers, covered: S.covered, alerts: S.alerts });
        emit({ type: "status", state: "idle" });
      }
    }
  }

  const json = (data, status = 200) => Promise.resolve(new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } }));
  const realFetch = window.fetch.bind(window);
  window.fetch = async (url, opts = {}) => {
    const path = String(url).split("?")[0];
    if (!path.startsWith("/api/")) return realFetch(url, opts);
    const body = opts.body ? JSON.parse(opts.body) : {};
    if (path === "/api/state") {
      return json({ provider: "claude", has_key: true, profile: { text: "", pdf_name: "예시-이력서.pdf" }, meeting: S.meeting, lan: "", meetings: [],
        providers: { claude: { name: "Claude", keys: "https://platform.claude.com/", has_key: true }, openai: { name: "ChatGPT", keys: "https://platform.openai.com/api-keys", has_key: false }, gemini: { name: "Gemini", keys: "https://aistudio.google.com/apikey", has_key: false } } });
    }
    if (path === "/api/settings" || path === "/api/profile") return json({ ok: true });
    if (path === "/api/prepare") { await sleep(2600); return json(JSON.parse(JSON.stringify(PREP[body.mode] || PREP.interview))); }
    if (path === "/api/pdf") return json({ error: "데모에서는 PDF를 만들지 않아요. 맥에 설치하면 바로 저장돼요." }, 400);
    if (path === "/api/pin") { S.pins = body.pins || []; emit({ type: "pins", pins: S.pins }); return json({ ok: true }); }
    if (path === "/api/speaker") {
      if (S.speakers[body.id] && body.name) { S.speakers[body.id].name = body.name; emit({ type: "speakers", speakers: S.speakers }); }
      return json({ ok: true });
    }
    if (path === "/api/start") {
      const mode = SCRIPT[body.mode] ? body.mode : "interview";
      Object.assign(S, { lines: [], speakers: {}, card: null, terms: [], flow: [], decisions: [], actions: [], numbers: [], covered: [], alerts: [], pins: [], last: null, run: S.run + 1 });
      S.meeting = { id: "demo-" + Date.now(), mode, title: body.title || PREP[mode].title, goals: (body.goals || []).filter((g) => g && g.trim()), started: Date.now() / 1000, minutes: Number(body.minutes) || 0, prep: body.prep || null };
      if (!S.meeting.goals.length) S.meeting.goals = PREP[mode].goals;
      emit(snapshot());
      play(mode, S.run);
      return json({ id: S.meeting.id });
    }
    if (path === "/api/stop") {
      const m = S.meeting; S.run += 1; emit({ type: "status", state: "wrapping" }); await sleep(2200);
      const a = Object.assign({}, SCRIPT[m.mode].after, { goals: m.goals.map((g, i) => ({ text: g, done: S.covered.includes(i) })), pins: S.pins, ended: new Date().toLocaleString("ko-KR") });
      S.meeting = null; emit(snapshot());
      return json({ id: m.id, after: a });
    }
    return json({ error: "데모에서는 쓸 수 없는 기능이에요" }, 404);
  };

  // ---------- 데모 안내 (준비 화면 맨 위에 한 줄) ----------
  document.addEventListener("DOMContentLoaded", () => {
    const bar = document.createElement("div");
    bar.className = "demobar";
    bar.innerHTML = '데모 화면이에요. 실제 받아쓰기 대신 예시 미팅을 재생해요. 미팅 종류를 고르고 "준비 자료 만들기", "미팅 시작"을 차례로 눌러 보세요. <a href="https://github.com/johndefine404/meeting-meo" target="_blank" rel="noopener">맥에 설치하기</a> <span class="demoby">· 만든 곳 <a href="https://define404.com" target="_blank" rel="noopener">Define404</a></span>';
    const brand = document.querySelector("#prep .brand");
    brand.insertAdjacentElement("afterend", bar);
    const st = document.createElement("style");
    st.textContent = ".demobar{background:#2a2410;color:#ffe7a3;border:1px solid #6b5a1e;border-radius:12px;padding:10px 14px;font-size:13.5px;line-height:1.55;margin:0 0 12px;word-break:keep-all}.demobar a{color:#ffc61a;margin-left:4px}.demobar .demoby{white-space:nowrap}";
    document.head.appendChild(st);
  });
})();
