/**
 * 약속(app/contract/README.md, v1.7)의 형식을 화면 쪽에서 옮긴 것. 약속이 바뀌면 여기도 바꾼다.
 * 화면은 이 형식만 보고 그린다. 대본의 내용(제품 이름, 숫자)을 알지 않는다.
 */
import type { UIMessage } from "ai"

/**
 * "analysis"(컨셉 보드 분석)는 화면에서만 있는 단계다. 서버는 보내지도 받지도 않는다:
 * 서버의 단계가 concept인데 컨셉 보드 분석 카드(kind diagnosis)가 와 있으면 화면이 analysis로 읽는다(workbenchStore).
 */
export const STAGE_IDS = ["idea", "concept", "analysis", "shelf", "result", "improve", "report", "followup"] as const
export type StageId = (typeof STAGE_IDS)[number]
/** 서버가 보내는 단계(약속). */
export type ServerStageId = Exclude<StageId, "analysis">

/** 일의 두 부분(약속 v1.1): 1부 컨셉 기획, 2부 매대 테스트. 단계의 이름은 그대로다. */
export const PART_IDS = ["concept", "test"] as const
export type PartId = (typeof PART_IDS)[number]
export const PART_STAGES: Record<PartId, readonly StageId[]> = {
  concept: ["idea", "concept", "analysis"],
  test: ["shelf", "result", "improve", "report", "followup"],
}

export type CardKind = "brief" | "evidence" | "ideas" | "concepts" | "shelf-run" | "result" | "improve" | "report" | "explore" | "trend" | "history" | "group" | "diagnosis" | "followup"

export type BriefPayload = {
  fields: {
    key: "product" | "channel" | "target" | "occasion" | "need"
    label: string
    value: string | null
    note?: string
    state: "set" | "asking" | "empty"
  }[]
  /** 기획자가 넣은 방향("아침용", "유자"). 약속 v1.3. */
  thoughts?: string[]
}
/** 근거 표시(약속 v1.2): 소비자 기록, 편의점 매출, 매대, 웹에서 찾은 것, 칠성이의 제안. */
export const ORIGINS = ["record", "sales", "shelf", "web", "suggestion", "internal"] as const
export type Origin = (typeof ORIGINS)[number]

export type EvidenceItem = {
  id: string
  origin: Origin
  text: string
  source: string
  url?: string
  date?: string
  note?: string
}
export type EvidencePayload = { items: EvidenceItem[] }

/** 지시서 33: 규격 하나. 값이 있는 칸만 온다. price는 권장 소비자가, factory_price는 출고가. */
export type VariantRow = {
  label: string
  volume_ml?: number
  price?: number
  factory_price?: number
  shelf_life_months?: number
  shelf_life_days?: number
  kcal?: number
}
/** 제품 사양의 칸(아이디어와 컨셉이 함께 쓴다). */
export type ProductSpec = Pick<IdeaItem, "variants" | "shelf_variant" | "launch" | "season" | "channels" | "storage" | "estimated">
export type IdeaItem = {
  id: string
  name: string
  flavor: string
  pack: string
  features: string[]
  line: string
  diff: string
  /** 누가 낸 것인지(약속 v1.3). */
  by?: "chilseong" | "planner"
  /** 기획자가 남기기로 한 것(약속 v1.3). */
  kept?: boolean
  /** 방금 고쳐진 칸의 이름: "name", "flavor", "pack", "features", "line"(약속 v1.3). */
  changed?: string[]
  /** 지시서 33: 제품 사양(없어도 되는 칸). variants는 규격의 표, shelf_variant는 매대에 올릴 규격의 차례. */
  variants?: VariantRow[]
  shelf_variant?: number
  /** 유통기한·열량이 칠성이가 어림한 값이면 true. */
  estimated?: boolean
  launch?: string
  season?: string
  channels?: string[]
  storage?: string
}
export type IdeasPayload = { basis: string; items: IdeaItem[] }
/** 컨셉 카드의 제품 특징 한 줄(약속 v1.4). key로 컨셉끼리 같은 줄을 맞춘다. 값 안의 줄바꿈(\n)은 줄을 나눠 그린다. */
export type SpecRow = { key: string; label: string; value: string }
/**
 * 컨셉 한 장(약속 v1.4): 위쪽 예시 시안(headline, name, benefit, points, price, pack)과 아래쪽 제품 특징(spec).
 * 저장된 옛 대화에는 옛 형식(v1.3)의 컨셉이 있을 수 있어서 v1.4의 칸도 없을 수 있다고 본다(있는 것만 그린다).
 */
