const count = new Intl.NumberFormat("ko-KR")
const n = (x: number) => count.format(x)
const won = (x: number) => `${n(Math.round(x))}원`
const pct = (x: number) => `${Math.round(x)}%`

/** 받침이 있으면 앞의 것, 없으면 뒤의 것("을/를"). */
function josa(word: string, pair: string) {
  const [yes, no] = pair.split("/")
  const code = word.trim().slice(-1).charCodeAt(0) - 0xac00
  return code >= 0 && code <= 11171 && code % 28 !== 0 ? yes : no
}

/**
 * 후속 개선의 새 화면(보고서 한 장): 조사 확인. 다음 행동은 칠성이의 말과 대화의 버튼이 맡는다.
 * 글의 기준(토스 UX 라이팅): 한 문장에 숫자 하나의 뜻, 누가 무엇을 했는지를 주어로, 통계의 말(대비, 편차, 문항) 대신 일상의 말.
 * "가상 소비자의 값"은 "예상", "조사의 값"은 "실제"로만 부른다.
 */
export const followupReportCopy = {
  won,
  people: (x: number) => `${n(x)}명`,
  pct,
  // 결론: 가장 크게 어긋난 곳을 실제 → 예상의 차례로
  headline: {
    same: (target: string) => `실제 ${target}의 답은 예상과 거의 같았어요.`,
    price: (price: number, target: string, actual: number, virtual: number) =>
      `실제 ${target}의 ${pct(actual)}만 ${won(price)}을 내겠다고 했어요. 예상은 ${pct(virtual)}였어요.`,
    worry: (target: string, actual: number, virtual: number) =>
      `맛이 걱정된다는 실제 ${target}는 ${pct(actual)}였어요. 예상은 ${pct(virtual)}였어요.`,
  },
  // 숫자 줄
  figAnswers: (target: string) => `조사에 답한 ${target}`,
  figAnswersOf: (raw: number) => `전체 응답 ${n(raw)}명 가운데`,
  figRemoved: "뺀 응답",
  figRemovedOf: (items: { label: string; count: number }[]) => items.map((r) => `${r.label} ${n(r.count)}명`).join(", "),
  figNone: "뺀 응답이 없어요",
  figGap: { price: (price: number) => `${won(price)}을 내겠다는 사람`, worry: () => "맛이 걱정된다는 사람" } as Record<string, (price: number) => string>,
  figGapOf: (virtual: number) => `예상은 ${pct(virtual)}였어요`,
  // ① 예상과 실제
  diffName: "예상과 실제",
  diffTitle: { price: "예상과 가장 달랐던 것은 가격이에요", worry: "예상과 가장 달랐던 것은 맛 걱정이에요" } as Record<string, string>,
  diffSame: "예상과 실제가 거의 같았어요",
  colItem: "소비자의 답",
  colVirtual: "예상",
  colActual: "실제",
  colGap: "차이",
  gap: (x: number) => (x > 0 ? `+${n(x)}%p` : x < 0 ? `−${n(-x)}%p` : "같음"),
  keyVirtual: (total: number) => `예상: 가상 소비자 ${n(total)}명`,
  keyActual: (target: string, total: number) => `실제: 조사에 답한 ${target} ${n(total)}명`,
  notAsked: "예상 없음",
  how: (target: string, total: number, priced: number | null, virtual: number) =>
    `실제는 조사에 답한 ${target} ${n(total)}명의 답이에요.${priced && priced !== total ? ` 가격은 값을 적어 낸 ${n(priced)}명으로 계산했어요.` : ""} ` +
    `예상은 처음 매대 테스트에서 가상 소비자 ${n(virtual)}명이 고르지 않은 까닭으로 든 것을 센 값이에요.`,
  // ② 가격
  priceName: "가격을 바꾸면 (조사에 답한 100명에게 팔 때)",
  priceTitle: (best: number, now: number) =>
    best === now ? `지금 가격 ${won(now)}일 때 매출이 가장 커요`
      : `${won(best)}으로 ${best < now ? "내리면" : "올리면"} 매출이 가장 커요`,
  colPrice: "가격",
  colCanPay: "사겠다는 사람",
  colMoney: "매출",
  money: (x: number) => `${(x / 10000).toFixed(1)}만 원`,
  moneyAxis: (x: number) => `${Math.round(x / 10000)}만`,
  nowAt: (p: number) => `지금 가격 ${won(p)}`,
  keyBest: "매출이 가장 큰 가격",
  keyRest: "다른 가격",
  tipMoney: "100명에게 팔 때의 매출",
  // ③ 소비자가 적은 이유
  badName: "망설인 이유",
  badTitle: (text: string) => `망설인 사람은 '${text}'${josa(text, "을/를")} 가장 많이 들었어요`,
  goodName: "사고 싶은 이유",
  goodTitle: (text: string) => `사고 싶은 사람은 '${text}'${josa(text, "을/를")} 가장 많이 들었어요`,
  colOpinion: "이유",
  colSaid: "답한 사람",
  colIntent: "그중 사겠다는 사람",
  // 다시 테스트 결과
  retest: {
    headline: (name: string, before: number, after: number) =>
      after < before ? `실제 답에 맞추니 ${name}${josa(name, "을/를")} 고른 사람이 ${n(before)}명에서 ${n(after)}명으로 줄었어요.`
        : after > before ? `실제 답에 맞추니 ${name}${josa(name, "을/를")} 고른 사람이 ${n(before)}명에서 ${n(after)}명으로 늘었어요.`
          : `실제 답에 맞춰도 ${name}${josa(name, "을/를")} 고른 사람은 ${n(before)}명으로 같았어요.`,
    figBefore: "처음 테스트",
    figAfter: "다시 테스트",
    figOf: (total: number) => `${n(total)}명 중 고른 사람`,
    figLost: "빠진 사람",
    figLostOf: "처음에는 골랐지만 이번에는 고르지 않음",
    figGain: "새로 고른 사람",
    figGainOf: "처음에는 고르지 않았지만 이번에는 고름",
    moveName: "고른 사람의 변화",
    moveTitle: (lost: number, gain: number) =>
      lost && gain ? `${n(lost)}명이 빠지고 ${n(gain)}명이 새로 골랐어요` : lost ? `${n(lost)}명이 빠졌고 새로 고른 사람은 없어요`
        : gain ? `빠진 사람 없이 ${n(gain)}명이 새로 골랐어요` : "고른 사람이 그대로예요",
    colGroup: "가상 소비자",
    colCount: "사람 수",
    stay: "두 번 모두 고른 사람",
    lost: "빠진 사람",
    gain: "새로 고른 사람",
    lostName: "빠진 가상 소비자",
    lostTitle: "실제 답을 반영하자 고르지 않게 된 사람들이에요",
    gainName: "새로 고른 가상 소비자",
    gainTitle: "실제 답을 반영하자 고르게 된 사람들이에요",
    colWho: "누구",
    colLines: "반영한 조사 답",
    colSaid: "매대에서 한 말",
    noLines: "반영한 답 없음",
    running: (asked: number, total: number) => `${n(total)}명 중 ${n(asked)}명에게 다시 물었어요. 끝나면 결과가 여기에 나와요.`,
    say: {
      done: (target: string, name: string, before: number, after: number) =>
        `다시 테스트가 끝났어요. 실제 ${target}의 답에 맞추니 ${name}${josa(name, "을/를")} 고른 사람이 ${n(before)}명에서 ${n(after)}명${after === before ? "으로 같았어요" : after < before ? "으로 줄었어요" : "으로 늘었어요"}.`,
      move: (lost: number, gain: number) =>
        lost && gain ? `${n(lost)}명이 빠지고 ${n(gain)}명이 새로 골랐어요.` : lost ? `${n(lost)}명이 빠졌고 새로 고른 사람은 없어요.`
          : gain ? `빠진 사람 없이 ${n(gain)}명이 새로 골랐어요.` : "누가 골랐는지도 그대로예요.",
      ask: (lost: number) => (lost ? "빠진 사람을 다시 데려올 개선안을 조사에서 찾아볼까요?" : "조사에서 나온 개선안도 볼까요?"),
      btnIdeas: "조사에서 나온 개선안 보기",
      planner: "가상 소비자 고치고 다시 테스트",
    },
  },
  // 가상 소비자 최적화
  fit: {
    headline: (n: number, target: string) => `가상 소비자 ${count.format(n)}명이 이제 실제 ${target}처럼 답해요.`,
    lead: (target: string, k: number, n: number) =>
      `최적화는 가상 소비자의 답을 실제 조사와 같은 비율로 맞추는 일이에요. 조사에 답한 ${target} ${count.format(k)}명의 답을 가상 소비자 ${count.format(n)}명에게 나눠 줬어요.`,
    figSurvey: (target: string) => `반영한 실제 ${target}`,
    figSurveyOf: "조사에 답한 사람",
    figPeople: "최적화한 가상 소비자",
    figPeopleOf: "처음 매대 테스트의 가상 소비자 그대로",
    figBefore: (virtual: number) => `최적화 전에는 ${pct(virtual)}였어요`,
    figNew: "최적화 전에는 없던 답이에요",
    name: "바뀐 것",
    title: { price: "가격을 보는 눈이 가장 크게 바뀌었어요", worry: "맛을 걱정하는 사람의 수가 가장 크게 바뀌었어요" } as Record<string, string>,
    titleSame: "최적화 전과 거의 같아요",
    colBefore: "최적화 전",
    colAfter: "최적화 후",
    colActual: "실제",
    keyBefore: "최적화 전",
    keyAfter: "최적화 후",
    none: "없음",
    valueName: "좋아진 점",
    valueTitle: (target: string) => `실제 ${target}가 망설이는 곳을 가상 소비자로 찾을 수 있어요`,
    value: {
      price: (price: number, before: number, after: number) =>
        `가격: ${won(price)}이 부담인 가상 소비자가 ${pct(100 - before)}에서 ${pct(100 - after)}로 늘었어요. 얼마로 고쳐야 하는지 볼 수 있어요.`,
      worry: (_price: number, before: number, after: number) =>
        `맛: 맛을 걱정하는 가상 소비자가 ${pct(before)}에서 ${pct(after)}로 ${after < before ? "줄었어요" : "늘었어요"}. 맛을 고칠지 말지 판단할 수 있어요.`,
    } as Record<string, (price: number, before: number, after: number) => string>,
    valueHope: (after: number) => `기대: 맛이 궁금하거나 추억이 떠오른다는 가상 소비자가 ${pct(after)} 생겼어요. 무엇을 앞세울지 볼 수 있어요.`,
    how: "낼 수 있는 가격과 걱정, 기대만 반영했어요. 사겠다는 답은 실제 구매와 달라서 반영하지 않았어요.",
  },
  // 최적화로 나온 개선안과 보정의 순환
  ideas: {
    headline: (k: number) => `최적화한 가상 소비자로 보니 고칠 곳이 ${["", "한", "두", "세"][k] ?? k} 가지예요.`,
    none: "최적화한 가상 소비자로 봐도 새로 고칠 곳은 없어요.",
    lead: "아직 매대에서 테스트한 값은 아니에요. 최적화한 가상 소비자 가운데 누구에게 닿는지만 셌어요.",
    name: "개선안",
    title: (first: string) => `먼저 볼 것은 ${first}이에요`,
    kinds: { price: "가격", flavor: "맛", appeal: "소구점" } as Record<string, string>,
    colWhat: "바꿀 것",
    colNow: "지금",
    colNext: "바꾸면",
    colReach: "닿는 가상 소비자",
    reach: {
      price: (before: number, after: number) => `낼 수 있는 사람 ${pct(before)} → ${pct(after)}`,
      people: (k: number, total: number) => `${count.format(total)}명 중 ${count.format(k)}명`,
    },
    cycleName: "보정의 순환",
    cycleTitle: (saved: boolean) => (saved ? "가상 소비자 인사이트에 추가했어요" : "조사를 올릴 때마다 가상 소비자가 실제에 가까워져요"),
    cycle: ["매대 테스트", "제안서", "실제 소비자 조사", "조사 결과 올리기", "가상 소비자 최적화", "개선안"],
    cycleNow: 5,
    cycleBack: "다시 매대 테스트로",
    savedCols: ["타깃", "반영한 조사", "최적화한 가상 소비자", "1,800원을 내겠다", "맛 걱정"],
    savedPrice: (price: number) => `${won(price)}을 내겠다`,
    savedWorry: "맛 걱정",
    colTarget: "타깃",
    colSurvey: "반영한 조사",
    colPeople: "최적화한 가상 소비자",
  },
  // 견본 페이지(/proto/followup)의 대화
  proto: {
    stage: "후속 개선",
    file: "3-2_소비자조사_패널데이터.xlsx",
    placeholder: "칠성이에게 말하기",
    loading: "조사 결과를 불러오고 있어요.",
    missing: "올린 조사를 찾지 못했어요. 주소 끝에 ?upload=올림 번호를 붙여 주세요.",
    read: (raw: number, removed: number, target: string, k: number) =>
      `조사 결과를 읽었어요. ${n(raw)}명 가운데 ${removed ? `중복이거나 성의 없는 답 ${n(removed)}명을 빼고, ` : ""}${target} ${n(k)}명의 답을 봤어요.`,
    gaps: (cnt: number) => `제 예상과 ${["", "한", "두", "세"][cnt] ?? cnt} 가지가 달랐어요.`,
    gap: {
      price: (price: number, virtual: number, actual: number) =>
        virtual >= 100 ? `가격: 저는 모두 ${won(price)}을 낼 거라고 봤는데, 실제로는 ${pct(actual)}만 내겠다고 했어요.`
          : `가격: 저는 ${pct(virtual)}가 ${won(price)}을 낼 거라고 봤는데, 실제로는 ${pct(actual)}였어요.`,
      worry: (_price: number, virtual: number, actual: number) =>
        `맛: 저는 ${pct(virtual)}가 맛을 걱정할 거라고 봤는데, 실제로는 ${pct(actual)}였어요.`,
    } as Record<string, (price: number, virtual: number, actual: number) => string>,
    noGap: "제 예상과 거의 같았어요.",
    ask: (target: string, total: number) => `실제 ${target}의 답에 맞춰 가상 소비자를 고치고, 같은 ${n(total)}명에게 다시 물어볼까요?`,
    btnApply: "가상 소비자 고치고 다시 테스트",
    btnIdeas: "조사에서 나온 개선안 보기",
  },
}
