/**
 * 테스트가 도는 동안의 기다리는 화면(11-25). 탐색 카드와 타깃 테스트 카드가 같이 쓴다.
 * 무엇을 하는지(머리), 어디까지 왔는지(막대), 언제 끝나는지(남은 시간), 먼저 온 결과(지금까지의 한 줄, 방금 다녀간 손님),
 * 떠나도 된다는 말. 숫자는 모두 서버의 waiting 칸(옛 서버면 asked/total)에서 온다.
 */
import { useEffect, useRef, type ReactNode } from "react"
import { Badge } from "@astryxdesign/core/Badge"
import { ProgressBar } from "@astryxdesign/core/ProgressBar"
import { Text } from "@astryxdesign/core/Text"
import type { RunWaitingGuest, ShelfRunView } from "../../chat/contract-shelf"
import { shelfCopy } from "../../copy/shelf"
import "./run-waiting.css"

const w = shelfCopy.waiting

function Guests({ rows }: { rows: RunWaitingGuest[] }) {
  // 처음 그릴 때 이미 있던 줄은 움직이지 않는다. 그 뒤에 온 줄만 부드럽게 들어온다.
  const seen = useRef<Set<string> | null>(null)
  const first = seen.current === null
  const known = seen.current ?? new Set<string>()
  useEffect(() => {
    seen.current = new Set([...(seen.current ?? []), ...rows.map((r) => r.visit)])
  }, [rows])
  return (
    <ol className="run-waiting-guests" aria-label={w.recent}>
      {rows.map((g) => (
        <li key={g.visit} className="run-waiting-guest" data-ours={g.ours || undefined}
          data-new={!first && !known.has(g.visit) ? true : undefined}>
          <Text hasTabularNumbers>{w.guest(g.age, g.sex)}</Text>
          <span className="run-waiting-chose">
            <span className="run-waiting-mark" role={g.ours ? "img" : undefined} aria-label={g.ours ? w.ours : undefined} aria-hidden={g.ours ? undefined : true} />
            <Text weight={g.ours ? "semibold" : "normal"}>{g.chose}</Text>
          </span>
          {g.said ? <Text className="run-waiting-said">“{g.said}”</Text> : <span />}
        </li>
      ))}
    </ol>
  )
}

export function RunWaiting({ view, kind, children, actions }: {
  view: ShelfRunView
  kind: "explore" | "target"
  /** 막대 아래에 접어 두는 자세한 표(탐색의 연령·성별 표) */
  children?: ReactNode
  /** 멈추기 등. 떠나도 된다는 말 옆에 놓인다 */
  actions?: ReactNode
}) {
  const wait = view.waiting
  const total = view.total
  const done = wait ? wait.steps_done : view.asked
  const max = wait ? wait.steps_total : total
  const visited = wait ? wait.visited : view.asked
  const mode = wait?.mode === "improve" ? "improve" : kind
  const eta = wait?.eta_s
  const allIn = wait != null && visited + view.skipped >= total && done < max
  const lead = wait?.lead
  const recent = wait?.recent ?? []
  return (
    <section className="run-waiting" aria-label={w.status}>
      <div className="run-waiting-head">
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2">
          <Badge label={w.status} variant="neutral" />
          <Text weight="semibold">{view.concept.name}</Text>
        </div>
        <Text weight="medium" hasTabularNumbers>{eta != null ? w.remaining(eta) : w.guess[mode]}</Text>
      </div>
      <div className="run-waiting-progress">
        <ProgressBar label={w.progress} isLabelHidden value={done} max={Math.max(1, max)} variant="neutral" />
        <Text hasTabularNumbers>{allIn ? w.allVisited(total) : w.visited(visited, total)}</Text>
      </div>
      {lead && (
        <Text weight="semibold" hasTabularNumbers>
          {lead.kind === "group" ? w.leadGroup(w.guest(lead.age, lead.sex), lead.picked, lead.n)
            : w.leadTarget(lead.picked, lead.n, lead.name)}
        </Text>
      )}
      {recent.length > 0 && (
        <div className="grid gap-2">
          <Text weight="medium">{w.recent}</Text>
          <Guests rows={recent} />
        </div>
      )}
      {children}
      <div className="run-waiting-foot">
        <Text>{w.leave}</Text>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </section>
  )
}

/** 테스트가 끝난 순간 이 탭이 가려져 있으면 탭 제목으로 알린다. 탭으로 돌아오면 원래 제목으로 되돌린다. */
export function useRunDoneTitle(status: string | undefined) {
  const prev = useRef(status)
  useEffect(() => {
    const was = prev.current
    prev.current = status
    if (was !== "running" || status !== "done" || !document.hidden) return
    const original = document.title
    document.title = w.doneTitle
    const back = () => {
      if (document.hidden) return
      if (document.title === w.doneTitle) document.title = original
      document.removeEventListener("visibilitychange", back)
    }
    document.addEventListener("visibilitychange", back)
  }, [status])
}
