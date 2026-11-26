import { useEffect, useRef, useState, type ReactNode } from "react"
import { Badge } from "@astryxdesign/core/Badge"
import { Button } from "@astryxdesign/core/Button"
import { ChatLayout, ChatMessageList } from "@astryxdesign/core/Chat"
import { Heading } from "@astryxdesign/core/Heading"
import { Step, Stepper } from "@astryxdesign/core/Stepper"
import { Text } from "@astryxdesign/core/Text"
import { ChilseongTurn, SayText, TurnBlock } from "../../components/chat/ChatParts"
import { Composer } from "../../components/Composer"
import { PlannerBubble } from "../../components/PlannerBubble"
import type { DiagnosisPayload } from "../../chat/contract-diagnose"
import { diagnoseCopy } from "../../copy/diagnose"
import { w7 } from "./copy"
import { compare, concept, defaults, panel, sessions, shelfResult, type MethodId, type QuestionId } from "./data"
import { SceneA, SceneB, SceneD, SceneE } from "./Scenes"
import { SceneC } from "./SceneC"
import { quoteLabel } from "./parts"
import "./proto.css"

export type ProtoState = {
  scene: number
  aChoice: "both" | "original" | null
  question: QuestionId | null
  method: MethodId | null
  quote: string | null
  adopted: boolean
}

const initial: ProtoState = { scene: 0, aChoice: null, question: null, method: null, quote: null, adopted: false }

/** 장면 B에서 고르지 않고 건너뛰었으면 기본값을 쓴다. */
export function resolved(s: ProtoState) {
  const question = s.question ?? defaults.question
  const method: "fgi" | "fgd" = s.method === "fgi" ? "fgi" : s.method === "fgd" ? "fgd" : defaults.method
  const session = sessions[method]
  const quote = session.turns.find((t) => t.id === s.quote) ?? session.turns.find((t) => t.id === session.findings[0].turnIds[0])!
  return { question, method, session, quote }
}

/**
 * W7 UX 시안. 실제 대화 화면(TestPage)과 같은 틀: 위의 단계 표시줄, 왼쪽 대화, 오른쪽 작업대.
 * 컨셉 진단은 서버에서 읽고 테스트 이후 장면은 시연용 응답으로 진행한다.
 */
