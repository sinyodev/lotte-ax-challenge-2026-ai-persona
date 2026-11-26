import type { Origin } from "./contract"

export type LegacyDiagnosisPayload = {
  trend: string
  history: string
  price: string
  competition: string
  distribution: string
  alternative: string
}

type DiagnosisDetail = {
  summary: string
  status: "flag" | "ok" | "missing"
  source: string | null
  details: string[]
}

export type DiagnosisPeak = { year: number; season: string; peak: number; slot: number }
export type DiagnosisRange = { count: number; low: number; high: number }
/** low·high는 상자 그림의 수염, accept는 [가격, 그 값 이상을 내겠다고 답한 사람 수]의 줄(100원마다). 옛 payload에는 없다. */
export type DiagnosisWtp = {
  n: number; spec: string; p25: number; median: number; p75: number
  low?: number; high?: number; accept?: [number, number][]
}

export type DiagnosisTrend = DiagnosisDetail & {
  id: "trend"
  peaks?: DiagnosisPeak[]
  stages?: string[]
  highlight?: string | null
  keyword?: string
  /** 달별 검색 지수(컨셉 보드 분석의 선 그래프). 옛 payload에는 없다. */
  series?: { month: string; search_index: number | null }[]
}
export type DiagnosisPrice = DiagnosisDetail & {
  id: "price"
  current?: number | null
  label?: string
  kind?: string | null
  spec?: string
  rivals?: DiagnosisRange | null
  same?: DiagnosisRange | null
  wtp?: DiagnosisWtp | null
  /** 같은 용기·용량 제품마다 가격 하나(컨셉 보드 분석의 가격 그림). 옛 payload에는 없다. */
  points?: { name: string; price: number }[]
}
/** 비슷한 과거 사례의 표 한 줄. reasons는 사유의 묶음 이름이고, 사유가 비었으면 null. 옛 payload에는 없다. */
export type DiagnosisHistoryRow = { name: string; year: number | null; status: string | null; reasons: string[] | null }
export type DiagnosisSection = DiagnosisTrend | DiagnosisPrice | DiagnosisDetail & {
  id: "history" | "distribution"
  link?: string
  stores?: number
  rate?: number
  storage?: string
  rows?: DiagnosisHistoryRow[]
}
export type DiagnosisFix = {
  id: string
  values: { price: number }
  reason: string
  hypothesis: string
  evidence: { origin: Origin; text: string }[]
}
export type DiagnosisPayload = {
  concept_id: string
  concept_name: string
  sections: DiagnosisSection[]
  fixes: DiagnosisFix[]
}

export type ComparisonQuote = { id: string; text: string; person: string; topic?: string } | null
export type ComparisonKind = "form" | "flavor" | "price"

export type ComparisonSelection = {
  n: number
  picked: number
  rate: number
  interval: [number, number]
}

export type PairedComparison = {
  gained: number
  lost: number
  difference: number
  interval: [number, number]
}

export type ComparisonPricePoint = { price: number; selection: ComparisonSelection }

export type ComparisonPayload = {
  demo: true
  focus?: ComparisonKind
  volumeMl: number
  base: ComparisonPricePoint
  variants: Record<ComparisonKind, { selection: ComparisonSelection; paired: PairedComparison }>
  priceStep: { source: "joined-shelf"; step: number; medianGap: number; rivalCount: number; distinctPrices: number }
    | { source: "demo"; step: number }
  pricePoints: [lower: ComparisonPricePoint, original: ComparisonPricePoint, higher: ComparisonPricePoint]
}
