import type { RunView } from "./contract"

export type ExplorePayload = { run_id: string }

export const EXPLORE_RESULT = "explore-result"

export type RunUsage = {
  elapsed_s: number
  calls: number
  input_tokens: number | null
  output_tokens: number | null
  est_cost_krw: number | null
  est_cost_usd: number | null
  priced_as: string | null
}

export type ShelfPlacement = { storage: string; store_rate: number | null }

type ExploreGroup = { age: string; sex: string; label: string }

export type ExploreCell = ExploreGroup & {
  total: number
  n: number
  picked: number
  rate: number | null
  low: number | null
  high: number | null
}

export type ExploreAxisGroup = { key: string; label: string; n: number; picked: number; rate: number | null }

/** 성별(두 그룹)·연령대(네 그룹)로 묶은 판정. clear가 null이면 응답이 덜 찼거나 적어 판정하지 않았다. */
export type ExploreAxis = {
  axis: "sex" | "age"
  groups: ExploreAxisGroup[]
  clear: boolean | null
  stat: number | null
  test: string
}

export type ExploreResult = {
  cells: ExploreCell[]
  occasions: { occasion: string; n: number; picked: number; rate: number | null }[]
  overall_rate: number | null
  weighting: "population" | "equal"
  suggested: ExploreGroup | null
  overlap: boolean
  /** 옛 실행에는 없다. */
  axes?: { sex: ExploreAxis; age: ExploreAxis }
}

/** 요약 구역의 버튼이 하는 일(지시서 32): 대화에 그 버튼을 누른 말을 보내거나, 작업대의 단계로 간다. */
export type BriefDo = { say: string; to: string; ids: string[] } | { stage: "concept" }

/** 테스트 결과 맨 위의 요약 구역(지시서 32의 A). 글은 서버가 만든다. 없을 수 있다(옛 서버, 탐색·개선안의 테스트). */
export type ResultBrief = {
  headline: string
  range: string
  points: {
    key: string
    value: string
    text: string
    bar?: { label: string; n: number; self: boolean }[]
    of?: number
    stacked?: boolean
  }[]
  actions: { id: string; reason: string | null; label: string; do: BriefDo }[]
  /** 타깃의 표기("19~29세"). 옛 서버에는 없다. */
  group?: string
  /** 컨셉을 올린 매대에서 가장 많이 고른 제품(많아야 여섯, 컨셉이 그 밖이면 끝에 붙는다). 옛 서버에는 없다. */
  top?: { name: string; picked: number; ours: boolean; self: boolean }[]
  /** 도는 중일 때만: 끝나기까지 남은 초. 셀 수 없으면 null. */
  eta_s?: number | null
}

/** 도는 테스트의 기다리는 화면(11-25). status가 running일 때만 온다. 옛 서버에는 없다. */
export type RunWaitingGuest = {
  visit: string
  age: string
  sex: string
  occasion: string | null
  chose: string
  said: string
  ours: boolean
}
export type RunWaitingLead =
  | { kind: "group"; age: string; sex: string; picked: number; n: number }
  | { kind: "target"; picked: number; n: number; name: string }
export type RunWaiting = {
  mode: "target" | "explore" | "improve"
  /** 한 손님에게 두 매대를 묻는다. 답 하나가 한 걸음(저장해 둔 답을 다시 쓴 것 포함) */
  steps_done: number
  steps_total: number
  /** 컨셉이 있는 매대의 답이 온 손님 */
  visited: number
  /** 두 매대의 답이 모두 온 손님 */
  complete: number
  /** 지금까지의 속도로 계산한 남은 초. 아직 모르면 null */
  eta_s: number | null
  lead: RunWaitingLead | null
  recent: RunWaitingGuest[]
}

/** GET /api/runs/{id}. The additional fields may be absent from older runs. */
export type ShelfRunView = RunView & {
  waiting?: RunWaiting
  brief?: ResultBrief
  requested?: number
  usage?: RunUsage
  placement?: ShelfPlacement | null
  target_basis?: string | null
  explore?: ExploreResult
}

/**
 * 결과 보고서(지시서 32의 B). 제안서 종이의 test 칸에 온다(kind: "result-report"). 글은 모두 서버가 만든 보고서체 그대로다.
 * 첫 장(head~disclaimer) → 근거(evidence) → 다음 실제 조사의 조건(next) → 부록(appendix).
 * evidence.voices와 evidence.compare는 이름 붙은 자리다(W7, W6이 더한다). compare가 비어 있으면 그리지 않는다.
 */
export type ResultReport = {
  kind: "result-report"
  chat_id?: string | null
  head: { title: string; product: string; spec: string }
  recommend: { verdict: "research" | "retest" | "hold"; text: string; reasons: string[] }
  decisions: string[]
  key: { key: string; label: string; value: string; note: string | null }[]
  limits: string[]
  opinion: string
  disclaimer: string
  evidence: {
    who: { lines: string[]; cells: { label: string; n: number; picked: number; rate: number | null }[] }
    from: { rows: { key: string; label: string; n: number; top: { name: string; count: number }[] }[]; note: string | null }
    barriers: { label: string; n: number }[]
    variants: {
      name: string
      change: string
      n: number
      rank: number | null
      rate: number
      value: string
      verdict: "base" | "better" | "same" | "worse"
      pair?: import("./contract-improve").ImprovePaired
      adopted?: boolean
      best: boolean
      line: string | null
    }[]
    voices: { factor: string; quote: string; who: string | null }[]
    compare: { title: string; lines: string[] }[]
  }
  next: { target: string; questions: string[]; conditions: string[]; unknowns: string[] }
  appendix: { method: string[]; records: string[]; rules: string[] }
}

export function isResultReport(x: unknown): x is ResultReport {
  return Boolean(x && typeof x === "object" && (x as { kind?: unknown }).kind === "result-report")
}
