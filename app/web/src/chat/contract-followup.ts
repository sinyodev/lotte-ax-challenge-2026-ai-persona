/** 후속 개선(약속 v1.20)의 형식. */
import { useEffect, useState } from "react"

export const UPLOAD_SURVEY = "upload-survey"
export const FOLLOWUP_TO = "followup"
export const SURVEY_MAX_BYTES = 8 * 1024 * 1024

export type FollowupOpinion = { text: string; n: number; intent: number }
export type FollowupDiff = {
  id: "price" | "worry" | "hope"
  text: string
  actual: number
  actual_n: number
  virtual: number | null
  virtual_n: number | null
}
export type FollowupPayload = {
  upload_id: string
  step: "diff" | "applied" | "retest" | "ideas"
  concept: { id: string; name: string; price: number }
  target: string
  n: { raw: number; clean: number; target: number }
  removed: { label: string; count: number }[]
  diffs: FollowupDiff[]
  note: string
  curve: { price: number; share: number; money: number }[]
  best_price: number | null
  opinions: { good: FollowupOpinion[]; bad: FollowupOpinion[] }
  track: { total: number; original: number | null; retest: number | null; improved: number | null }
  base_run: string
  retest_run: string | null
  can_retest: boolean
  /** 최적화한 가상 소비자의 집계(%). 아직 맞추지 않았으면 null. */
  fit?: { n: number; priced: number; diffs: Record<string, number> } | null
  /** 최적화로 나온 개선안(개선안 걸음에만). */
  ideas?: FollowupIdea[]
  /** 최적화한 가상 소비자를 가상 소비자 인사이트에 추가했는가. */
  saved?: boolean
}

export type FollowupIdea = {
  kind: string
  before: string
  after: string
  change: string
  reason: string
  evidence: string
  effect: { kind: "price"; before: number; after: number } | { kind: "worry"; n: number; total: number } | { kind: "hope"; label: string; n: number; total: number } | null
}

export type FollowupPerson = {
  id: string
  who: string
  lines: string[]
  before: boolean
  after: boolean | null
  said: string
}
export type FollowupPeople = {
  status: string
  total: number
  asked: number
  before: { n: number; picked: number }
  after: { n: number; picked: number }
  people: FollowupPerson[]
}

const POLL_MS = 2000

/** 다시 테스트한 가상 소비자들. 테스트가 도는 동안 2초마다 다시 읽는다. */
export function useFollowupPeople(uploadId: string, enabled: boolean, sample?: FollowupPeople | null) {
  const [data, setData] = useState<FollowupPeople | null>(null)
  useEffect(() => {
    if (!enabled || sample) return
    let alive = true
    let timer: number | undefined
    const read = async () => {
      try {
        const res = await fetch(`/api/followup/${encodeURIComponent(uploadId)}/people`, { cache: "no-store" })
        if (!alive || res.status === 404) return
        if (res.ok) {
          const body = (await res.json()) as FollowupPeople
          if (!alive) return
          setData(body)
          if (body.status !== "running") return
        }
      } catch {
        // 조용히 다시 시도한다
      }
      if (alive) timer = window.setTimeout(read, POLL_MS)
    }
    void read()
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
  }, [uploadId, enabled, sample])
  return sample ?? data
}

/** 조사 파일을 올리고 올림 번호를 받는다. 실패하면 화면에 낼 한 문장을 던진다. */
export async function uploadSurvey(chatId: string, file: File, messages: { tooBig: string; failed: string }) {
  if (file.size > SURVEY_MAX_BYTES) throw new Error(messages.tooBig)
  const content = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "")
    reader.onerror = () => reject(new Error(messages.failed))
    reader.readAsDataURL(file)
  })
  const res = await fetch("/api/followup/upload", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, filename: file.name, content_base64: content }),
  })
  const body = (await res.json().catch(() => null)) as { upload_id?: string; detail?: unknown } | null
  if (!res.ok || !body?.upload_id) throw new Error(typeof body?.detail === "string" ? body.detail : messages.failed)
  return body.upload_id
}