export default function W7ProtoPage() {
  const [s, setS] = useState<ProtoState>(initial)
  const [diagnosis, setDiagnosis] = useState<DiagnosisPayload | null>(null)
  const [failed, setFailed] = useState(false)
  const [request, setRequest] = useState(0)
  const retry = () => {
    setFailed(false)
    setRequest(n => n + 1)
  }
  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => controller.abort(), 6000)
    let active = true
    fetch(`/api/w7/diagnosis?${new URLSearchParams({ pack: concept.pack })}`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error()
        const payload = await response.json() as DiagnosisPayload
        if (!Array.isArray(payload.sections) || !Array.isArray(payload.fixes)) throw new Error()
        return payload
      })
      .then(payload => { if (active) setDiagnosis(payload) })
      .catch(() => { if (active) setFailed(true) })
      .finally(() => window.clearTimeout(timer))
    return () => {
      active = false
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [request])
  const set = (patch: Partial<ProtoState>) => setS((p) => ({ ...p, ...patch }))
  const go = (scene: number, patch: Partial<ProtoState> = {}) => set({ ...patch, scene, adopted: scene === 4 ? (patch.adopted ?? false) : false })
  const r = resolved(s)
  // 장면이 바뀌면 작업대를 맨 위부터 보인다
  const bench = useRef<HTMLDivElement>(null)
  useEffect(() => {
    bench.current?.scrollTo({ top: 0 })
  }, [s.scene, s.adopted])

  const canOpenInterview = s.question !== null && (s.method === "fgi" || s.method === "fgd")
  const qText = w7.b.questions[r.question].q
  const mName = w7.b.methods[r.method].name
  const canCompare = Boolean(diagnosis?.fixes.length)
  const diagnosticSummary = diagnosis?.sections.filter(section => section.status === "flag")
    .map(section => section.summary).join(" ")

  /** 장면마다 칠성이의 말, 대표 버튼, 보조 버튼, 기획자가 누른 말 */
  const turns: { say: string; actions: ReactNode; planner: string }[] = [
    {
      say: diagnosis
        ? [diagnosticSummary, canCompare ? w7.a.choose : w7.a.original].filter(Boolean).join(" ")
        : failed ? diagnoseCopy.unavailable : w7.a.start,
      planner: s.aChoice ? diagnoseCopy.reply[s.aChoice] : w7.a.skipped,
      actions: (
        <>
          {canCompare && <Button label={diagnoseCopy.reply.both} variant="primary" onClick={() => go(1, { aChoice: "both" })} />}
          <Button label={diagnoseCopy.reply.original} variant={canCompare ? "secondary" : "primary"}
            onClick={() => go(1, { aChoice: "original" })} />
        </>
      ),
    },
    {
      say: w7.b.chat(panel.total, shelfResult.picked),
      planner: w7.b.planner(qText, mName),
      actions: (
        <Button
          label={w7.b.cta}
          variant="primary"
          isDisabled={!canOpenInterview}
          tooltip={canOpenInterview ? undefined : w7.b.needPick}
          onClick={() => go(2)}
        />
      ),
    },
    {
      say: w7.c.chat[r.method],
      planner: w7.c.planner,
      actions: <Button label={w7.c.cta} variant="primary" onClick={() => go(3)} />,
    },
    {
      say: w7.d.chat[r.method],
      planner: s.quote ? `${w7.d.planner}: ${quoteLabel(r.quote)}` : w7.d.planner,
      actions: (
        <Button
          label={w7.d.cta}
          variant="primary"
          isDisabled={!s.quote}
          tooltip={s.quote ? undefined : w7.d.needPick}
          onClick={() => go(4)}
        />
      ),
    },
    {
      say:
        (compare.verdict === "unclear" ? `${w7.e.unclear} ` : "") +
        w7.e.chat(compare.total, compare.original.picked, compare.changed.picked, compare.gained, compare.lost),
      planner: w7.e.planner,
      actions: <Button label={w7.e.cta} variant="primary" onClick={() => go(4, { adopted: true })} />,
    },
  ]

  const benchTitle = s.scene === 4 && s.adopted ? w7.adopted.title : w7.stageOf[s.scene]

  return (
    <div className="w7-proto flex h-dvh min-h-0 flex-col">
      <div className="flex items-center gap-4 border-b px-6 py-3" data-proto-line>
        <div className="shrink-0">
          <Text type="supporting" weight="medium">
            {w7.stageOf[s.scene]}
          </Text>
        </div>
        <div className="min-w-0 flex-1">
          <Stepper
            activeStep={s.scene}
            label={w7.page.stepperLabel}
            density="compact"
            onStepClick={(i) => go(i)}
            horizontalOptions={{ minimumStepWidth: 96, collapsedVariant: "withLabelAndControls" }}
          >
            {w7.steps.map((label, i) => (
              <Step key={label} step={i} label={label} />
            ))}
          </Stepper>
        </div>
        <Badge label={w7.page.prototype} />
        <Button
          label={w7.page.restart}
          variant="secondary"
          size="sm"
          onClick={() => setS(initial)}
        />
      </div>
      <div className="flex min-h-0 flex-1">
        <section aria-label={w7.page.chatLabel} className="flex w-80 shrink-0 flex-col border-r lg:w-110" data-proto-line>
          <ChatLayout
            density="compact"
            composer={
              <div className="w7-composer" title={w7.page.composerNote}>
                <Composer onSubmit={() => {}} hasModeMenu={false} placeholder={w7.page.placeholder} density="balanced" />
              </div>
            }
          >
            <ChatMessageList align="top" gap={5}>
              {turns.slice(0, s.scene + 1).flatMap((t, i) => {
                const isCurrent = i === s.scene
                const isAdoptedTurn = isCurrent && s.scene === 4 && s.adopted
                const nodes = [
                  <ChilseongTurn key={`c${i}`}>
                    <TurnBlock>
                      <SayText text={t.say} />
                    </TurnBlock>
                    {isCurrent && !isAdoptedTurn && (
                      <TurnBlock>
                        <div className="flex flex-wrap items-center gap-2">{t.actions}</div>
                      </TurnBlock>
                    )}
                  </ChilseongTurn>,
                ]
                if (!isCurrent || isAdoptedTurn) nodes.push(<PlannerBubble key={`p${i}`} text={t.planner} />)
                if (isAdoptedTurn)
                  nodes.push(
                    <ChilseongTurn key="adopted">
                      <TurnBlock>
                        <SayText text={w7.adopted.chat} />
                      </TurnBlock>
                      <TurnBlock>
                        <div className="flex flex-wrap items-center gap-2">
                          <Button label={w7.adopted.other} variant="secondary" onClick={() => go(1)} />
                          <Button label={w7.adopted.toReport} variant="secondary" isDisabled tooltip={w7.adopted.reportNote} />
                        </div>
                      </TurnBlock>
                    </ChilseongTurn>,
                  )
                return nodes
              })}
            </ChatMessageList>
          </ChatLayout>
        </section>
        <div className="min-w-0 flex-1" data-proto-bench>
          <section className="flex h-full min-h-0 flex-col">
            <div className="flex min-h-14 items-center justify-between gap-3 px-6 pt-5 pb-3">
              <Heading level={2}>{benchTitle}</Heading>
            </div>
            <div ref={bench} className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-6 pt-1 pb-8">
              {s.scene === 0 && <SceneA payload={diagnosis} failed={failed} retry={retry} />}
              {s.scene === 1 && <SceneB state={s} set={set} />}
              {s.scene === 2 && <SceneC key={`${r.method}-${r.question}`} method={r.method} question={r.question} />}
              {s.scene === 3 && <SceneD method={r.method} quote={s.quote} onQuote={(id) => set({ quote: id })} />}
              {s.scene === 4 && <SceneE quote={r.quote} method={r.method} adopted={s.adopted} />}
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
