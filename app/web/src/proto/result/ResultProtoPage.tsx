/**
 * 견본: 테스트 결과의 새 화면과 대화(참가자의 승인을 받기 위한 화면. 앱의 흐름에는 아직 잇지 않았다).
 * 왼쪽은 칠성이가 결과를 인사이트로 정리하고 다음 일을 제안하는 말과 버튼, 오른쪽은 결과 화면(보고서 한 장).
 * 자료는 저장소에 넣지 않고 ?run=실행 id의 결과를 읽어 그린다.
 */
import { useEffect, useState } from "react"
import { Button } from "@astryxdesign/core/Button"
import { ChatLayout, ChatMessageList } from "@astryxdesign/core/Chat"
import { Heading } from "@astryxdesign/core/Heading"
import { Text } from "@astryxdesign/core/Text"
import { useSearchParams } from "react-router"
import type { ShelfRunView } from "../../chat/contract-shelf"
import { ChilseongTurn, SayText, TurnBlock } from "../../components/chat/ChatParts"
import { Composer } from "../../components/Composer"
import { PlannerBubble } from "../../components/PlannerBubble"
import { ResultReport } from "../../components/workbench/ResultReport"
import { dashCopy as d } from "../../copy/result-dashboard"
import { resultReportCopy as t } from "../../copy/result-report"
import "../board-analysis/board-analysis-proto.css"

const p = t.proto

function useRun(run: string | null) {
  const [state, setState] = useState<ShelfRunView | "loading" | "missing">(run ? "loading" : "missing")
  useEffect(() => {
    if (!run) return
    let alive = true
    fetch(`/api/runs/${encodeURIComponent(run)}`)
      .then((r) => r.json())
      .then((v) => alive && setState(v && v.result ? v : "missing"))
      .catch(() => alive && setState("missing"))
    return () => { alive = false }
  }, [run])
  return state
}

function sayOf(view: ShelfRunView) {
  const res = view.result!
  const group = view.brief?.group ?? view.who.label.replace(/\s*손님$/, "")
  const own = res.from.own.reduce((a, x) => a + x.count, 0)
  const barrier = res.barriers[0]
  const shifted = res.picked > 0 && own * 2 >= res.picked
  const facts = [shifted ? p.own(res.picked, own) : "", barrier ? p.barrier(res.n - res.picked, barrier.count, barrier.label) : ""].filter(Boolean)
  const lead = p.done(group, res.n, res.picked, Math.round((100 * res.picked) / Math.max(1, res.n)), view.concept.name, res.products, res.rank)
  return [lead, facts.length ? [p.learned(facts.length), ...facts].join(" ") : "", facts.length ? p.unknown(shifted, !!barrier) : p.next]
    .filter(Boolean).join("\n\n")
}

export default function ResultProtoPage() {
  const [params] = useSearchParams()
  const view = useRun(params.get("run"))
  const ready = typeof view === "object"
  return (
    <div className="bap flex h-dvh min-h-0">
      <aside className="bap-chat flex min-h-0 shrink-0 flex-col">
        <ChatLayout composer={<div className="p-3"><Composer onSubmit={() => {}} hasModeMenu={false} placeholder={p.placeholder} density="balanced" /></div>}>
          <ChatMessageList align="top" gap={5}>
            <PlannerBubble text={p.planner} />
            {ready && (
              <ChilseongTurn>
                <TurnBlock><SayText text={sayOf(view)} /></TurnBlock>
                <TurnBlock>
                  <div className="flex flex-wrap gap-2">
                    <Button variant="primary" label={p.btnImprove} />
                    <Button variant="secondary" label={p.btnReport} />
                  </div>
                </TurnBlock>
              </ChilseongTurn>
            )}
          </ChatMessageList>
        </ChatLayout>
      </aside>
      <main className="bap-bench min-w-0 flex-1 overflow-y-auto">
        <div className="flex flex-col gap-4 p-5">
          <Heading level={1}>{p.stage}</Heading>
          {ready ? (
            <div className="bap-card">
              <div className="flex flex-wrap items-baseline justify-between gap-2 pb-4">
                <Text weight="semibold">{view.concept.name}</Text>
                <Text hasTabularNumbers weight="medium">{d.spec(view.concept.pack, view.concept.price)}</Text>
              </div>
              <ResultReport view={view} askFor={() => () => {}} />
            </div>
          ) : <Text>{view === "loading" ? p.loading : p.missing}</Text>}
        </div>
      </main>
    </div>
  )
}
