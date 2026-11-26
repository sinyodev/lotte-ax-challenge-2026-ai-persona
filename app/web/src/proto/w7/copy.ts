/**
 * W7 UX 시안(/proto/w7)의 화면 글. 장면마다 칠성이의 말(chat), 작업대의 글(bench), 버튼(cta)이 있다.
 * "임시"가 붙은 것은 설계안에 없어 시안을 만들며 넣은 문구다.
 */
import type { MethodId, PersonId, QuestionId } from "./data"

const won = (n: number) => `${n.toLocaleString("ko-KR")}원`

export const w7 = {
  page: {
    restart: "처음부터 다시",
    prototype: "시안", // 임시
    stepperLabel: "장면", // 임시
    chatLabel: "칠성이와의 대화",
    placeholder: "칠성이에게 말하기",
    composerNote: "시안에서는 입력이 전달되지 않아요", // 임시
  },
  /** 위 단계 표시줄의 다섯 장면 */
  steps: ["컨셉 진단", "테스트 결과", "소비자 인터뷰", "인터뷰 결론", "개선안 테스트"],
  /** 장면이 속한 앱의 단계(표시줄 왼쪽, 작업대 제목) */
  stageOf: ["컨셉 보드", "테스트 결과", "테스트 결과", "테스트 결과", "개선안 테스트"],
  source: { provided: "제공 자료 집계", demo: "시연용 응답" },
  mark: { flag: "걸림", ok: "괜찮음" },

  /* ───── A ───── */
  a: {
    start: "테스트 전에 볼 자료를 확인하고 있어요.",
    choose: "원래 안과 가격을 고친 안을 각각 보여줄 수 있어요. 어떤 안을 테스트할까요?",
    original: "원래 안을 가상 매대에 올려 볼까요?",
    skipped: "진단을 건너뛰었어요",
  },

  /* ───── B ───── */
  b: {
    chat: (total: number, picked: number) =>
      `가상 소비자 ${total}명 중 ${picked}명이 밀키스 화채를 골랐어요. 결과에서 갈리는 곳이 세 군데 보여요. 직접 물어볼까요? 질문 하나와 방식을 골라 주세요.`,
    cta: "이 질문으로 인터뷰 열기",
    needPick: "질문과 방식을 고르면 열 수 있어요",
    resultTitle: "매대 테스트 결과",
    picked: (total: number, picked: number) => `가상 소비자 ${total}명 중 ${picked}명이 골랐어요`,
    original: "원래 안 1,800원",
    fixed: "가격을 고친 안",
    rank: (r: number, n: number) => `${n}개 중 ${r}위`,
    from: "고른 사람이 평소 고르던 것",
    fromOwn: "자사 제품",
    fromRival: "다른 회사 제품",
    fromNone: "평소 안 삼",
    people: (n: number) => `${n}명`,
    askTitle: "더 물어볼 곳",
    questions: {
      "q-fizz": { q: "‘화채’라는 이름의 탄산음료, 손이 가나요?", basis: "지나친 81명 중 29명이 ‘화채인데 탄산이라 어색하다’고 답했어요" },
      "q-price": { q: "1,800원이면 손이 가나요?", basis: "지나친 81명 중 18명이 가격을 걸린 점으로 꼽았어요" },
      "q-season": { q: "여름 한정이라서 더 사고 싶어지나요, 망설여지나요?", basis: "고른 39명 중 14명이 ‘한정이라서’를 이유로 꼽았어요" },
      "q-own": { q: "평소 밀키스를 마시던 사람은 왜 이걸 골랐나요?", basis: "고른 39명 중 11명이 평소 자사 제품을 고르던 사람이에요" },
    } satisfies Record<QuestionId, { q: string; basis: string }>,
    methodTitle: "물어보는 방식",
    methods: {
      one: { name: "한 명 인터뷰", when: "한 사람의 이유를 끝까지 들어요" },
      fgi: { name: "FGI(집단 심층 인터뷰)", when: "여러 사람에게 같은 질문을 따로 물어요. 서로의 답을 보지 않아요" },
      fgd: { name: "FGD(집단 토론)", when: "의견이 갈리는 주제를 서로 부딪쳐 봐요" },
    } satisfies Record<MethodId, { name: string; when: string }>,
    notReady: "시안에는 없어요", // 임시
    planner: (q: string, m: string) => `${m}로 물어볼게요: ${q}`,
  },

  /* ───── C ───── */
  c: {
    chat: {
      fgi: "고른 사람 셋, 지나친 사람 셋으로 여섯 명을 모셨어요. 여섯 명에게 같은 질문을 따로 물었어요. 서로의 답은 보지 않았어요.",
      fgd: "고른 사람 셋, 지나친 사람 셋으로 여섯 명을 모셨어요. 1차는 각자 답했고, 2차부터 서로의 말을 읽고 답했어요.",
    },
    cta: "결론 보기",
    question: "질문",
    noScript: "시안에는 첫 번째 질문의 발언만 들어 있어요", // 임시
    honesty: "가상 소비자의 발언이에요. 출시 전 제품이라 맛을 본 것처럼 말하지 않아요.",
    play: "재생",
    pause: "멈춤",
    replay: "처음부터 재생",
    idle: "재생을 누르면 첫 발언부터 들려 드려요",
    progressFgi: (cur: number, total: number) => `${cur}/${total}명`,
    roundsFgd: ["1차 각자", "2차 서로", "정리"],
    picked: "고름",
    passed: "지나침",
    usual: (name: string, isOwn: boolean) => `평소 ${name}(${isOwn ? "자사" : "다른 회사"})`,
    host: "칠성이",
    hostRole: "진행",
    changed: "바뀜",
    waiting: "대기",
    agree: "동의",
    rebut: "반박",
    to: (label: string, stance: string) => `${label}에게 ${stance}`,
    participants: "참석자",
    transcript: "발언",
    sceneLabel: { fgi: "칠성이와 참석자 한 명이 마주 앉은 인터뷰 자리", fgd: "여섯 명이 원탁에 둘러앉은 토론 자리" },
    planner: "결론 보기",
  },

  /* ───── D ───── */
  d: {
    chat: {
      fgi: "여섯 명 중 네 명이 ‘화채’라는 이름에서 탄산이 없는 음료를 떠올렸어요. 지나친 세 명 중 두 명도 이 얘기를 했어요. 결론을 펼쳐 근거 발언을 하나 골라 주세요. 그 발언으로 개선안을 만들게요.",
      fgd: "여섯 명 중 네 명이 ‘화채’라는 이름에서 탄산이 없는 음료를 떠올렸어요. 지나친 세 명 중 두 명도 이 얘기를 했고, 2차에서 한 명이 생각을 바꿨어요. 결론을 펼쳐 근거 발언을 하나 골라 주세요. 그 발언으로 개선안을 만들게요.",
    },
    cta: "이 발언으로 개선안 만들기",
    needPick: "근거 발언을 하나 골라 주세요",
    groups: { agreed: "모인 의견", split: "갈린 의견", changed: "생각이 바뀐 사람" },
    count: (n: number) => `여섯 명 중 ${n}명`,
    round: (r: number) => (r === 3 ? "정리" : `${r}차`),
    fullOpen: "전체 기록 보기",
    fullClose: "전체 기록 닫기",
    filterAll: "모두",
    filterPicked: "고른 사람",
    filterPassed: "지나친 사람",
    planner: "이 발언으로 개선안 만들기",
  },

  /* ───── E ───── */
  e: {
    chat: (total: number, a: number, b: number, gained: number, lost: number) =>
      `같은 가상 소비자 ${total}명 중 원래 안은 ${a}명, 무탄산 안은 ${b}명이 골랐어요. 무탄산으로 바꾸자 ${gained}명이 새로 골랐고, 원래 고르던 ${lost}명은 지나쳤어요. 이 안을 채택할까요?`,
    unclear: "차이가 있다고 말하기 어려워요.",
    cta: "이 안 채택",
    title: "원래 안과 무탄산 안",
    verdict: { better: "나아짐", unclear: "차이를 말하기 어려움", worse: "나빠짐" },
    headline: (total: number, a: number, b: number, gained: number, lost: number) =>
      `같은 가상 소비자 ${total}명 중 원래 안은 ${a}명, 무탄산 안은 ${b}명이 골랐어요. 무탄산으로 바꾸자 ${gained}명이 새로 골랐고, 원래 고르던 ${lost}명은 지나쳤어요`,
    segments: { both: "둘 다 고름", gained: "새로 고름", lost: "고르다 지나침", neither: "둘 다 지나침" },
    net: (v: number, a: number, b: number) => `늘어난 사람 ${v}명 (범위 ${a}~${b}명)`,
    countsTitle: "고른 사람",
    originalName: "원래 안 탄산",
    changedName: "무탄산 안",
    of: (total: number, n: number) => `${total}명 중 ${n}명`,
    range: (a: number, b: number) => `범위 ${a}~${b}명`,
    whoTitle: (n: number) => `새로 고른 ${n}명`,
    usualTitle: "평소 고르던 제품",
    own: "자사",
    rival: "다른 회사",
    lostNote: (n: number, own: number, rival: number) => `고르다 지나친 ${n}명은 자사 ${own}명, 다른 회사 ${rival}명이었어요`, // 임시
    basisTitle: "이 안이 나온 근거",
    hypothesis: "가설",
    hypothesisText: "‘화채’라는 이름은 탄산이 없는 음료를 떠올리게 해서, 탄산이 고르지 않는 이유가 돼요.",
    evidence: "근거",
    evidenceCount: (n: number, of: number) => `매대 테스트에서 지나친 ${of}명 중 ${n}명이 같은 이유를 댔어요`,
    changeOne: "바꿀 것 하나",
    changeLine: (from: string, to: string) => `제형 ${from} → ${to}`,
    keepLine: "이름, 용량, 가격, 판매 방식은 그대로예요", // 임시
    quoteBy: (label: string, round: string, picked: string) => `${label}, ${round}, ${picked}`,
    planner: "이 안 채택",
  },

  /* ───── E 채택 뒤 ───── */
  adopted: {
    chat: "컨셉 보드의 제형을 무탄산으로 바꾸고, 왜 바꿨는지 기록을 남겼어요. 결과 보고서의 개선안 구역에도 실었어요. 보고서로 갈까요, 다른 안도 볼까요?",
    toReport: "결과 보고서로",
    other: "다른 안도 보기",
    reportNote: "시안은 여기까지예요", // 임시
    title: "컨셉 보드",
    spec: { name: "이름", flavor: "맛", form: "제형", pack: "용량", price: "가격", sale: "판매" },
    changedMark: "바뀜",
    specChange: (from: string, to: string) => `${from} → ${to}`,
    logTitle: "바꾼 기록",
    logWhat: (from: string, to: string) => `제형 ${from} → ${to}`,
    logWhy: (gained: number, lost: number, total: number) =>
      `개선안 테스트에서 같은 가상 소비자 ${total}명 중 ${gained}명이 새로 고르고 ${lost}명이 지나쳤어요`,
    logQuote: (by: string) => `근거 발언: ${by}`,
  },

  personLabel: (p: { age: number; gender: string; job: string }) => `${p.age}세 ${p.gender}, ${p.job}`,
  personShort: (id: PersonId) => id.replace("p", ""),
  won,
}
