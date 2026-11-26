export const ideaStatuses = [
  "기획 중", "가상 테스트 중", "가상 테스트 완료", "소비자 조사 진행", "정성 조사 중", "정량 조사 중",
  "출시", "보류", "폐기", "단종",
] as const
export type IdeaStatus = typeof ideaStatuses[number]

export const ideaCheckKeys = ["virtual_test", "qual", "quant", "launched"] as const
export type IdeaChecks = Record<typeof ideaCheckKeys[number], boolean>

export type IdeaRow = {
  id: string
  name: string
  brand: string | null
  category: string | null
  pack: string | null
  price: string | null
  owner: string | null
  concept: string | null
  launched_on: string | null
  last_work: string | null
  work_date: string | null
  status: IdeaStatus
  checks: IdeaChecks
  last_test: { selection_rate: number | null; own_share: number | null; virtual_sales: string | null } | null
  verdict: string | null
  reason: string | null
  trend: string | null
  started: string | null
  updated: string | null
  source: "chat" | "assets" | "import" | "manual" | "concept"
  attachment_count: number
  chat_id: string | null
}

export type IdeaMatch = IdeaRow & { score: number; matches: string[] }

export type IdeaPatch = Partial<Pick<IdeaRow,
  "name" | "status" | "verdict" | "reason" | "owner" | "concept" | "launched_on"
>> & { checks?: Partial<IdeaChecks> }
export type IdeaLog = { id: string; at: string; text: string; filename: string | null }
export type IdeaLaunch = { name: string; row_id: string; launched_on: string }

export type IdeasDashboard = {
  status_counts: Record<IdeaStatus, number>
  funnel: { ideas: number; virtual_test: number; research: number; launched: number }
  skipped_research_count: number
  max_saved_won: number
  reason_counts: Record<string, number>
  brand_counts: Record<string, number>
  category_counts: Record<string, number>
  recent: IdeaRow[]
  launches: IdeaLaunch[]
  undated_launches: number
}

export type IdeaImportPreview = {
  items: { row: IdeaRow; missing: string[]; duplicates: { id: string; name: string }[] }[]
  warnings: string[]
}

export async function ideaRequest<T>(path = "", options?: { method: "POST" | "PATCH"; body: unknown } | { signal: AbortSignal }) {
  const response = await fetch(`/api/ideas${path}`, options && "method" in options ? {
    method: options.method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options.body),
  } : options)
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null
    throw new Error(typeof body?.detail === "string" ? body.detail : "")
  }
  return response.json() as Promise<T>
}
