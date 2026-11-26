const won = (n: number) => `${Math.round(n).toLocaleString("ko-KR")}원`
const pct = (n: number) => `${Math.round(n)}%`
/** 빼기는 마이너스 기호(−)로 쓴다. */
const signed = (n: number, unit: (v: number) => string) => n > 0 ? `+${unit(n)}` : n < 0 ? `−${unit(-n)}` : unit(0)
const yearMonth = (month: string) => `${Number(month.slice(0, 4))}년 ${Number(month.slice(5, 7))}월`

/** 컨셉 보드 분석(1부의 세 번째 단계). 옛 이름은 "테스트 전 진단". 화면은 AnalysisReport(copy/analysis-report.ts와 함께 쓴다). */
export const diagnoseCopy = {
  title: "컨셉 보드 분석",
  alternative: "다음에 확인할 안",
  trend: "트렌드",
  history: "비슷한 과거 사례",
  price: "가격",
  competition: "경쟁 제품",
  distribution: "유통",
  empty: "확인할 자료가 없어요.",
  loading: "컨셉 보드 분석 자료를 확인하고 있어요.",
  unavailable: "지금은 분석 자료를 불러올 수 없어요.",
  retry: "자료 다시 불러오기",
  won,
  /** 머리의 규격과 가격: "500mL PET 1,800원" */
  spec: (spec: string, price: number | null | undefined) => [spec, price ? won(price) : ""].filter(Boolean).join(" "),

  // ① 핵심 인사이트: 걸린 점마다 [이어지는 꼴, 끝나는 꼴]. 코드가 이어 붙인다.
  insight: {
    cooled: ["수요는 한 해 전보다 식었고", "수요는 한 해 전보다 식었어요"],
    promoted: ["검색이 는 데는 광고·협찬의 몫이 크고", "검색이 는 데는 광고·협찬의 몫이 커요"],
    trend: ["검색 흐름에 살펴볼 점이 있고", "검색 흐름에 살펴볼 점이 있어요"],
    priceHigh: (little: boolean) => [
      `값은 소비자가 내겠다는 값보다 ${little ? "조금 " : ""}높고`,
      `값은 소비자가 내겠다는 값보다 ${little ? "조금 " : ""}높아요`,
    ],
    price: ["값에 살펴볼 점이 있고", "값에 살펴볼 점이 있어요"],
    shelf: (p: number) => [`진열할 수 있는 편의점은 ${pct(p)}뿐이고`, `진열할 수 있는 편의점은 ${pct(p)}뿐이에요`],
    history: ["비슷한 제품이 접힌 적이 있고", "비슷한 제품이 접힌 적이 있어요"],
    clear: "테스트를 막는 점은 없어요.",
  },

  // ② 숫자 줄
  noData: "자료 없음",
  tile: {
    trendVs: (season: string | null) => season ? `작년 ${season} 대비 검색` : "작년 정점 대비 검색",
    pct: (n: number) => signed(n, pct),
    priceVs: "소비자가 내겠다는 값 대비",
    priceVsLow: "같은 용량 제품 최저가 대비",
    gap: (n: number) => signed(n, won),
    cases: (n: number) => `${n}건`,
    similar: "비슷한 제품",
    share: (n: number) => pct(n),
    shelf: "진열할 수 있는 편의점",
  },

  // ③ 살펴볼 점의 제목
  chart: {
    searchPeak: (keyword: string, month: string) => `${keyword ? `${keyword} 검색은 ` : "검색은 "}${yearMonth(month)}이 정점이었어요`,
    priceOver: (gap: number) => `우리 가격은 소비자가 내겠다는 값보다 ${won(gap)} 높아요`,
    priceUnder: (gap: number) => `우리 가격은 소비자가 내겠다는 값보다 ${won(gap)} 낮아요`,
    priceSame: "우리 가격은 소비자가 내겠다는 값과 같아요",
    priceAboveAll: "우리 가격은 같은 용량 제품들보다 높아요",
    priceBelowAll: "우리 가격은 같은 용량 제품들보다 낮아요",
    priceAmong: "우리 가격은 같은 용량 제품들 사이에 있어요",
    priceOnly: "가격을 견줄 자료가 적어요",
  },

  // ④ 비슷한 과거 사례의 표
  table: { product: "제품", year: "연도", result: "결과", reason: "사유" },
  reasonNone: "기록 없음",
  reasonOther: "아이디어 보드에",

  // ⑤ 테스트할 안(버튼은 대화에 있다. 서버의 phrases.py와 같은 말)
  pick: {
    both: (a: number, b: number) => `${won(a)}과 ${won(b)} 둘 다 테스트`,
    only: (p: number) => `${won(p)}만 테스트`,
  },
  asIs: "이대로 테스트하기",
  // 기획자가 보내는 말(바꾸지 않는다)
  reply: { original: "원래 안만 테스트", both: "원래 안과 고친 안 둘 다 테스트", fix: "고친 안만 테스트" },

  // 옛 요약 문장을 화면에서 쉬운 말로 바꾼다(저장된 대화용)
  plain: [
    [/ ?트렌드 판정은 피크아웃이에요\.?/g, " 정점이 지났어요."],
    [/최대지불의향가격 중앙값/g, "소비자가 내겠다는 값(조사의 가운데 값)"],
    [/최대지불의향가격/g, "소비자가 내겠다는 값"],
    [/중앙값/g, "가운데 값"],
    [/상승기와 광고성 바이럴에 함께 해당해요/g, "찾는 사람이 늘었지만, 광고·협찬으로 늘어난 언급이 많아요"],
    [/광고성 바이럴을 제외한 다른 상승기 검색어/g, "광고·협찬을 빼고 검색이 늘고 있는 다른 검색어"],
    [/ · 사유 기록 없음/g, ". 사유는 기록에 없어요"],
    [/ · /g, ", "],
    [/피크아웃/g, "정점이 지남"],
    [/계절성 수요/g, "여름에만 찾음"],
    [/광고성 바이럴/g, "광고·협찬으로 늘어난 언급"],
    [/상승기/g, "찾는 사람이 느는 때"],
  ] as [RegExp, string][],
}
