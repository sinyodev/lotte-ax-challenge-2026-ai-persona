/**
 * 단계 표시줄과 작업대의 상태(Zustand).
 * 약속 3절대로 메시지들의 파트를 처음부터 차례로 읽어 만든다. 같은 id는 뒤의 것이 이기고, 자리는 처음 온 곳을 지킨다.
 * 멈춘 차례(metadata.stopped)의 단계와 카드는 읽지 않는다: 서버가 노트를 차례 앞으로 되돌리므로 작업대도 차례 앞의 모습이다(지시서 11).
 * 컨셉 보드 분석(analysis)은 화면에서만 있는 단계다: 분석 카드(kind diagnosis)는 서버가 concept로 보내도 analysis에 두고,
 * 서버의 단계가 concept인데 분석 카드가 와 있으면 지금 단계를 analysis로 본다.
 */
import { create } from "zustand"
import { isKnownPart, STAGE_IDS, type CardData, type ChilseongMessage, type StageId } from "./contract"

export type WorkCard = CardData & { id: string }

/**
 * 카드 안에서 고르기(약속 v1.2 choices.on_card). 카드 id마다 하나.
 * chosen이 null이면 아직 답하지 않았고(누를 수 있다), 배열이면 보낸 뒤다(고른 것만 표시가 남는다).
 */
export type CardPick = { choicesId: string; kind: "single" | "multi"; chosen: string[] | null }

export type Derived = {
  stage: StageId
  cards: WorkCard[]
  sample: boolean
  source: string | null
  picks: Record<string, CardPick>
}

export function deriveWorkbench(messages: ChilseongMessage[]): Derived {
  let stage: StageId = STAGE_IDS[0]
  let sample = false
  let source: string | null = null
  const cards = new Map<string, WorkCard>()
  const picks: Record<string, CardPick> = {}
  messages.forEach((m, idx) => {
    if (m.role !== "assistant") return
    const isStopped = Boolean(m.metadata?.stopped)
    const next = messages[idx + 1]
    for (const p of m.parts) {
      if (!isKnownPart(p)) continue
      if (isStopped && p.type !== "data-session") continue
      if (p.type === "data-stage") stage = p.data.current
      else if (p.type === "data-session") {
        sample = p.data.sample
        source = p.data.source
      } else if (p.type === "data-card" && p.id) {
        // 이전 버전은 인터뷰 질문을 제안하는 차례에도 변경안 목록을 같이 저장했다.
        if (p.data.kind === "improve" && m.parts.some(part => part.type === "data-choices" &&
          part.id === "w7-group" && part.data.options.some(o => o.id.startsWith('w7-group:["open",')))) {
          const run = (p.data.payload as { base_run?: string } | null)?.base_run
          if (run) {
            const id = `group-${run}`
            cards.delete(id)
            cards.set(id, { id, kind: "group", stage: "improve", title: "인터뷰 준비", status: "ready",
              payload: { demo: false, view: "setup", run_id: run, concept: "", questions: [], candidates: [], suggested: [] } })
            continue
          }
        }
        // 테스트의 카드는 다시 오면 맨 뒤로 옮긴다(작업대가 가장 최근에 본 테스트 하나만 보인다)
        if (["shelf-run", "result", "improve", "group"].includes(p.data.kind)) cards.delete(p.id)
        cards.set(p.id, { ...p.data, id: p.id, ...(p.data.kind === "diagnosis" ? { stage: "analysis" as const } : {}) })
      }
      else if (p.type === "data-choices" && p.id && p.data.on_card) {
        // 다음 기획자의 말이 이 질문의 답이면 고른 것, 직접 써서 답했으면 빈 배열(더 누를 수 없다)
        const reply = next?.role === "user" ? next.metadata?.reply : undefined
        const chosen = next ? (reply?.to === p.id ? reply.ids : []) : null
        picks[p.data.on_card] = { choicesId: p.id, kind: p.data.kind, chosen }
      }
    }
  })
  // forEach 안에서 바뀌므로 타입이 좁혀지지 않게 StageId로 읽는다
  if ((stage as StageId) === "concept" && [...cards.values()].some((c) => c.kind === "diagnosis")) stage = "analysis"
  return { stage, cards: [...cards.values()], sample, source, picks }
}

type State = Derived & {
  /** 지금 보고 있는 단계. null이면 진행 중인 단계를 본다. */
  viewStage: StageId | null
  /** 방금 열리거나 바뀐 카드. 잠깐 테두리를 강조하고 그 자리로 스크롤한다. */
  flash: { id: string; tick: number } | null
  /** 카드마다 마지막으로 본 내용(바뀐 것을 알아내려고 쓴다). */
  signatures: Record<string, string>
  /** 카드 안에서 고르는 중인 것. choices의 id마다 고른 항목의 id들. */
  pending: Record<string, string[]>
  togglePick: (choicesId: string, itemId: string, kind: "single" | "multi") => void
  /** quiet: 저장한 대화를 처음 펼칠 때. 바뀐 카드로 강조하거나 스크롤하지 않는다. */
  sync: (messages: ChilseongMessage[], quiet?: boolean) => void
  view: (stage: StageId | null) => void
  reset: () => void
}

const initial = {
  stage: STAGE_IDS[0] as StageId,
  cards: [] as WorkCard[],
  sample: false,
  source: null as string | null,
  picks: {} as Record<string, CardPick>,
  pending: {} as Record<string, string[]>,
  viewStage: null,
  flash: null,
  signatures: {} as Record<string, string>,
}

export const useWorkbench = create<State>((set, get) => ({
  ...initial,
  sync: (messages, quiet = false) => {
    const next = deriveWorkbench(messages)
    const prev = get()
    const signatures: Record<string, string> = {}
    let changedId: string | null = null
    for (const c of next.cards) {
      const sig = JSON.stringify(c)
      signatures[c.id] = sig
      if (prev.signatures[c.id] !== sig) changedId = c.id
    }
    const stageChanged = next.stage !== prev.stage
    if (quiet) changedId = null
    const changed = stageChanged || changedId !== null
    set({
      ...next,
      signatures,
      // 새 단계나 카드가 오면 진행 중인 단계로 돌아온다
      viewStage: changed ? null : prev.viewStage,
      flash: changedId ? { id: changedId, tick: (prev.flash?.tick ?? 0) + 1 } : prev.flash,
    })
  },
  togglePick: (choicesId, itemId, kind) => {
    const cur = get().pending[choicesId] ?? []
    const next =
      kind === "single"
        ? cur.includes(itemId)
          ? []
          : [itemId]
        : cur.includes(itemId)
          ? cur.filter((x) => x !== itemId)
          : [...cur, itemId]
    set({ pending: { ...get().pending, [choicesId]: next } })
  },
  view: (stage) => set({ viewStage: stage === get().stage ? null : stage }),
  reset: () => set(initial),
}))