export type ConceptItem = {
  id: string
  name: string
  headline?: string
  benefit?: string
  points?: string[]
  price?: string
  pack?: string
  spec?: SpecRow[]
  /** 11-25: 소비자 인식 한 문장(타깃의 채워지지 않은 니즈). 옛 컨셉에는 없다. */
  insight?: string
  /** 11-25: 보드가 둘 이상일 때 확정한 보드. */
  confirmed?: boolean
  /** 방금 고쳐진 것의 이름: headline, name, benefit, points 또는 spec의 key(약속 v1.4). */
  changed?: string[]
  /** 지시서 33: 제품 사양(없어도 되는 칸). variants는 규격의 표, shelf_variant는 매대에 올릴 규격의 차례. */
  variants?: VariantRow[]
  shelf_variant?: number
  /** 유통기한·열량이 칠성이가 어림한 값이면 true. */
  estimated?: boolean
  launch?: string
  season?: string
  channels?: string[]
  storage?: string
}
/** locked: 확정한 뒤라 매대에 올릴 규격을 고를 수 없다(지시서 33 후속). */
export type ConceptsPayload = { items: ConceptItem[]; locked?: boolean }
/**
 * 매대 테스트 카드(약속 v1.6, 지시서 15). 숫자는 대화에 박아 두지 않고 카드가 GET /api/runs/{run_id}에서 읽는다.
 * who는 "20대 손님"처럼 누구에게 묻는지.
 */
export type ShelfRunPayload = {
  run_id: string
  concept: { name: string; pack: string; container: string; volume: number; price: number }
  who: string
}
/** 결과 카드(약속 v1.6). 숫자는 카드가 GET /api/runs/{run_id}에서 읽는다. */
export type ResultPayload = { run_id: string }

/** GET /api/runs/{id}(지시서 15의 1절). 화면이 2초마다 읽는다. */
export type RunStatus = "running" | "done" | "stopped" | "failed"
export type RunQuote = { visitor: string; who: string; occasion: string; said: string; chose: string }
export type RunResult = {
  n: number
  picked: number
  /** 윌슨 95% 구간(%) */
  low: number
  high: number
  rank: number | null
  products: number
  neighbors: { name: string; picked: number; ours: boolean; self: boolean }[]
  from: { rival: { name: string; count: number }[]; own: { name: string; count: number }[]; none: number; pending?: number }
  views: { label: string; count: number }[]
  barriers: { label: string; count: number }[]
  by_occasion: { occasion: string; n: number; picked: number }[]
  quotes: { picked: RunQuote[]; passed: RunQuote[] }
}
export type RunView = {
  id: string
  status: RunStatus
  concept: { id: string; name: string; pack: string; container: string; volume: number; price: number; promo: string | null }
  who: { label: string; occasion: string | null; occasion_share: number | null }
  asked: number
  total: number
  skipped: number
  started_at: string
  updated_at: string
  model: string
  result: RunResult | null
}
export type { ImproveKind, ImproveItem, ImprovePayload } from "./contract-improve"
export type ReportPayload = { sections: { title: string; body: string }[] }

/**
 * 칠성이가 아닌 화자(약속 v1.7 say.speaker). 글 파트의 providerMetadata.chilseong.speaker에 실려 온다.
 * 지금은 테스트의 손님 한 명뿐이다. label은 "24세 여자, 대학생".
 */
export type Speaker = { kind: "shopper"; label: string }
export function speakerOf(part: { providerMetadata?: unknown }): Speaker | null {
  const meta = part.providerMetadata as { chilseong?: { speaker?: Speaker } } | undefined
  const sp = meta?.chilseong?.speaker
  return sp && sp.kind === "shopper" && typeof sp.label === "string" ? sp : null
}

/** 자료 파트의 data: 칠성이의 이벤트에서 t와 id를 뺀 나머지(약속 3절). */
export type ActivityData = { label: string; status: "running" | "done" }
export type ChoicesData = {
  kind: "single" | "multi"
  options: { id: string; label: string; note?: string }[]
  /** 있으면 마지막에 직접 쓰는 칩. 누르면 입력창으로 간다(약속 v1.2). */
  free?: { label: string }
  /** 있으면 그 id의 카드 안에서 고른다. options의 id = 카드 항목의 id(약속 v1.2). */
  on_card?: string
}
export type ActionsData = { actions: { id: string; label: string; note?: string; primary?: boolean }[] }
export type ConfirmData = {
  title: string
  desc?: string
  rows: { label: string; value: string; note?: string }[]
  confirm: { id: string; label: string }
  cancel: { id: string; label: string }
}
export type SummaryData = { title: string; value: string; note?: string }
export type StageData = { current: ServerStageId }
export type CardData = {
  stage: StageId
  kind: CardKind
  title: string
  status: "loading" | "ready" | "error"
  payload: unknown
  /** 카드 전체의 근거 표시(약속 v1.2). */
  origin?: Origin
}
export type SessionData = { source: "replay" | "live" | string; sample: boolean }

