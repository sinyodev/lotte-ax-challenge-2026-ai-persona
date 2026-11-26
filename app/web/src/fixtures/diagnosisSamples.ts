/**
 * 견본 자료. 견본 페이지(/design)에서 컨셉 보드 분석 카드의 세 경우를 보이려고 넣은 예시 값이다.
 * 실제 화면은 서버가 보낸 값만 그린다. 숫자, 달별 지수, 제품 이름과 가격은 모두 지어낸 견본이다.
 */
import type { DiagnosisPayload } from "../chat/contract-diagnose"
import type { WorkCard } from "../chat/workbenchStore"

// 지어낸 달별 검색 지수(2024-10 ~ 2026-09). 여름마다 솟고 2026년 여름은 2025년보다 낮다.
const months = Array.from({ length: 24 }, (_, i) => {
  const d = new Date(2024, 9 + i, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`
})
const shape: Record<string, number> = { "06": 0.45, "07": 1, "08": 0.6, "05": 0.25, "09": 0.2 }
const series = months.map((month) => {
  const top = month.startsWith("2025") ? 100 : month.startsWith("2026") ? 39 : 20
  return { month, search_index: Math.round(Math.max(6, top * (shape[month.slice(5)] ?? 0.08))) }
})

const trend = {
  id: "trend", status: "flag", source: "제공 검색·SNS 자료", keyword: "수박화채", highlight: "여름",
  summary: "수박화채의 여름(6~8월) 최고 검색 지수는 2025년 100, 2026년 39예요. 정점이 지났어요.",
  stages: ["피크아웃", "계절성 수요"],
  details: ["월별 검색·SNS 관측 기간은 2024-10~2026-09예요.", "두 해 모두 7월에 검색이 가장 많았어요."],
  peaks: [
    { year: 2025, season: "봄", peak: 33, slot: 8101 }, { year: 2025, season: "여름", peak: 100, slot: 8102 },
    { year: 2025, season: "가을", peak: 31, slot: 8103 }, { year: 2026, season: "봄", peak: 33, slot: 8105 },
    { year: 2026, season: "여름", peak: 39, slot: 8106 },
  ],
  series,
}

const price = (current: number, status: "flag" | "ok") => ({
  id: "price", status, source: "정량조사 · 편의점 매대", current, label: "권장 소비자가", kind: "탄산", spec: "500ml 페트",
  summary: `권장 소비자가는 ${current.toLocaleString("ko-KR")}원으로, 소비자가 내겠다는 값(조사의 가운데 값)과 같아요.`,
  details: ["같은 용기·용량 3종은 2,000원~2,600원이에요."],
  rivals: { count: 7, low: 1670, high: 2600 }, same: { count: 3, low: 2000, high: 2600 },
  wtp: { n: 240, p25: 1500, median: 1700, p75: 2000, spec: "500mL PET" },
  points: [{ name: "견본 사이다 500mL", price: 2000 }, { name: "견본 콜라 500mL", price: 2300 }, { name: "견본 에이드 500mL", price: 2600 }],
})

const history = {
  id: "history", status: "ok", source: "아이디어 보드", link: "/ideas",
  summary: "밀키스 수박 500mL(2021년, 시즌 한정)이 단종된 적이 있어요. 사유는 기록에 없어요.",
  details: ["밀키스 딸기 500mL PET(2025년, 시즌 한정)가 단종된 적이 있어요. 사유는 계획된 종료예요."],
  rows: [
    { name: "밀키스 수박 500mL", year: 2021, status: "단종", reasons: null },
    { name: "밀키스 딸기 500mL PET", year: 2025, status: "단종", reasons: ["계획된 종료"] },
  ],
}

const distribution = {
  id: "distribution", status: "ok", source: null, storage: "상온", summary: "상온 보관 제품이라 냉장·냉동 진열 설비가 필요 없어요.",
  details: ["제공된 유통 인프라에는 상온 제품의 진열 가능 점포율이 없어요."],
}

const fix = {
  id: "price-1700", values: { price: 1700 },
  reason: "소비자가 내겠다는 값(조사의 가운데 값)을 참고해 1,700원에 테스트해요.",
  hypothesis: "가격을 낮추면 매대에서 고르는 사람이 늘 수 있어요.",
  evidence: [{ origin: "internal", text: "2026년 10월 정량조사에서 500mL PET에 최대 얼마까지 내겠는지 답한 240명의 가운데 값은 1,700원, 가운데 절반은 1,500원~2,000원이에요." }],
}

const card = (id: string, payload: object): WorkCard =>
  ({ id, kind: "diagnosis", stage: "analysis", title: "컨셉 보드 분석", status: "ready", payload: payload as DiagnosisPayload }) as WorkCard

export const diagnosisFlags = card("diagnosis-flags", {
  concept_id: "a", concept_name: "밀키스 화채",
  sections: [trend, price(1800, "flag"), history, distribution], fixes: [fix],
})

export const diagnosisClear = card("diagnosis-clear", {
  concept_id: "b", concept_name: "밀키스 화채",
  sections: [{ ...trend, status: "ok", stages: ["계절성 수요"] }, price(1700, "ok"), history, distribution], fixes: [],
})

export const diagnosisNoFix = card("diagnosis-nofix", {
  concept_id: "c", concept_name: "레쓰비 프리즈",
  sections: [
    { id: "distribution", status: "flag", source: "제공 유통 인프라", stores: 800, rate: 0.31, storage: "냉동",
      summary: "편의점 800곳 기준 냉동 음료 진열 가능 점포율은 31%예요.", details: ["제공 자료의 편의점 전체를 분모로 집계했어요."] },
    history,
  ],
  fixes: [],
})
