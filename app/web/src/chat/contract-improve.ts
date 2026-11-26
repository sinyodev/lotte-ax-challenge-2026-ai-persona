export type ImproveKind = "price" | "name" | "pack" | "promo" | "flavor" | "form" | "container" | "appeal" | "volume"

export type ImproveEvidence = { origin: string; text: string; quote_id?: string; session_id?: string }
export type ImproveGroup = { label: string; count: number }

export type ImprovePaired = {
  n: number
  both: number
  gained: number
  lost: number
  neither: number
  /** 선택률(%). 차이와 차이의 구간은 %p. */
  original_rate: number
  changed_rate: number
  delta_pp: number
  low_pp: number
  high_pp: number
  verdict: "more" | "less" | "unclear"
  gained_groups?: ImproveGroup[]
  lost_groups?: ImproveGroup[]
}

type SalesRange = [low: number, mid: number, high: number]

/** W6 sales.estimate의 집계. 금액 단위는 원이다. */
export type ImproveSales = {
  monthly?: { month: string; amount: SalesRange }[]
  season_total?: { amount: SalesRange }
  assumptions?: string[]
}

export type ImprovePricePoint = {
  price: number
  /** 해당 가격의 매대 테스트 선택률(%). 집계 중이거나 결과가 없으면 null. */
  rate: number | null
  n: number
  picked: number
  run_id?: string
  sales?: ImproveSales
}

export type ImproveItem = {
  id: string
  change: string
  reason: string
  run_id?: string
  kind?: ImproveKind
  before?: string
  after?: string
  // 저장된 옛 카드에는 가설, 근거, 짝지은 비교가 없다.
  hypothesis?: string
  evidence?: ImproveEvidence[]
  edit_values?: Record<string, string | number>
  paired?: ImprovePaired
}

export type ImprovePayload = {
  base_run: string
  items: ImproveItem[]
  price_curve?: ImprovePricePoint[]
  adopted_item_id?: string | null
  /** 카드를 열면 먼저 보일 안(조사에서 나온 첫 안, 약속 v1.20). */
  focus_id?: string | null
}
