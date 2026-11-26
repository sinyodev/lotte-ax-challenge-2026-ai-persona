/**
 * 화면에 보이는 글을 모두 여기에 둔다. 부품 안에 한글 문장을 직접 적지 않는다.
 * "임시" 표시가 붙은 문구는 지시서에 없어 구현 세션이 넣은 것이다. 설계 세션이 확정한다.
 */

export const STAGES = [
  "아이디어 회의",
  "컨셉 보드",
  "컨셉 보드 분석",
  "매대 테스트",
  "테스트 결과",
  "개선안 테스트",
  "결과 보고서",
  "후속 개선",
] as const

export type StageName = (typeof STAGES)[number]

/** 일의 두 부분(약속 v1.1). 단계는 contract.ts의 PART_STAGES. */
export const PARTS = {
  concept: "컨셉 기획",
  test: "매대 테스트",
} as const

/**
 * 카드 제목 옆의 작은 이름표(약속 v1.3). 칠성이가 낸 카드("suggestion")에만 붙인다.
 * 찾아본 것의 항목에는 우리 분류 대신 출처의 이름(source)이 붙는다.
 */
export const ORIGIN_LABELS: Partial<Record<string, string>> = {
  suggestion: "칠성이의 제안",
}

/** 받침이 있으면 "은", 없으면 "는". 한글과 숫자로 끝나는 이름만 가리고, 나머지는 "은"으로 둔다. */
function eunNeun(name: string) {
  const ch = name.trim().slice(-1)
  const code = ch.charCodeAt(0)
  if (code >= 0xac00 && code <= 0xd7a3) return (code - 0xac00) % 28 === 0 ? "는" : "은"
  if (/[0-9]/.test(ch)) return "2459".includes(ch) ? "는" : "은"
  return "은"
}

/** 받침이 없거나 ㄹ 받침이면 "로", 나머지는 "으로". 한글과 숫자로 끝나는 이름만 가리고, 나머지는 "로"로 둔다. */
function euroRo(name: string) {
  const ch = name.trim().slice(-1)
  const code = ch.charCodeAt(0)
  if (code >= 0xac00 && code <= 0xd7a3) {
    const jong = (code - 0xac00) % 28
    return jong === 0 || jong === 8 ? "로" : "으로"
  }
  if (/[0-9]/.test(ch)) return "036".includes(ch) ? "으로" : "로"
  return "로"
}

