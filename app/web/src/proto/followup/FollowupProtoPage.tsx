/**
 * 견본: 후속 개선의 새 화면과 대화(참가자의 승인을 받기 위한 화면. 앱의 흐름에는 아직 잇지 않았다).
 * 왼쪽은 칠성이가 조사에서 알게 된 것을 정리하고 다음 일을 제안하는 말과 버튼, 오른쪽은 조사 확인 화면(보고서 한 장).
 * 자료는 저장소에 넣지 않고 ?upload=올림 번호의 집계를 읽어 그린다.
 */
import { useEffect, useState } from "react"
import { Button } from "@astryxdesign/core/Button"
import { ChatLayout, ChatMessage, ChatMessageBubble, ChatMessageList } from "@astryxdesign/core/Chat"
import { Heading } from "@astryxdesign/core/Heading"
import { Icon } from "@astryxdesign/core/Icon"
import { Text } from "@astryxdesign/core/Text"
import { PaperClipIcon } from "@heroicons/react/20/solid"
import { useSearchParams } from "react-router"
import type { FollowupPayload, FollowupPeople } from "../../chat/contract-followup"
import { ChilseongTurn, SayText, TurnBlock } from "../../components/chat/ChatParts"
import { Composer } from "../../components/Composer"
import { FollowupReport, FollowupRetest, bigGaps, retestMoves } from "../../components/workbench/FollowupReport"
import { followupRetestPayload, followupRetestPeople } from "../../fixtures/followupRetestSample"
import { followupReportCopy as t } from "../../copy/followup-report"
import "../board-analysis/board-analysis-proto.css"

const p = t.proto

function useUpload(id: string | null) {
  const [state, setState] = useState<FollowupPayload | "loading" | "missing">(id ? "loading" : "missing")
  useEffect(() => {
    if (!id) return
    let alive = true
    fetch(`/api/followup/${encodeURIComponent(id)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((v) => alive && setState(v && v.diffs ? v : "missing"))
      .catch(() => alive && setState("missing"))
    return () => { alive = false }
  }, [id])
  return state
}

function sayOf(v: FollowupPayload) {
  const removed = v.removed.reduce((a, r) => a + r.count, 0)
  const gaps = bigGaps(v)
  const found = gaps.length ? [p.gaps(gaps.length), ...gaps.map((g) => p.gap[g.id]?.(v.concept.price, g.virtual, g.actual) ?? "")].filter(Boolean).join("\n") : p.noGap
  return [p.read(v.n.raw, removed, v.target, v.n.target), found, p.ask(v.target, v.track.total)].join("\n\n")
}

function usePeople(id: string | null, on: boolean) {
  const [people, setPeople] = useState<FollowupPeople | null>(null)
  useEffect(() => {
    if (!id || !on) return
    let alive = true
    fetch(`/api/followup/${encodeURIComponent(id)}/people`).then((r) => (r.ok ? r.json() : null)).then((v) => alive && setPeople(v)).catch(() => null)
    return () => { alive = false }
  }, [id, on])
  return people
}

function retestSay(v: FollowupPayload, people: FollowupPeople) {
  const m = retestMoves(people)
  const s = t.retest.say
  return [s.done(v.target, v.concept.name, m.before, m.after), s.move(m.lost.length, m.gain.length), s.ask(m.lost.length)].join("\n\n")
}

export default function FollowupProtoPage() {
  const [params] = useSearchParams()
  const sample = params.get("sample") === "retest"
  const wantsRetest = sample || params.get("view") === "retest"
  const loaded = useUpload(sample ? null : params.get("upload"))
  const livePeople = usePeople(params.get("upload"), wantsRetest && !sample)
  const view = sample ? followupRetestPayload() : loaded
  const people = sample ? followupRetestPeople : livePeople
  const ready = typeof view === "object"
  const retest = ready && wantsRetest && people ? people : null
  return (
    <div className="bap flex h-dvh min-h-0">
      <aside className="bap-chat flex min-h-0 shrink-0 flex-col">
        <ChatLayout composer={<div className="p-3"><Composer onSubmit={() => {}} hasModeMenu={false} placeholder={p.placeholder} density="balanced" /></div>}>
          <ChatMessageList align="top" gap={5}>
            <ChatMessage sender="user">
              <ChatMessageBubble>{retest ? t.retest.say.planner : <span className="inline-flex items-center gap-1"><Icon icon={PaperClipIcon} size="sm" /> {p.file}</span>}</ChatMessageBubble>
            </ChatMessage>
            {ready && retest && retest.status === "done" && (
              <ChilseongTurn>
                <TurnBlock><SayText text={retestSay(view, retest)} /></TurnBlock>
                <TurnBlock><Button variant="primary" label={t.retest.say.btnIdeas} /></TurnBlock>
              </ChilseongTurn>
            )}
            {ready && !retest && (
              <ChilseongTurn>
                <TurnBlock><SayText text={sayOf(view)} /></TurnBlock>
                <TurnBlock>
                  <div className="flex flex-wrap gap-2">
                    <Button variant="primary" label={p.btnApply} />
                    <Button variant="secondary" label={p.btnIdeas} />
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
                <Text hasTabularNumbers weight="medium">{t.won(view.concept.price)}</Text>
              </div>
              {retest ? <FollowupRetest payload={view} people={retest} /> : <FollowupReport payload={view} />}
            </div>
          ) : <Text>{view === "loading" ? p.loading : p.missing}</Text>}
        </div>
      </main>
    </div>
  )
}