export type ChilseongDataTypes = {
  activity: ActivityData
  choices: ChoicesData
  actions: ActionsData
  confirm: ConfirmData
  summary: SummaryData
  stage: StageData
  card: CardData
  session: SessionData
}

/**
 * 기획자의 답에 붙이는 메타데이터(약속 4절). 직접 써서 보낸 말에는 reply가 없다.
 * stopped는 약속에 없는 것: 멈춘 칠성이의 차례에 화면이 붙이고, 서버가 저장한 대화를 돌려줄 때도 붙인다(지시서 11).
 */
export type MessageMeta = { reply?: { to: string; ids: string[] }; stopped?: boolean }

export type ChilseongMessage = UIMessage<MessageMeta, ChilseongDataTypes>
export type ChilseongPart = ChilseongMessage["parts"][number]

/** 진행 방식(약속 4절). */
export type Mode = "manual" | "suggest" | "delegate"

const KNOWN_DATA = new Set(["activity", "choices", "actions", "confirm", "summary", "stage", "card", "session"])
/** 화면이 그리지 않는 AI SDK의 기본 파트. 경고하지 않는다. */
const IGNORED_PARTS = new Set(["step-start", "text"])

const warned = new Set<string>()
/** 모르는 종류는 무시하고 콘솔에 한 번만 경고한다(약속 1절). */
export function isKnownPart(part: { type: string }): boolean {
  if (IGNORED_PARTS.has(part.type)) return true
  if (part.type.startsWith("data-") && KNOWN_DATA.has(part.type.slice(5))) return true
  if (!warned.has(part.type)) {
    warned.add(part.type)
    console.warn(`[chilseong] ignoring unknown part: ${part.type}`)
  }
  return false
}

/** 신제품 제안서(지시서 14, GET /api/chats/{id}/proposal). 글은 서버가 보고서체로 보낸 그대로 쓴다. */
export type ProposalRow = { role: "proposal" | "rival" | "own"; name: string; pack: string; price: string; promo: string }
export type ProposalPage = {
  concept_id: string
  title: string
  gist: string
  background: { text: string; refs: number[] }[]
  overview: { label: string; value: string }[]
  sketch: { headline: string; name: string; benefit: string; points: string[]; price: string; pack: string }
  /** 컨셉 보드에서 만든 예시 이미지의 주소. 만들지 않았으면 null(옛 서버는 보내지 않는다). */
  image?: string | null
  compare: { rows: ProposalRow[]; pod: string | null; range: string | null }
  /**
   * 매대 테스트 결과 보고(지시서 22, 약속 v1.13). 그 컨셉의 테스트가 100명 이상 다녀갔을 때만 온다(없으면 null).
   * 문장은 모두 서버가 만든 보고서체 그대로다. 옛 서버(v1.7의 lines 모양)가 보낸 것은 isReportTest로 걸러 쓰지 않는다.
   */
  test?: ReportTest | Record<string, unknown> | null
  plan: string[]
  sources: { n: number; text: string }[]
  notice: string
  /** 맨 아래 알림의 줄들(notice와 테스트를 했으면 한 줄 더). 옛 서버는 보내지 않는다. */
  notices?: string[]
}
export type Proposal = { date: string; dept: string; pages: ProposalPage[] }

/** 결과 보고서의 칸(약속 v1.13). */
export type ReportTest = {
  review: { text: string; tone: "weak" | "cannibal" | "ok" }
  overview: string[]
  findings: string[]
  inflow: { label: string; n: number; share: string }[]
  compare: {
    name: string
    change: string
    n: number
    rank: number | null
    rate: number
    value: string
    verdict: "base" | "better" | "same" | "worse"
    best: boolean
    line: string | null
  }[]
  voices: {
    picked: { factor: string; quote: string; who: string } | null
    passed: { factor: string; n: number; quote: string | null; who: string | null; others: string | null } | null
  }
  plans: { title: string; body: string }[]
  caution: string
}

/** 새 모양(v1.13)의 결과 보고서인지. 옛 서버가 보낸 v1.7 모양은 아니라고 본다. */
export function isReportTest(x: ProposalPage["test"]): x is ReportTest {
  return Boolean(x && typeof x === "object" && "review" in x && "plans" in x)
}
