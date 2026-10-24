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
      interview: {
        message: "작은 가게 사장님 문제를 혼자서 기획부터 출시까지 끝내 본 디자이너",
        criteria: ["0에서 1 실행력", "개발자와의 협업", "작은 가게 고객 이해", "원격 협업 신뢰", "디자인 체계 수립"],
        answers: [
          { qtype: "자기소개", question: "간단히 자기소개 부탁드려요.", cue: "기획부터 출시 · 제품 10종 · 스토어 4종", answer: "프로덕트 디자이너로 기획부터 출시까지 직접 끝내는 일을 해 왔습니다. 자사 제품 10종을 기획하고 디자인했고, 그중 4종을 스토어에 출시했습니다. 최근에는 사내 출퇴근 앱을 1주 만에 두 스토어에 동시에 출시했습니다.", facts: ["자사 제품 10종 기획·디자인", "4종 스토어 출시", "사내 출퇴근 앱 1주 출시"], gaps: "", dont: "" },
          { qtype: "지원 동기", question: "왜 저희 회사에 지원하셨나요?", cue: "작은 가게 · 직접 풀기 · 예약 흐름", answer: "작은 가게 사장님이 겪는 예약 문제를 직접 풀어 보고 싶었습니다. 고객 인터뷰 20회로 예약 흐름을 다시 설계한 경험이 있어서, ○○랩의 예약·고객 관리 서비스에서 바로 도움이 될 수 있다고 생각했습니다.", facts: ["고객 인터뷰 20회로 예약 흐름 재설계"], gaps: "○○랩 서비스를 직접 써 본 느낌", dont: "" },
          { qtype: "성공 경험", question: "혼자서 0에서 1로 제품을 만든 경험을 들려주세요.", cue: "1주 · 두 스토어 · 혼자 기획", answer: "사내 출퇴근 앱을 1주 만에 앱스토어와 플레이스토어에 동시에 출시했습니다. 기획과 화면 설계를 제가 맡고, 개발자와 매일 같은 날 화면을 맞췄습니다. 결과는 ○○ 같은 숫자로 말씀드릴 수 있게 정리해 가겠습니다.", facts: ["사내 출퇴근 앱 1주 출시", "앱스토어·플레이스토어 동시 출시"], gaps: "출시 후 사용자 수 같은 결과 숫자", dont: "" },
          { qtype: "갈등·협업", question: "스펙이 매주 바뀔 때 개발자와 어떻게 일하세요?", cue: "그날 화면 · 한 문서 · 토큰 140개", answer: "바뀐 부분은 그날 화면으로 다시 맞추고, 결정은 한 문서에 남깁니다. 디자인 토큰 140개를 만들어 두어서 스펙이 바뀌어도 화면이 일관되게 유지됩니다.", facts: ["디자인 토큰 140개로 디자인 체계 수립"], gaps: "", dont: "" },
          { qtype: "강점", question: "본인의 가장 큰 강점은 무엇인가요?", cue: "끝까지 · 직접 · 고객 목소리", answer: "기획부터 출시까지 혼자서도 끝까지 가져가는 점입니다. 고객 인터뷰 20회를 직접 하고 그 결과를 화면에 반영해 본 경험이 그 근거입니다.", facts: ["고객 인터뷰 20회"], gaps: "", dont: "" },
        ],
        risks: [
          { qtype: "약점", question: "디자이너가 1명뿐이라 업무 범위가 넓은데, 부담되지 않으세요?", cue: "범위 확인 · 우선순위 · 같이 정하기", answer: "범위가 넓은 만큼 처음 3개월에 무엇을 먼저 할지 같이 정하고 싶습니다. 이전에도 제품 10종을 혼자 기획·디자인하며 우선순위를 정해 온 경험이 있습니다.", facts: ["자사 제품 10종 기획·디자인"], gaps: "", dont: "야근이 많아도 괜찮다는 식의 무리한 약속" },
          { qtype: "이직 사유", question: "지금 회사를 떠나려는 이유는 무엇인가요?", cue: "더 큰 문제 · 고객과 가까이", answer: "지금 일에서 배운 것을 더 많은 사장님 고객에게 직접 닿는 제품에 쓰고 싶어서입니다. 현재 회사나 동료에 대한 불만은 이유가 아닙니다.", facts: [], gaps: "", dont: "전 직장이나 동료 험담, 구체적인 내부 사정" },
        ],
        ask: ["디자이너가 처음 맡게 될 과제는 무엇인가요?", "개발자와 화면을 맞추는 주기와 방식이 궁금합니다.", "원격 근무는 어느 정도 가능한가요?", "입사 후 3개월 동안 기대하시는 결과는 무엇인가요?"],
        dont: ["이전 회사의 내부 숫자나 고객 이름", "희망 연봉을 먼저 숫자로 말하기", "확인되지 않은 성과 숫자"],
        timeplan: ["자기소개 2분", "경험 질문 15분", "협업 방식 질문 8분", "내가 물어볼 질문 5분"],
      },
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
        [1800, { card: { card: 1, qtype: "지원 동기", kind: "질문", gist: "지원 이유와 혼자 0에서 1로 만든 제품 경험은?", intent: "디자이너 1명 구조에서 혼자 끌 수 있는지 확인", reply: "작은 가게 사장님 문제를 직접 풀고 싶어 지원했고, 사내 앱을 1주 만에 두 스토어에 출시한 경험이 있습니다.", hints: [{ exp: "사내 앱 1주 출시", link: "0에서 1 경험" }, { exp: "제품 10종 기획", link: "혼자 끈 경험" }] },
          flow: ["회사 소개", "지원 이유와 0→1 경험 질문"], covered: [0] }],
        [4000, { me: "네, 먼저 지원 이유부터 말씀드리면 작은 가게 사장님 문제를 직접 풀어 보고 싶었습니다." }],
        [4000, { line: [2, "How do you work with engineers when the spec keeps changing every week?"], ko: "스펙이 매주 바뀔 때 개발자와 어떻게 일하세요?" }],
        [1900, { card: { card: 3, qtype: "갈등·협업", kind: "질문", gist: "스펙이 매주 바뀔 때 개발자와 일하는 방식은?", intent: "변화 속에서 협업을 유지하는 방법 확인", reply: "바뀐 부분은 그날 화면으로 다시 맞추고, 결정은 한 문서에 남깁니다.", hints: [{ exp: "디자인 토큰 140개", link: "바뀌어도 일관되게" }] },
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
        debrief: {
          scores: [{ name: "0에서 1 실행력", score: 4, why: "1주 출시 사례를 숫자와 함께 말함" }, { name: "개발자와의 협업", score: 4, why: "그날 화면으로 맞추는 방식을 구체적으로 말함" }, { name: "작은 가게 고객 이해", score: 3, why: "사장님 문제 이야기는 했지만 인터뷰 사례는 못 꺼냄" }, { name: "원격 협업 신뢰", score: 2, why: "원격 근무 관련 경험은 말하지 못함" }],
          answers: [
            { question: "지원 이유와 혼자서 0에서 1로 만든 제품 경험", qtype: "지원 동기", mine: "작은 가게 사장님 문제를 풀고 싶다고 답했고, 사례는 짧게만 말함", verdict: "보통", better: "작은 가게 사장님이 겪는 예약 문제를 직접 풀고 싶어 지원했습니다. 사내 출퇴근 앱을 1주 만에 두 스토어에 출시했고, 고객 인터뷰 20회로 예약 흐름을 다시 설계한 경험이 ○○랩에서 바로 쓰일 거라고 생각합니다.", cue: "사장님 문제 · 1주 출시 · 인터뷰 20회" },
            { question: "스펙이 매주 바뀔 때 개발자와 일하는 방식", qtype: "갈등·협업", mine: "바뀐 부분은 그날 화면으로 맞춘다고 답함", verdict: "좋음", better: "바뀐 부분은 그날 화면으로 다시 맞추고, 결정은 한 문서에 남깁니다. 디자인 토큰 140개가 있어서 바뀌어도 화면이 일관됩니다.", cue: "그날 화면 · 한 문서 · 토큰 140개" },
            { question: "원격 근무 가능 여부와 일하는 방식", qtype: "근무 형태", mine: "원격으로 직무 인터뷰를 해도 된다는 말에 바로 동의함", verdict: "아쉬움", better: "원격으로 진행해도 좋습니다. 원격에서도 개발자와 매일 같은 화면을 보며 맞추는 방식을 써 왔고, 입사 후 근무 방식은 팀 기준에 맞추겠습니다.", cue: "원격 가능 · 같은 화면 · 팀 기준" },
          ],
          went_well: ["1주 출시 사례를 숫자로 말해서 설득력이 있었다", "협업 방식을 한 문장으로 분명하게 답했다"],
          to_fix: ["고객 인터뷰 20회 사례를 꺼내지 못했다", "원격 근무 경험 질문에는 근거 없이 짧게 답했다", "마지막에 내가 물어볼 질문을 하지 못했다"],
          lessons: ["지원 동기 답에는 항상 내 경험 숫자 하나를 붙인다", "원격 근무 질문이 올 것에 대비해 원격 협업 사례를 하나 준비한다", "마지막 질문 시간에 물어볼 것 두 개를 미리 정해 둔다"],
          signals: ["CTO가 협업 방식에 오래 관심을 보였다", "대표가 디자이너 1명 구조에 대한 우려를 두 번 언급했다"],
        },
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

  // ---------- 면접 기록장 · 연습 (이 탭 안에서만 저장) ----------
  const iv = PREP.interview.interview;
  let bid = 0;
  const stamp = () => { const d = new Date(), z = (n) => String(n).padStart(2, "0"); return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())} ${z(d.getHours())}:${z(d.getMinutes())}`; };
  const bank = {
    answers: [
      { id: "b1", qtype: "자기소개", question: "간단히 자기소개 부탁드려요.", cue: "기획부터 출시 · 제품 10종 · 스토어 4종", answer: iv.answers[0].answer, facts: iv.answers[0].facts, gaps: "", dont: "", company: "", source: "연습", updated: "2026-10-12 21:40", scores: [{ date: "2026-10-10", total: 62 }, { date: "2026-10-12", total: 78 }] },
      { id: "b2", qtype: "갈등·협업", question: "개발자와 의견이 갈렸을 때 어떻게 푸셨나요?", cue: "사용자 근거 · 작은 시안 · 같이 결정", answer: "개발 일정 때문에 화면 범위를 두고 의견이 갈린 적이 있습니다. 사용자 인터뷰 근거를 보여 드리고, 가장 작은 시안부터 같이 만들어 보며 함께 정했습니다.", facts: ["고객 인터뷰 20회"], gaps: "", dont: "", company: "", source: "복기", updated: "2026-10-17 15:20", scores: [{ date: "2026-10-17", total: 71 }] },
      { id: "b3", qtype: "마지막 한마디", question: "마지막으로 하고 싶은 말씀 있으세요?", cue: "관심 · 첫 과제 · 감사", answer: "오늘 이야기를 들으며 이 일을 더 하고 싶어졌습니다. 첫 과제가 무엇일지 기대되고, 시간 내 주셔서 감사합니다.", facts: [], gaps: "", dont: "", company: "△△스튜디오", source: "준비", updated: "2026-10-09 10:05", scores: [] },
    ],
    lessons: [{ text: "답은 결론부터 한 문장으로 시작한다", date: "2026-10-12", from: "연습" }, { text: "마지막 질문 시간에 물어볼 것 두 개를 미리 정해 둔다", date: "2026-10-17", from: "△△스튜디오 · 면접" }],
    history: [{ id: "20261017-143000", company: "△△스튜디오 · 면접", date: "20261017", result: "다음 단계" }],
  };
  const pastAfter = () => Object.assign({}, SCRIPT.interview.after, { goals: PREP.interview.goals.map((g, i) => ({ text: g, done: i !== 1 })), pins: [], ended: "2026. 10. 17. 오후 3:10:00", carried: true });
  const doneAfter = {};
  function bankUpsert(item, source, company) {
    const q = (item.question || "").trim();
    if (!q && !(item.answer || "").trim()) return null;
    const single = ["자기소개", "지원 동기", "이직 사유", "강점", "약점", "처우", "입사 시기", "근무 형태", "마지막 한마디"];
    const companyQ = ["지원 동기", "마지막 한마디"];
    const co = (item.company || company || "").trim().slice(0, 40);
    const same = (a) => !companyQ.includes(item.qtype) || (a.company || "") === co;
    let hit = item.id ? bank.answers.find((a) => a.id === item.id)
      : (bank.answers.find((a) => a.question.trim() === q && same(a)) || bank.answers.find((a) => single.includes(item.qtype) && a.qtype === item.qtype && same(a)));
    if (!hit) { hit = { id: "n" + (++bid), scores: [], company: companyQ.includes(item.qtype) ? co : "", facts: [], gaps: "", dont: "", cue: "" }; bank.answers.push(hit); }
    ["qtype", "question", "answer", "cue", "gaps", "dont"].forEach((k) => { if ((item[k] || "").trim()) hit[k] = item[k].trim(); });
    if ((item.facts || []).length) hit.facts = item.facts.slice(0, 5);
    hit.source = source; hit.updated = stamp();
    return hit;
  }
  function bankOp(b) {
    if (b.op === "upsert") { const saved = (b.answers || []).map((x) => bankUpsert(x, b.source || "준비", b.company || "")).filter(Boolean); return { ok: true, saved: saved.length, bank }; }
    if (b.op === "delete") bank.answers = bank.answers.filter((a) => a.id !== b.id);
    else if (b.op === "edit") bank.answers.forEach((a) => { if (a.id === b.id) { ["question", "answer", "cue"].forEach((k) => { if (k in b) a[k] = String(b[k]).trim(); }); a.updated = stamp(); } });
    else if (b.op === "score") bank.answers.forEach((a) => { if (a.id === b.id) a.scores = (a.scores || []).concat({ date: stamp().slice(0, 10), total: Number(b.total) || 0 }).slice(-10); });
    else if (b.op === "lesson_delete") { if (b.index >= 0 && b.index < bank.lessons.length) bank.lessons.splice(b.index, 1); }
    else if (b.op === "result") bank.history.forEach((h) => { if (h.id === b.id) h.result = String(b.result || "대기").slice(0, 20); });
    else if (b.op === "carry") {
      const e = doneAfter[b.id]; if (!e || !e.after.debrief) throw new Error("가져갈 면접 정리가 없어요");
      const picks = new Set(b.picks || []);
      e.after.debrief.answers.forEach((x, i) => { if (picks.has(i) && x.better) bankUpsert({ qtype: x.qtype, question: x.question, answer: x.better, cue: x.cue }, "복기", (e.title || "").split(" · ")[0]); });
      e.after.debrief.lessons.forEach((t) => { if (!bank.lessons.some((l) => l.text === t)) bank.lessons.push({ text: t, date: stamp().slice(0, 10), from: e.title }); });
      if (!bank.history.some((h) => h.id === b.id)) bank.history.unshift({ id: b.id, company: e.title, date: new Date().toISOString().slice(0, 10).replace(/-/g, ""), result: "대기" });
      e.after.carried = true;
    } else throw new Error("알 수 없는 요청이에요");
    return { ok: true, bank };
  }
  // 채점 흉내: AI 대신 답의 길이와 숫자 유무로 점수를 조금씩 다르게 준다
  function fakeScore(b) {
    const ans = (b.answer || "").trim();
    if (ans.length < 5) throw new Error("답이 너무 짧아요. 한두 문장 이상 말하거나 적어 주세요.");
    const ref = [...iv.answers, ...iv.risks].find((a) => a.question === b.question);
    const hasNum = /\d/.test(ans), long = ans.length > 60, sec = Number(b.secs) || 0;
    const sc = [
      { name: "결론 먼저", score: ans.length > 20 ? 4 : 3, why: ans.length > 20 ? "첫 문장에서 질문에 바로 답했어요" : "첫 문장에 결론을 먼저 두면 더 좋아요" },
      { name: "구체성", score: hasNum ? 5 : long ? 3 : 2, why: hasNum ? "숫자와 사례가 들어 있어요" : "내 경험의 숫자나 사례가 하나 더 필요해요" },
      { name: "질문 적합", score: long ? 4 : 3, why: long ? "묻는 것에 맞게 답했어요" : "회사·직무와 이어지는 말을 더하면 좋아요" },
      { name: "위험 관리", score: 4, why: "말하지 않을 것을 건드리지 않았어요" },
    ];
    let total = sc.reduce((a, x) => a + x.score * 5, 0) + (long ? 6 : 0) + (hasNum ? 4 : 0);
    if (sec > 120) total -= 8;
    total = Math.max(30, Math.min(96, total));
    const good = [], fix = [];
    if (hasNum) good.push("숫자로 말해서 믿음이 갔어요"); else fix.push("경험에 숫자 하나를 붙여 보세요 (예: 1주, 20회)");
    if (long) good.push("답의 길이가 적당해요"); else fix.push("두세 문장으로 이유까지 이어 말해 보세요");
    good.push("말하지 않을 것을 피했어요");
    if (sec > 120) fix.push("2분이 넘었어요. 핵심어 세 개만 남기고 줄여 보세요");
    return { scores: sc, total, good, fix,
      better: ref ? ref.answer : (b.ref || "먼저 결론을 한 문장으로 말하고, 이어서 내 경험 하나를 숫자와 함께 말씀드립니다. 마지막으로 이 회사에서 어떻게 쓸지로 맺습니다."),
      cue: ref ? ref.cue : "결론 · 경험 숫자 · 회사와 연결",
      followup_q: ref && ref.qtype === "지원 동기" ? "저희 서비스에서 가장 먼저 바꾸고 싶은 화면은 무엇인가요?" : "그때 가장 어려웠던 점은 무엇이었고 어떻게 넘기셨나요?" };
  }

  const json = (data, status = 200) => Promise.resolve(new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } }));
  const realFetch = window.fetch.bind(window);
  window.fetch = async (url, opts = {}) => {
    const path = String(url).split("?")[0];
    if (!path.startsWith("/api/")) return realFetch(url, opts);
    const body = opts.body ? JSON.parse(opts.body) : {};
    if (path === "/api/state") {
      return json({ provider: "claude", has_key: true, profile: { text: "", pdf_name: "예시-이력서.pdf" }, meeting: S.meeting, lan: "", meetings: [{ id: "20261017-143000", mode: "interview", title: "△△스튜디오 · 면접" }],
        providers: { claude: { name: "Claude", keys: "https://platform.claude.com/", has_key: true }, openai: { name: "ChatGPT", keys: "https://platform.openai.com/api-keys", has_key: false }, gemini: { name: "Gemini", keys: "https://aistudio.google.com/apikey", has_key: false } } });
    }
    if (path === "/api/bank") {
      if (opts.method !== "POST") return json(bank);
      try { return json(bankOp(body)); } catch (e) { return json({ error: e.message }, 400); }
    }
    if (path === "/api/rehearse") {
      await sleep(1800);
      try { return json(fakeScore(body)); } catch (e) { return json({ error: e.message }, 400); }
    }
    if (path === "/api/transcribe") { await sleep(900); return json({ text: "작은 가게 사장님 문제를 직접 풀고 싶어서 지원했습니다. 사내 앱을 1주 만에 두 스토어에 출시한 경험이 있습니다.", secs: 12 }); }
    const mm = path.match(/^\/api\/meetings\/([\w-]+)$/);
    if (mm) {
      const id = mm[1];
      if (doneAfter[id]) return json({ meeting: { id, mode: doneAfter[id].mode, title: doneAfter[id].title }, after: doneAfter[id].after });
      if (id === "20261017-143000") return json({ meeting: { id, mode: "interview", title: "△△스튜디오 · 면접" }, after: pastAfter() });
      return json({ meeting: null, after: null });
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
      const kit = S.meeting.prep && S.meeting.prep.interview;
      if (mode === "interview" && kit) S.meeting.cards = [...(kit.answers || []).map((a) => Object.assign({}, a, { risk: false })), ...(kit.risks || []).map((a) => Object.assign({}, a, { risk: true }))]
        .filter((c) => c.question).map((c) => ({ qtype: c.qtype, question: c.question, answer: c.answer, cue: c.cue, dont: c.dont || "", risk: c.risk }));
      emit(snapshot());
      play(mode, S.run);
      return json({ id: S.meeting.id });
    }
    if (path === "/api/stop") {
      const m = S.meeting; S.run += 1; emit({ type: "status", state: "wrapping" }); await sleep(2200);
      const a = Object.assign({}, SCRIPT[m.mode].after, { goals: m.goals.map((g, i) => ({ text: g, done: S.covered.includes(i) })), pins: S.pins, ended: new Date().toLocaleString("ko-KR") });
      S.meeting = null; emit(snapshot());
      doneAfter[m.id] = { mode: m.mode, title: m.title, after: a };
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
