/**
 * 견본: 컨셉 보드 분석의 새 화면과 대화(참가자의 승인을 받기 위한 화면. 앱의 흐름에는 아직 잇지 않았다).
 * 왼쪽은 칠성이가 분석을 인사이트로 정리하고 매대 테스트를 제안하는 말과 버튼, 오른쪽은 분석 화면(보고서 한 장).
 * 자료는 저장소에 넣지 않고 ?chat=대화 id의 분석 카드를 읽어 그린다.
 */
import { useEffect, useState } from "react"
import { Button } from "@astryxdesign/core/Button"
import { ChatLayout, ChatMessageList } from "@astryxdesign/core/Chat"
import { Heading } from "@astryxdesign/core/Heading"
import { Text } from "@astryxdesign/core/Text"
import { useSearchParams } from "react-router"
import type { DiagnosisPayload } from "../../chat/contract-diagnose"
import { ChilseongTurn, SayText, TurnBlock } from "../../components/chat/ChatParts"
import { Composer } from "../../components/Composer"
import { PlannerBubble } from "../../components/PlannerBubble"
import { AnalysisReport } from "../../components/workbench/AnalysisReport"
import { AnalysisSpec } from "../../components/workbench/DiagnosisCard"
import { priceFacts, sectionOf, trendKeyword, trendPair } from "../../components/workbench/analysisModel"
import { diagnoseCopy as c } from "../../copy/diagnose"
import { boardAnalysisCopy as p } from "./copy"
import "./board-analysis-proto.css"

type Part = { type?: string; data?: { kind?: string; payload?: unknown } }

function usePayload(chat: string | null, pack: string | null) {
  const [state, setState] = useState<DiagnosisPayload | "loading" | "missing">(chat || pack ? "loading" : "missing")
  useEffect(() => {
    if (!chat && !pack) return
    let alive = true
    if (pack) {
      // 대화 없이 서버가 방금 집계한 분석(과제 컨셉의 규격)
      fetch(`/api/w7/diagnosis?pack=${encodeURIComponent(pack)}`)
        .then((r) => r.json())
        .then((d) => alive && setState(d && "sections" in d ? d : "missing"))
        .catch(() => alive && setState("missing"))
      return () => { alive = false }
    }
    fetch(`/api/chats/${encodeURIComponent(chat!)}`)
      .then((r) => r.json())
      .then((d) => {
        const cards = (d.messages ?? []).flatMap((m: { parts?: Part[] }) =>
          (m.parts ?? []).filter((part) => part.type === "data-card" && part.data?.kind === "diagnosis"))
        const payload = cards[cards.length - 1]?.data?.payload as DiagnosisPayload | undefined
        if (alive) setState(payload && "sections" in payload ? payload : "missing")
      })
      .catch(() => alive && setState("missing"))
    return () => { alive = false }
  }, [chat, pack])
  return state
}

/** 칠성이의 말: 살펴볼 점을 한 문장씩 정리하고 끝에 테스트를 제안한다. */
function sayOf(payload: DiagnosisPayload) {
  const facts: string[] = []
  const trend = sectionOf(payload, "trend")
  const pair = trend?.status === "flag" ? trendPair(trend) : null
  if (trend && pair && pair.change < 0) facts.push(p.cooling(trendKeyword(trend), Math.round((pair.now / pair.before) * 100)))
  const price = sectionOf(payload, "price")
  const f = priceFacts(price, payload)
  if (price?.status === "flag" && f.current != null && f.wtp && f.current > f.wtp.median) {
    facts.push(p.priceOver(f.current, f.wtp.median, f.current - f.wtp.median))
    if (f.same && f.current < f.same.low) facts.push(p.cheaper(f.same.count, f.same.low))
  }
  const flags = payload.sections.filter((s) => s.status === "flag").length
  const ask = f.current != null && f.fix != null ? p.propose(f.current, f.fix) : p.proposeOne
  return [p.lead(flags), facts.join(" "), ask].filter(Boolean).join("\n\n")
}

export default function BoardAnalysisProtoPage() {
  const [params] = useSearchParams()
  const payload = usePayload(params.get("chat"), params.get("pack"))
  const ready = typeof payload === "object"
  const f = ready ? priceFacts(sectionOf(payload, "price"), payload) : null
  return (
    <div className="bap flex h-dvh min-h-0">
      <aside className="bap-chat flex min-h-0 shrink-0 flex-col">
        <ChatLayout composer={<div className="p-3"><Composer onSubmit={() => {}} hasModeMenu={false} placeholder={p.placeholder} density="balanced" /></div>}>
          <ChatMessageList align="top" gap={5}>
            <PlannerBubble text={p.planner} />
            {ready && (
              <ChilseongTurn>
                <TurnBlock><SayText text={sayOf(payload)} /></TurnBlock>
                <TurnBlock>
                  <div className="flex flex-wrap gap-2">
                    {f?.current != null && f.fix != null ? (
                      <>
                        <Button variant="primary" label={c.pick.both(f.current, f.fix)} />
                        <Button variant="secondary" label={c.pick.only(f.current)} />
                        <Button variant="secondary" label={c.pick.only(f.fix)} />
                      </>
                    ) : <Button variant="primary" label={c.asIs} />}
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
                <Text weight="semibold">{payload.concept_name}</Text>
                <AnalysisSpec payload={payload} />
              </div>
              <AnalysisReport payload={payload} />
            </div>
          ) : <Text>{payload === "loading" ? p.loading : p.missing}</Text>}
        </div>
      </main>
    </div>
  )
}
