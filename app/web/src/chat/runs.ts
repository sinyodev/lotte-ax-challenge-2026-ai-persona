/**
 * 매대 테스트의 진행과 결과(지시서 15). 카드가 GET /api/runs/{id}를 2초마다 읽고, 끝나면(running이 아니면) 멈춘다.
 * 읽지 못하면 조용히 다시 시도한다. 견본 페이지는 sample을 넘겨 서버를 부르지 않는다.
 */
import { useCallback, useEffect, useState } from "react"
import type { RunView } from "./contract"

export const RUN_POLL_MS = 2000
/** 이만큼 다녀가면 "먼저 온 결과 보기"가 열린다(서버의 phrases.SHELF_EARLY_AT과 같다). */
export const EARLY_RESULT_AT = 100

export function useRun(runId: string | null | undefined, sample?: RunView | null) {
  const [view, setView] = useState<RunView | null>(sample ?? null)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    if (sample || !runId) return
    let alive = true
    let timer: number | undefined
    const read = async () => {
      try {
        const res = await fetch(`/api/runs/${encodeURIComponent(runId)}`)
        if (res.ok) {
          const body = (await res.json()) as RunView
          if (!alive) return
          setView(body)
          if (body.status !== "running") return
        }
      } catch {
        // 조용히 다시 시도한다
      }
      if (alive) timer = window.setTimeout(read, RUN_POLL_MS)
    }
    void read()
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
  }, [runId, sample, tick])

  /** 멈추기: POST /api/runs/{id}/stop. 멈춘 뒤 한 번 다시 읽는다. */
  const stop = useCallback(async () => {
    if (!runId || sample) return
    await fetch(`/api/runs/${encodeURIComponent(runId)}/stop`, { method: "POST" }).catch(() => null)
    setTick((t) => t + 1)
  }, [runId, sample])

  /** 이어서 하기: POST /api/runs/{id}/resume. 저장된 답은 그대로 두고 남은 손님만 묻는다(11-25). */
  const resume = useCallback(async () => {
    if (!runId || sample) return
    await fetch(`/api/runs/${encodeURIComponent(runId)}/resume`, { method: "POST" }).catch(() => null)
    setTick((t) => t + 1)
  }, [runId, sample])

  return { view: sample ?? view, stop, resume }
}

/** "먼저 온 결과 보기"를 열 만큼 다녀갔는가. 인원이 100명보다 적으면 끝났을 때만. */
export function canSeeEarly(v: RunView) {
  return v.status === "running" && v.asked >= Math.min(EARLY_RESULT_AT, v.total) && v.asked < v.total
}
