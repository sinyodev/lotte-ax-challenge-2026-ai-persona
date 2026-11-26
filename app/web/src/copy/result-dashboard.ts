/**
 * 테스트 결과 화면(ResultDashboard의 머리와 전체 결과 표, ResultReport)의 글. 한 줄 결론은 서버(brief.headline)가 보내고, 서버가 없는 옛 결과에서만 여기의 글틀을 쓴다.
 * 이 화면에서 사람 수의 주어는 "가상 소비자"다("손님"과 섞지 않는다). 숫자는 코드가 넣는다.
 */
const count = new Intl.NumberFormat("ko-KR")
const n = (x: number) => count.format(x)

/** 받침이 있으면 앞의 것, 없으면 뒤의 것("을/를"). 한글이 아니면(숫자·영문) 받침 없음으로 본다. */
function josa(word: string, pair: string) {
  const [yes, no] = pair.split("/")
  const last = word.trim().replace(/['’”")\]]+$/, "").slice(-1)
  const code = last.charCodeAt(0) - 0xac00
  return code >= 0 && code <= 11171 && code % 28 !== 0 ? yes : no
}

export const dashCopy = {
  // 머리
  spec: (pack: string, price: number) => `${pack}, ${n(price)}원`,
  who: (group: string, total: number) => `${group} ${n(total)}명에게 물었어요`,
  whoAll: (total: number) => `가상 소비자 ${n(total)}명에게 물었어요`,
  running: "중간 결과",
  done: "테스트 완료",
  stopped: "멈춘 테스트",
  failed: "멈춘 테스트",
  answered: (asked: number, total: number) => `${n(total)}명 중 ${n(asked)}명이 답했어요`,
  eta: (sec: number) => (sec < 60 ? "1분 안에 끝나요" : `약 ${Math.ceil(sec / 60)}분 남았어요`),
  progress: "답한 가상 소비자", // 진행 막대의 이름(화면 읽기용)
  // 한 줄 결론(옛 결과, 서버의 글이 없을 때)
  headline: (group: string, total: number, k: number, rank: number | null, products: number, running: boolean) => {
    const lead = running ? "지금까지는 " : ""
    if (!k) return `${lead}${group} ${n(total)}명 중 고른 가상 소비자가 ${running ? "없어요" : "없었어요"}`
    return rank
      ? `${lead}${group} ${n(total)}명 중 ${n(k)}명이 골랐고, 매대 ${products}개 가운데 ${rank}위예요`
      : `${lead}${group} ${n(total)}명 중 ${n(k)}명이 골랐어요`
  },
  // 숫자 타일
  tileRate: "선택률",
  rate: (pct: string) => `${pct}%`,
  tileRank: "매대 순위",
  rank: (rank: number) => `${rank}위`,
  noRank: "순위 없음",
  rankOf: (products: number) => `${products}개 제품 가운데`,
  tileOwn: "자사 제품에서 옮겨 옴",
  tileBarrier: "가장 큰 걸림돌",
  people: (x: number) => `${n(x)}명`,
  // 차트 제목(인사이트 한 문장)
  shelfTitle: "매대 내 선택 순위",
  shelfTimes: (name: string, top: number, times: string) => `기존 1위 ${name}(${n(top)}명)의 ${times}배예요`,
  shelfBehind: (name: string, top: number, k: number) => `기존 1위 ${name}(${n(top)}명)보다 ${n(top - k)}명 적어요`,
  shelfRankOnly: (products: number, rank: number) => `매대 ${products}개 제품 가운데 ${rank}위예요`,
  shelfNone: "고른 가상 소비자가 없었어요. 많이 고른 기존 제품이에요",
  fromTitle: "수요 유입 경로",
  fromOwn: (k: number, own: number) => `고른 ${n(k)}명 가운데 ${n(own)}명은 자사 제품을 고르던 가상 소비자예요`,
  fromRivalMost: (k: number, rival: number) => `고른 ${n(k)}명 가운데 ${n(rival)}명은 경쟁사 제품을 고르던 가상 소비자예요`,
  segRival: "경쟁사 제품",
  segOwn: "자사 제품",
  segNone: "아무것도 안 삼",
  segPending: "확인 중",
  barrierTitle: "비구매 요인",
  barrierLine: (passed: number, c: number, label: string) =>
    `고르지 않은 ${n(passed)}명 중 ${n(c)}명이 '${label}'${josa(label, "을/를")} 들었어요`,
  occasionTitle: "음용 상황별 선택률",
  occasionLine: (occ: string) => `'${occ}'일 때 가장 많이 골랐어요`,
  // 손님의 말
  quotes: "가상 소비자의 말",
  quotesPicked: "고른 가상 소비자",
  quotesPassed: "고르지 않은 가상 소비자",
  chose: (name: string) => `${name}${josa(name, "을/를")} 골랐어요`,
  choseNothing: "아무것도 사지 않았어요",
  noPurchase: "아무것도 사지 않음", // 서버 shelftest/result.NO_PURCHASE_SHOWN과 같다
  // 전체 결과 표
  all: "전체 결과 표",
  tFrom: "고른 가상 소비자가 컨셉이 없는 매대에서 고르던 제품",
  tKind: "구분",
  tProduct: "제품",
  tPeople: "가상 소비자",
  tBarriers: "고르지 않은 까닭",
  tOccasions: "음용 상황별 선택",
  tOccasion: "음용 상황",
  tAsked: "답한 수",
  tPicked: "고른 수",
  tRate: "선택률",
  tNeighbors: "매대 순위 가까이의 제품",
  tQuotes: "그 밖의 가상 소비자의 말",
  tRecords: "테스트 기록",
  // 견본 페이지(/design)의 이름
  designRunning: "테스트 결과: 도는 중(견본)",
  designOld: "테스트 결과: 요약 없는 옛 결과(견본)",
}
