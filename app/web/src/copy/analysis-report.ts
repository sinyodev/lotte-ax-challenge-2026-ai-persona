const won = (n: number) => `${Math.round(n).toLocaleString("ko-KR")}원`
const ym = (month: string) => `${Number(month.slice(0, 4))}년 ${Number(month.slice(5, 7))}월`

/** 컨셉 보드 분석의 새 화면(보고서 한 장). 다음 행동은 화면이 아니라 칠성이의 말과 대화의 버튼이 맡는다. */
export const analysisReportCopy = {
  flag: "살펴볼 점",
  ok: "문제없음",
  // 숫자 줄의 덧말
  shelfRoom: "냉장·냉동 설비 불필요",
  historyEnded: "단종되거나 개발을 멈춘 비슷한 제품",
  // 검색 추이(최근 1년과 그 전 1년을 같은 달끼리 겹친다)
  summer: "여름",
  monthShort: (m: number) => `${m}월`,
  period: (from: string, to: string) => `${ym(from)}~${ym(to)}`,
  change: (n: number) => (n > 0 ? `+${n}%` : n < 0 ? `−${-n}%` : "0%"),
  // 가격(내겠다는 값의 분포와 우리 가격)
  ours: "우리 가격",
  oursAt: (p: number) => `우리 가격 ${won(p)}`,
  wtpMedian: "소비자가 내겠다는 값(가운데)",
  wtpHalf: "절반이 답한 범위",
  sameGroup: "같은 용량의 다른 제품",
  sameRange: (n: number) => `같은 용량의 다른 제품 ${n}종`,
  range: (a: number, b: number) => (a === b ? won(a) : `${won(a)}~${won(b)}`),
  wouldPay: (p: number, k: number, n: number) =>
    `${won(p)} 이상을 내겠다는 사람 ${k.toLocaleString("ko-KR")}명(${Math.round((k / n) * 100)}%)`,
  wouldNot: (k: number) => `그보다 낮게 답한 사람 ${k.toLocaleString("ko-KR")}명`,
  people: (n: number) => `${n}명`,
  binTitle: (p: number) => `${won(p)}대`,
  binName: "이 값까지 내겠다는 사람",
  won,
  // 과거 사례
  historyTitle: (n: number) => `비슷한 제품이 전에 ${n}건 있었어요`,

}