export const copy = {
  app: {
    name: "AX편의점",
    owner: "상품기획팀",
  },
  nav: {
    label: "주 메뉴", // 임시: 화면 읽기 프로그램용 이름
    newChat: "새 대화",
    recentChats: "최근 대화",
    // 06: 최근 대화의 날짜 묶음과 줄 끝의 표시
    recentGroups: { today: "오늘", yesterday: "어제", week: "지난 7일", older: "그 전" },
    recentWorking: "칠성이가 일하고 있어요", // 임시: 돌아가는 원에 올려놓으면 나오는 말
    recentWaiting: "기획자님의 답을 기다리고 있어요", // 임시: 강조색 점에 올려놓으면 나오는 말
    // 11: 최근 대화 지우기
    recentDelete: "대화 지우기", // 임시: 줄에 올려놓으면 나오는 지우기 버튼의 이름(화면 읽기용, 풍선 도움말)
    deleteTitle: "이 대화를 지울까요?",
    deleteDesc: "지운 대화는 되돌릴 수 없어요.", // 임시: 확인 창의 설명(Astryx AlertDialog가 설명을 꼭 받는다)
    deleteAction: "지우기",
    deleteCancel: "그만두기",
    shelf: "매대",
    panel: "소비자 패널",
    reliability: "신뢰도",
  },
  home: {
    avatar: "칠성이",
    greeting: "안녕하세요, 상품기획팀 칠성이예요.",
    partLabel: "할 일 고르기", // 임시: 위쪽 전환의 이름(화면 읽기용)
    suggestionsLabel: "추천", // 임시: 추천 칩 묶음의 이름(화면 읽기용)
    // 04: 고른 부분에 따라 바뀌는 글(대본 2판의 "첫 화면")
    concept: {
      prompt: "어떤 신제품을 생각하고 계세요?",
      // 첫 칩은 칠성이의 소개를 부른다(서버의 phrases.ABOUT_ASK와 같아야 한다)
      suggestions: ["칠성이는 무엇을 할 수 있나요?", "칠성이에게 추천받기"],
      placeholder: "예: 제로 탄산 신제품을 검토하고 싶어요",
    },
    test: {
      prompt: "어떤 컨셉을 매대에 올려 볼까요?",
      conceptsLabel: "확정한 컨셉", // 임시: 확정한 컨셉 카드 묶음의 이름(화면 읽기용)
      noConcepts: "아직 확정한 컨셉이 없어요. 컨셉 기획에서 먼저 만들거나, 가진 컨셉을 아래에 적어 주세요.",
      // 15: 확정한 컨셉 카드를 누르면 그 대화가 열리고 이 말이 보내진다(서버의 phrases.BTN_SHELF와 같아야 한다)
      sendToShelf: "매대에 올려 보기",
      placeholder: "가진 컨셉을 직접 적어도 돼요",
      preparing: "매대 테스트는 아직 준비하고 있어요.",
      // 06: 확정한 컨셉 카드
      toShelf: "매대에 올리기",
      containers: { can: "캔", pet: "페트", bottle: "병" }, // 임시: 용기 아이콘의 이름(화면 읽기용)
    },
  },
  mode: {
    label: "진행 방식",
    options: [
      { value: "manual", label: "직접 바꾸기", description: "가격, 용량, 행사를 직접 바꿔서 돌려요" },
      { value: "suggest", label: "추천받기", description: "칠성이가 개선안을 내고, 돌릴 것을 골라요" },
      { value: "delegate", label: "칠성이에게 맡기기", description: "정한 범위 안에서 칠성이가 돌리고 보고해요" },
    ],
    defaultValue: "suggest",
  },
  // 13: 입체 매장(/store)
  store: {
    label: "AX편의점 매장", // 임시: 입체 화면의 이름(화면 읽기용)
    loading: "매장을 불러오고 있어요", // 임시: 뼈대의 이름(화면 읽기용)
    failed: "매장을 불러오지 못했어요",
    retry: "다시 하기",
    resetView: "처음 시점으로",
    newSlot: "신제품 자리", // 임시: 비워 둔 칸에 올리면 나오는 풍선
    promo: "행사", // 임시: 행사 표시의 이름(화면 읽기용)
    price: (won: number) => `${won.toLocaleString("ko-KR")}원`,
    volume: (ml: number) => (ml >= 1000 ? `${ml / 1000}L` : `${ml}ml`),
    pack: (n: number) => `${n}개 묶음`, // 임시: 묶음 상품의 수량
  },
  pages: {
    shelf: {
      title: "매대",
      description: "편의점 음료·주류 매대의 상품, 가격, 행사를 봐요.",
    },
    panel: {
      title: "소비자 패널",
      description: "테스트에 참여하는 가상 소비자 3,000명의 구성을 봐요.",
    },
    reliability: {
      title: "신뢰도",
      description: "테스트 결과가 얼마나 일정한지, 실제 편의점 매출과 얼마나 맞는지 봐요.",
    },
    preparing: "준비하고 있어요",
    // 04: /test/new(2부의 자리)
    testPart: {
      title: "매대 테스트는 아직 준비하고 있어요",
      toConcept: "컨셉 기획로 가기", // 임시
    },
  },
  test: {
    stepperLabel: "진행 단계", // 임시
    plannerName: "기획자", // 임시: 기획자 말풍선 위의 이름
    notFound: "대화를 찾지 못했어요",
    // 11: 멈춘 차례
    stopped: "멈춤",
    retryStopped: "다시 하기",
    // 03: 대화 화면
    chilseong: "칠성이", // 임시: 칠성이의 말 옆 캐릭터의 이름(화면 읽기용)
    shopper: "손님", // 임시: 손님의 말 옆 사람 윤곽의 이름(화면 읽기용, 지시서 17)
    chatLabel: "칠성이와의 대화", // 임시: 대화 영역의 이름(화면 읽기용)
    placeholder: "칠성이에게 말하기", // 임시
    sample: "견본 대화",
    disconnected: "칠성이와 연결이 끊겼어요",
    resend: "다시 보내기",
    sendSelected: "이대로 보내기",
    // 06: 여럿 고르기와 카드 안에서 고르기
    multiHint: "여러 개 고를 수 있어요",
    pickedSend: (n: number) => `${n}개 고름 · 보내기`,
    pickNone: "골라서 보내기", // 임시: 하나도 안 골랐을 때의 보내기 버튼(못 누름)
    pickable: "고르기", // 임시: 카드 항목의 네모 칸 이름(화면 읽기용)
    // 08: 하는 일 표시가 5초를 넘으면 이름 옆에 흐른 시간
    elapsed: (s: number) => `${s}초`,
    activityRunning: "하는 중이에요", // 임시: 돌아가는 표시의 이름(화면 읽기용)
    activityDone: "끝났어요", // 임시: 체크 표시의 이름(화면 읽기용)
    // 끝난 하는 일에 "~는 중"이 남지 않게(전에 저장한 대화용). 서버의 phrases.ACT_DONE과 같다
    activityDoneLabel: (label: string): string =>
      ({
        "말씀 읽는 중": "말씀을 읽었어요",
        "찾아보는 중": "찾아봤어요",
        "요즘 소식 찾는 중": "요즘 소식을 찾았어요",
        "아이디어 내는 중": "아이디어를 냈어요",
        "아이디어 고치는 중": "아이디어를 고쳤어요",
        "컨셉 보드 만드는 중": "컨셉 보드를 만들었어요",
        "컨셉 고치는 중": "컨셉을 고쳤어요",
        "매대에 올리는 중": "매대에 올렸어요",
        "결과 정리하는 중": "결과를 정리했어요",
        "손님이 답하는 중": "손님이 답했어요",
        "개선안 내는 중": "개선안을 냈어요",
        "다시 물을 안 정리하는 중": "다시 물을 안을 정리했어요",
      })[label] ?? label,
    chosen: "고른 것", // 임시: 고른 칩 앞 체크 표시의 이름(화면 읽기용)
  },
  workbench: {
    label: "작업대", // 임시: 작업대 영역의 이름(화면 읽기용)
    backToCurrent: "지금 진행 중인 단계로 돌아가기",
    // 10: 기획 브리프 아래의 기획자의 생각
    briefThoughts: "기획자의 생각",
    loadFailed: "불러오지 못했어요",
    // 06, 10: 찾아본 것 카드
    evidenceLabel: "찾아본 것", // 임시: 찾아본 것 목록의 이름(화면 읽기용)
    newTab: "새 창에서 열려요", // 임시: 출처 링크가 새 창으로 열린다는 말(화면 읽기용)
    expand: "펼치기", // 임시: 세 줄에서 자른 근거 본문을 펼치는 곳의 이름(화면 읽기용)
    collapse: "접기", // 임시: 펼친 근거 본문을 접는 곳의 이름(화면 읽기용)
    retry: "다시 하기",
    ideasBasis: "어디서 나왔나",
    // 04: 아이디어 표의 열(대본 2판의 표 머리)
    ideaName: "이름",
    ideaFlavor: "맛",
    ideaPack: "용기와 용량",
    ideaFeatures: "특징",
    ideaDiff: "다른 안과의 차이",
    // 10: 아이디어 보드
    ideaMine: "내 아이디어",
    ideaKept: "남긴 아이디어",
    ideaKeep: "보드에 남기기",
    ideaUnkeep: "남기기 취소",
    ideaMakeConcept: "컨셉으로 만들기",
    makeConceptSay: (name: string) => `${name}, 컨셉으로 만들어 줘`,
    ideaRemove: "보드에서 빼기",
    changedMark: "방금 고쳤어요", // 임시: 방금 고쳐진 칸 옆 작은 점의 이름(화면 읽기용)
    // 10: 카드의 버튼을 누르면 기획자의 말로 보낸다(이름은 그 아이디어의 이름)
    keepSay: (name: string) => `${name}${eunNeun(name)} 남겨 줘`,
    unkeepSay: (name: string) => `${name}${eunNeun(name)} 안 남겨도 돼`, // 임시
    removeSay: (name: string) => `${name}${eunNeun(name)} 빼 줘`,
    // 12: 컨셉 카드(위: 예시 시안, 아래: 제품 특징)
    conceptLetter: (letter: string) => `컨셉 ${letter}`, // 임시: 카드의 이름(화면 읽기용)
    conceptImage: "제품 그림 자리", // 임시: 그림 칸의 이름(화면 읽기용)
    conceptDraft: "예시 시안",
    conceptSpec: "제품 특징",
    conceptPoints: "이런 점이 좋아요",
    conceptWho: "타깃과 음용 상황", // 임시: 컨셉 카드의 묶음 제목
    conceptSpecs: "제품 사양", // 임시: 컨셉 카드의 묶음 제목
    conceptCompare: "매대에서 비교되는 제품", // 임시: 컨셉 카드의 묶음 제목
    conceptPriceLine: (price: string, pack: string) => (pack ? `${price} (${pack})` : price),
    // 15: 매대 테스트 카드(shelf-run)
    run: {
      store: "입체 매장", // 임시: 매장 자리의 이름(화면 읽기용)
      asking: (who: string, total: number) => `${who} ${total.toLocaleString("ko-KR")}명에게 물어요`, // 임시: 누구에게 묻는지 한 줄
      visitedLabel: "다녀간 손님",
      visited: (asked: number, total: number) => `${asked.toLocaleString("ko-KR")} / ${total.toLocaleString("ko-KR")}`,
      progress: "다녀간 손님 수", // 임시: 진행 막대의 이름(화면 읽기용)
      // 카드의 버튼은 이 말을 대화로 보낸다(서버의 phrases.BTN_EARLY_RESULT, BTN_RESULT와 같아야 한다)
      early: "먼저 온 결과 보기",
      result: "결과 보기",
      stop: "멈추고 결과 보기",
      stopped: "멈춤",
      failed: "멈췄어요", // 임시: 서버에서 실패한 테스트의 표시
      running: "묻는 중", // 임시: 돌고 있다는 표시의 이름(화면 읽기용)
    },
    // 15: 결과 카드(result). docs/shelf-test-plan.md 3-3의 구성
    result: {
      asked: (who: string, n: number) => `${who} ${n.toLocaleString("ko-KR")}명에게 물었어요`,
      picked: "고른 가상 소비자",
      pickedCount: (n: number) => `${n.toLocaleString("ko-KR")}명`,
      noneYet: "아직 고른 가상 소비자가 없어요",
      range: (low: number, high: number) => `범위 ${low}~${high}명`,
      rangeLabel: "범위", // 임시: 폭 막대의 이름(화면 읽기용)
      rank: "매대에서의 순위",
      rankLine: (products: number, rank: number) => `음료 매대 ${products}개 제품 중 ${rank}위`,
      topPicked: "많이 고른 제품", // 임시: 컨셉을 아무도 구매하지 않았을 때 순위 대신 보이는 묶음의 이름
      own: "자사", // 임시: 자사 제품의 작은 표시
      from: "컨셉이 없는 매대에서 고르던 제품",
      fromRival: "경쟁사 제품",
      fromOwn: "자사 제품",
      fromNone: "고르지 않음",
      fromPending: (n: number) => `${n}명은 컨셉이 없는 매대에서 고르던 제품을 아직 확인하고 있어요.`,
      barriers: "걸린 점",
      quotes: "가상 소비자의 말",
      quotesPicked: "고른 가상 소비자", // 임시
      quotesPassed: "고르지 않은 가상 소비자", // 임시
      chose: (name: string) => `고른 것: ${name}`, // 임시
      // 17: 손님의 말마다의 버튼과, 누르면 대화로 가는 말
      ask: "이 가상 소비자 인터뷰하기",
      askSay: (who: string) => `${who} 가상 소비자를 인터뷰할게요`, // 임시: 기획자의 말풍선으로 남는 말
      count: (n: number) => `${n.toLocaleString("ko-KR")}명`,
    },
    // 17, 19: 개선안 테스트 카드(기존안과 변경안마다 타일 한 장)
    improve: {
      /** 카드 머리 오른쪽에 누구의 응답인지와 응답 인원을 보인다. */
      head: (who: string, n: number) => `${who} ${n.toLocaleString("ko-KR")}명 가운데 구매한 손님`,
      // 안의 이름(서버 agent/improve.py의 BASE_NAME, KIND_NAMES와 같다)
      baseName: "기존안",
      baseMark: "기준",
      kindNames: { price: "가격 변경안", name: "제품명 변경안", pack: "용기·용량 변경안", promo: "행사 변경안" },
      numbered: (name: string, k: number) => `${name} ${k}`,
      /** 옛 대화의 항목(kind가 없음): change 글의 앞말로 종류를 가린다(서버 change_text의 앞말) */
      changePrefixes: { price: "가격 ", pack: "용기와 용량 ", name: "이름 ", promo: "행사 " },
      arrow: "→",
      about: (name: string) => `${name}의 까닭`, // 임시: 까닭을 보이는 i 단추의 이름(화면 읽기용)
      price: (won: number) => `${won.toLocaleString("ko-KR")}원`,
      count: (n: number) => `${n.toLocaleString("ko-KR")}명`,
      delta: (n: number) => `${n.toLocaleString("ko-KR")}명`,
      same: "차이 없음",
      deltaLabel: { more: "기존안보다 많아요", less: "기존안보다 적어요" }, // 임시: 화살표의 이름(화면 읽기용)
      visited: (asked: number, total: number) => `${asked.toLocaleString("ko-KR")} / ${total.toLocaleString("ko-KR")}`,
      running: "테스트하는 중", // 임시: 스피너의 이름(화면 읽기용)
      bar: (name: string, n: number) => `${name} ${n.toLocaleString("ko-KR")}명`, // 임시: 막대의 이름(화면 읽기용)
      rank: (products: number, rank: number) => `음료 매대 ${products}개 제품 중 구매 ${rank}위`,
      // 버튼과 누르면 대화로 가는 말(서버의 phrases.BTN_IMPROVE_ALL, BTN_IMPROVE_COMPARE, BTN_REPORT와 같아야 한다)
      rerun: "테스트하기",
      rerunSay: (name: string) => `${name}${euroRo(name)} 테스트해 줘`, // 임시: 기획자의 말풍선으로 남는 말
      rerunAll: "남은 안 모두 테스트하기",
      /** 도는 것을 본 변경안의 결과가 나오면 카드가 스스로 보내는 말이기도 하다(지시서 20) */
      compare: "변경안 결과 보기",
      report: "결과 보고서 내려받기",
    },
    // 14: 컨셉 보드 카드 머리 오른쪽의 버튼(대화의 download 버튼과 같은 일)
    download: "제안서로 내려받기",
    // 21: 결과 보고서 단계에서 작업대 머리 오른쪽의 버튼(제안서 화면을 새 탭으로 연다)
    savePdf: "PDF로 저장하기",
  },
  // 14: 신제품 제안서 화면(/proposal/:chatId). 종이 안의 문장은 서버가 보고서체로 보낸 그대로 쓰고, 칸의 이름만 여기에 둔다.
  proposal: {
    back: "대화로 돌아가기",
    save: "PDF로 저장하기",
    failed: "제안서를 만들지 못했어요",
    retry: "다시 해 보기",
    loading: "제안서를 만들고 있어요", // 임시: 뼈대의 이름(화면 읽기용)
    heading: "신제품 제안서",
    meta: (dept: string, date: string) => `${dept} | ${date}`,
    /** "2026-11-21" → "2026. 11. 21." */
    date: (iso: string) => {
      const [y, m, d] = iso.split("-")
      return y && m && d ? `${y}. ${m}. ${d}.` : iso
    },
    docTitle: (title: string) => `신제품 제안서 ${title}`, // 임시: PDF로 저장할 때의 파일 이름이 되는 창의 제목
    gist: "제안 요지",
    sections: {
      background: "제안 배경",
      overview: "제품 개요",
      compare: "경쟁 제품 및 차별점",
      plan: "향후 계획",
    },
    // 22: 매대 테스트를 한 컨셉의 종이(결과 보고서). 칸 안의 문장은 서버가 보낸다
    reportHeading: "신제품 매대 테스트 결과 보고",
    review: "검토 의견",
    report: {
      overview: "테스트 개요",
      findings: "주요 결과",
      variants: "변경안 비교",
      voices: "소비자 반응",
      plans: "시사점 및 향후 계획",
    },
    caution: "유의 사항",
    inflowHead: { label: "수요 유입 경로", n: "소비자 수", share: "비율" },
    variantHead: { name: "안", change: "바꾼 값", n: "선택", rank: "선택 순위" },
    people: (n: number) => `${n.toLocaleString("ko-KR")}명`,
    rank: (rank: number | null) => (rank ? `${rank}위` : "-"),
    quote: (said: string, who: string | null) => (who ? `"${said}" (${who})` : `"${said}"`),
    barLabel: (name: string, value: string) => `${name} ${value}`,
    // "LLM용 복사": 참가자가 정한 이름이라 화면에 내지 않는 말의 예외로 둔다
    copyLlm: "LLM용 복사",
    copied: "복사했어요",
    copyFailed: "복사하지 못했어요",
    mdTitle: (heading: string, title: string) => `${heading}: ${title}`,
    overviewHead: { label: "항목", value: "내용" }, // 임시: 복사한 마크다운의 제품 개요 표 머리(종이에는 머리가 없다)
    numbered: (n: number, title: string) => `${n}. ${title}`,
    sketch: "예시 시안",
    compareHead: { role: "구분", name: "제품", pack: "용기·용량", price: "판매가", promo: "행사" },
    roles: { proposal: "제안 제품", rival: "경쟁 제품", own: "자사 유사 제품" },
    pod: (text: string) => `차별점: ${text}`,
    ref: (n: number) => `${n})`,
  },
  design: {
    title: "견본 페이지", // 임시: 아래 이름표 모두 임시
    colors: "색",
    colorNames: {
      accent: "강조",
      text: "글씨",
      secondary: "보조 글씨",
      border: "선",
      surface: "면",
      wash: "옅은 면",
      neutral: "버튼 면",
    },
    typeScale: "글씨 크기",
    typeSample: "검토할 신제품을 한 줄로 알려 주세요. 1,234원",
    buttons: "버튼",
    buttonVariants: { primary: "주", secondary: "보조", ghost: "글자만" },
    buttonStates: { normal: "기본", hover: "올려놓음(마우스를 올려 보세요)", disabled: "못 누름" },
    buttonSizes: "크기",
    buttonSample: "테스트 시작하기",
    chips: "추천 칩",
    modeButton: "진행 방식 버튼",
    modeButtonOpen: "펼친 모습",
    composer: "입력창",
    composerEmpty: "비어 있음",
    composerFilled: "글이 있음",
    composerSample: "제로 탄산 500ml 페트를 검토하고 싶어요",
    navItems: "왼쪽 메뉴 항목",
    navDefault: "기본",
    navSelected: "고른 상태",
    navRecent: "최근 대화 한 줄",
    navRecentHover: "최근 대화 한 줄: 올려놓으면 지우기 버튼", // 임시
    activityStopped: "하는 일: 멈춤", // 임시
    activityHalted: "하는 일: 끊김(돌지 않음)", // 임시
    stepper: "단계 표시줄",
    stepperFirst: "컨셉 기획 · 1단계",
    stepperSecond: "컨셉 기획 · 2단계",
    stepperThird: "컨셉 기획 · 3단계(컨셉 보드 분석)",
    stepperTest: "매대 테스트 · 2단계",
    stepperDone: "끝난 상태",
    card: "카드",
    cardTitle: "제로 탄산 500ml 페트",
    cardBody: "카드 안의 글은 이렇게 보여요.",
    emptyState: "빈 상태",
    avatar: "칠성이 자리",
    bubble: "기획자 말풍선",
    // 03: 대화 부품과 작업대 카드(임시: 견본 페이지의 이름표)
    chatParts: "대화 부품",
    say: "칠성이의 말",
    sayThinking: "칠성이가 말하는 중",
    activity: "하는 일 한 줄",
    choices: "칩",
    choicesMulti: "칩(여럿 고르기)",
    actions: "버튼 묶음",
    confirm: "확인 카드",
    summary: "요약 카드",
    active: "누를 수 있음",
    past: "지난 차례(흐려짐)",
    disconnected: "연결 끊김",
    workbenchCards: "작업대 카드",
    briefStates: ["브리프: 칸 하나만 정함", "브리프: 여럿 정함과 기획자의 생각"],
    ideas: "아이디어",
    otherCards: "임시 카드",
    loadingCard: "뼈대",
    errorCard: "오류",
    // 04(임시: 견본 페이지의 이름표)
    partSwitch: "위쪽 전환",
    partConcept: "컨셉 기획를 고름",
    partTest: "매대 테스트를 고름",
    confirmedConcepts: "확정한 컨셉 카드",
    confirmedSome: "있음",
    confirmedNone: "없음",
    testNotice: "누르거나 보냈을 때의 안내",
    actionsNoted: "설명이 붙은 버튼 묶음",
    actionsNotedTwo: "버튼 둘",
    actionsNotedThree: "버튼 셋",
    confirmNoted: "설명이 붙은 확인 카드",
    ideasTable: "아이디어 표",
    conceptBoard: "컨셉 보드",
    narrow: "좁은 작업대",
    // 06(임시: 견본 페이지의 이름표)
    evidence: "찾아본 것",
    evidenceAdded: "항목이 늘어남(새 항목만 잠깐 강조)",
    addEvidence: "항목 하나 더하기",
    freeChip: "직접 쓰기가 온 칩(그리지 않음)",
    onCard: "카드 안에서 고르기",
    onCardBefore: "고르기 전",
    onCardTwo: "둘 고름",
    onCardSent: "보낸 뒤",
    onCardChat: "대화 쪽",
    multiChips: "여럿 고르기 칩",
    recentMarks: "최근 대화의 표시",
    confirmedBundle: "확정한 컨셉 카드",
    ideaCards: "아이디어 카드(다른 값만 강조)",
    // 08(임시: 견본 페이지의 이름표)
    activityRunning: "하는 일: 하는 중",
    activitySlow: "하는 일: 5초 넘음",
    activityDone: "하는 일: 끝남",
    chipsAndButtons: "칩과 버튼(한 줄, 같은 높이)",
    chipsLong: "긴 이름",
    navCollapsed: "접은 메뉴",
    navExpanded: "펼친 메뉴",
    evidenceLong: "본문이 긴 것(세 줄에서 자름)",
    // 10(임시: 견본 페이지의 이름표)
    ideaBoard: "아이디어 보드(내 아이디어, 남긴 것, 방금 고쳐진 칸)",
    ideaBoardPick: "아이디어 보드: 컨셉으로 만들 것을 고르는 차례",
    ideaBoardBusy: "아이디어 보드: 칠성이가 말하는 중(버튼을 못 누름)",
    nextTurn: "다음 차례 보기",
    prevTurn: "처음으로",
    conceptChanged: "방금 고쳐진 줄(첫 번째 컨셉의 용량을 줄임)",
    // 12(임시: 견본 페이지의 이름표)
    conceptTwo: "컨셉 둘 나란히(값이 다른 줄만 굵게, 같은 줄은 같은 높이)",
    conceptOne: "컨셉 하나(모두 보통 굵기)",
    conceptNoRivals: "경쟁 제품이 없는 컨셉",
    conceptOld: "저장된 옛 대화의 컨셉(있는 칸만)",
    sentAs: "보낸 말",
    // 19(임시: 견본 페이지의 이름표)
    improveCard: "개선안 테스트(돌린 안, 도는 안, 안 돌린 안, 옛 모양의 안)",
    // 진단 카드(임시: 견본 페이지의 이름표)
    diagnosisFlags: "컨셉 보드 분석: 살펴볼 점 둘, 가격을 고친 안 하나",
    diagnosisClear: "컨셉 보드 분석: 걸리는 점 없음",
    diagnosisNoFix: "컨셉 보드 분석: 살펴볼 점이 있지만 고칠 안이 없음",
  },
} as const

export type ModeValue = (typeof copy.mode.options)[number]["value"]
