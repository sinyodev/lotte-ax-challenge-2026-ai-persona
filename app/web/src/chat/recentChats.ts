/**
 * 최근 대화(왼쪽 메뉴): 서버의 GET /api/chats가 주는 실제 목록(지시서 11).
 * 차례가 시작하고 끝날 때마다 다시 받는다(refresh). 지우기는 DELETE /api/chats/{id}.
 */
import { create } from "zustand"
import { PART_STAGES, type PartId, type StageId } from "./contract"

/** working: 칠성이가 일하는 중, waiting: 기획자의 답을 기다림, idle: 그 밖 */
export type RecentChatStatus = "working" | "waiting" | "idle"

export type RecentChat = {
  id: string
  title: string
  /** 마지막으로 말이 오간 때 */
  updatedAt: Date
  status: RecentChatStatus
  /** 어느 부분의 대화인지, 그 부분의 몇 번째 단계까지 왔는지 */
  part: PartId
  step: number
  /** 확정한 컨셉(첫 화면의 매대 테스트 쪽, 지시서 15). 확정하지 않았으면 빈 목록. */
  concepts: ApiConcept[]
}

/** 확정한 컨셉 한 줄. container는 서버의 말("캔", "페트", "병", "팩", "컵") 그대로. */
export type ApiConcept = { id: string; name: string; container: string; pack: string; price: string }

/** 서버가 주는 한 줄 */
type ApiChat = {
  id: string
  title: string
  updated_at: string | null
  part: string
  stage: string
  status: string
  concepts?: ApiConcept[]
}

/** 최근 대화 한 줄의 주소. 부분마다 주소가 다르다. */
export const recentChatHref = (c: { id: string; part: PartId }) => `/${c.part}/${c.id}`

/**
 * 지금 주소가 이 대화인가. 2부로 넘어간 대화는 목록에서 /test/…이지만 열려 있는 화면은 /concept/…일 수 있다(그 반대도).
 * 두 주소 모두에서 선택 표시가 되게 대화 id로 견준다(지시서 17의 D).
 */
export function isChatPath(pathname: string | undefined, id: string) {
  if (!pathname) return false
  const m = /^\/(concept|test)\/([^/]+)\/?$/.exec(pathname)
  return Boolean(m) && decodeURIComponent(m![2]) === id
}

function fromApi(c: ApiChat): RecentChat {
  const part: PartId = c.part === "test" ? "test" : "concept"
  const step = Math.max(0, PART_STAGES[part].indexOf(c.stage as StageId))
  const status: RecentChatStatus = c.status === "working" || c.status === "waiting" ? c.status : "idle"
  return {
    id: c.id,
    title: c.title,
    updatedAt: c.updated_at ? new Date(c.updated_at) : new Date(),
    status,
    part,
    step,
    concepts: c.concepts ?? [],
  }
}

type State = {
  chats: RecentChat[]
  refresh: () => Promise<void>
  remove: (id: string) => Promise<boolean>
}

let inflight: Promise<void> | null = null

export const useRecentChats = create<State>((set, get) => ({
  chats: [],
  refresh: () => {
    // 한꺼번에 여러 번 불려도 한 번만 받는다
    if (inflight) return inflight
    inflight = fetch("/api/chats")
      .then((r) => (r.ok ? (r.json() as Promise<ApiChat[]>) : Promise.reject(r.status)))
      .then((rows) => set({ chats: rows.map(fromApi) }))
      .catch(() => {
        // 서버가 꺼져 있으면 목록을 그대로 둔다
      })
      .finally(() => {
        inflight = null
      })
    return inflight
  },
  remove: async (id) => {
    const res = await fetch(`/api/chats/${encodeURIComponent(id)}`, { method: "DELETE" }).catch(() => null)
    if (!res || !res.ok) return false
    set({ chats: get().chats.filter((c) => c.id !== id) })
    return true
  },
}))
