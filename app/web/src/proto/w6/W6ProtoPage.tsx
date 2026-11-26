import { useEffect, useRef, useState, type DragEvent, type ReactNode } from "react"
import { Badge } from "@astryxdesign/core/Badge"
import { Button } from "@astryxdesign/core/Button"
import { ChatLayout, ChatMessage, ChatMessageBubble, ChatMessageList, ChatSystemMessage } from "@astryxdesign/core/Chat"
import { Heading } from "@astryxdesign/core/Heading"
import { Icon } from "@astryxdesign/core/Icon"
import { Spinner } from "@astryxdesign/core/Spinner"
import { Step, Stepper } from "@astryxdesign/core/Stepper"
import { Text } from "@astryxdesign/core/Text"
import { PaperClipIcon } from "@heroicons/react/20/solid"
import { ChilseongTurn, SayText, TurnBlock } from "../../components/chat/ChatParts"
import { Composer } from "../../components/Composer"
import { PlannerBubble } from "../../components/PlannerBubble"
import { w6 } from "./copy"
import { CompareScene, DiffScene, IdeasScene, ReportScene, RetestScene, RevisedScene } from "./Scenes"
import "./proto.css"

const THINK_MS = 1100
const LAST = 6
/** 장면 → 앱의 단계 */
const STEP_OF = [3, 4, 4, 4, 4, 4, 4]
/** 장면 → 후속 개선 안의 순서 */
const FLOW_OF = [-1, 0, 1, 2, 3, 3, 4]
/** 장면까지 나온 값: 처음 예상, 조사 반영, 개선안 */
const TRACK = [30, 24, 43]
const TRACK_FROM = [0, 3, 5]
/** 단계를 누르면 가는 장면 */
const SCENE_OF: Record<number, number> = { 0: 0, 1: 0, 2: 0, 3: 0, 4: 1 }

function FileBubble({ name }: { name: string }) {
  return (
    <ChatMessage sender="user">
      <ChatMessageBubble>
        <span className="w6-file"><Icon icon={PaperClipIcon} size="sm" /> {name}</span>
      </ChatMessageBubble>
    </ChatMessage>
  )
}

/** W6 UX 시안. 보고서 다음의 "후속 개선"를 실제 대화 화면과 같은 틀에서 눌러 본다. 타깃 조사 집계와 예시 숫자를 표시로 가른다. */
export default function W6ProtoPage() {
  const [scene, setScene] = useState(0)
  const [ready, setReady] = useState(false)
  const [file, setFile] = useState(w6.file)
  const [isDragging, setDragging] = useState(false)
  const bench = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setReady(false)
    bench.current?.scrollTo({ top: 0 })
    const t = window.setTimeout(() => setReady(true), THINK_MS)
    return () => window.clearTimeout(t)
  }, [scene])

  const go = (n: number) => setScene(Math.max(0, Math.min(LAST, n)))
  const upload = (name = w6.file) => {
    setFile(name)
    go(1)
  }
  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    // 시안은 파일의 이름만 쓰고 내용을 읽지 않는다
    if (scene === 0) upload(e.dataTransfer.files[0]?.name)
  }

  const turns: { say: string; actions: ReactNode; reply: ReactNode }[] = [
    {
      say: w6.s0.say,
      actions: (
        <>
          <Button label={w6.s0.cta} variant="primary" onClick={() => upload()} />
          <Button label={w6.s0.later} variant="secondary" isDisabled />
        </>
      ),
      reply: [<ChatSystemMessage key="when" variant="divider">{w6.when}</ChatSystemMessage>, <FileBubble key="file" name={file} />],
    },
    { say: w6.s1.say, actions: <Button label={w6.s1.cta} variant="primary" onClick={() => go(2)} />, reply: <PlannerBubble key="r1" text={w6.s1.cta} /> },
    { say: w6.s2.say, actions: <Button label={w6.s2.cta} variant="primary" onClick={() => go(3)} />, reply: <PlannerBubble key="r2" text={w6.s2.cta} /> },
    { say: w6.s2b.say, actions: <Button label={w6.s2b.cta} variant="primary" onClick={() => go(4)} />, reply: <PlannerBubble key="r2b" text={w6.s2b.cta} /> },
    {
      say: w6.s3.say,
      actions: (
        <>
          <Button label={w6.s3.cta} variant="primary" onClick={() => go(5)} />
          <Button label={w6.s3.one} variant="secondary" isDisabled />
        </>
      ),
      reply: <PlannerBubble key="r3" text={w6.s3.cta} />,
    },
    {
      say: w6.s4.say,
      actions: (
        <>
          <Button label={w6.s4.cta} variant="primary" onClick={() => go(6)} />
          <Button label={w6.s4.keep} variant="secondary" isDisabled />
        </>
      ),
      reply: <PlannerBubble key="r4" text={w6.s4.cta} />,
    },
    {
      say: w6.s5.say,
      actions: (
        <>
          <Button label={w6.s5.cta} variant="primary" onClick={() => go(0)} />
          <Button label={w6.s5.again} variant="secondary" onClick={() => go(4)} />
        </>
      ),
      reply: null,
    },
  ]
  const first = 0

  return (
    <div
      className="w6 relative flex h-dvh min-h-0 flex-col"
      onDragOver={(e) => {
        e.preventDefault()
        if (scene === 0) setDragging(true)
      }}
      onDragLeave={(e) => {
        if (e.currentTarget === e.target) setDragging(false)
      }}
      onDrop={onDrop}
    >
      <div className="flex items-center gap-4 border-b px-6 py-3" data-line>
        <div className="shrink-0"><Text type="supporting" weight="medium">{w6.part}</Text></div>
        <div className="min-w-0 flex-1">
          <Stepper activeStep={STEP_OF[scene]} label={w6.stepperLabel} density="compact" onStepClick={(i) => go(SCENE_OF[i])}>
            {w6.steps.map((label, i) => <Step key={label} step={i} label={label} />)}
          </Stepper>
        </div>
        <Badge label={w6.proto} />
        <div className="flex items-center gap-1">
          <Button label={w6.prev} variant="secondary" size="sm" isDisabled={scene === 0} onClick={() => go(scene - 1)} />
          <Button label={w6.next} variant="secondary" size="sm" isDisabled={scene === LAST} onClick={() => go(scene + 1)} />
          <Button label={w6.restart} variant="secondary" size="sm" onClick={() => go(0)} />
        </div>
      </div>
      <div className="flex min-h-0 flex-1">
        <section aria-label={w6.chatLabel} className="relative flex w-80 shrink-0 flex-col border-r lg:w-110" data-line>
          {isDragging && <div className="w6-drop"><Heading level={3}>{w6.s0.dropping}</Heading></div>}
          <ChatLayout
            density="compact"
            composer={
              <div className="w6-composer">
                <Composer onSubmit={() => {}} hasModeMenu={false} placeholder={w6.placeholder} density="balanced" />
              </div>
            }
          >
            <ChatMessageList align="top" gap={5}>
              {turns.slice(first, scene + 1).map((t, k) => {
                const i = first + k
                const isCurrent = i === scene
                if (isCurrent && !ready)
                  return (
                    <ChilseongTurn key={i} isThinking>
                      <TurnBlock>
                        <span className="w6-file"><Spinner size="sm" /><Text>{w6.thinking[i]}</Text></span>
                      </TurnBlock>
                    </ChilseongTurn>
                  )
                return [
                  <ChilseongTurn key={`c${i}`}>
                    <TurnBlock><SayText text={t.say} /></TurnBlock>
                    {isCurrent && (
                      <TurnBlock>
                        <div className="flex flex-wrap items-center gap-2">{t.actions}</div>
                      </TurnBlock>
                    )}
                    {isCurrent && i === 0 && <TurnBlock><Text>{w6.s0.drop}</Text></TurnBlock>}
                  </ChilseongTurn>,
                  isCurrent ? null : t.reply,
                ]
              })}
            </ChatMessageList>
          </ChatLayout>
        </section>
        <section className="w6-bench flex min-w-0 flex-1 flex-col">
          <div className="w6-top">
            <Heading level={2}>{w6.steps[STEP_OF[scene]]}</Heading>
            {FLOW_OF[scene] >= 0 && (
              <>
                <Stepper activeStep={FLOW_OF[scene]} label={w6.flowLabel} density="compact">
                  {w6.flow.map((label, i) => <Step key={label} step={i} label={label} />)}
                </Stepper>
                <div className="w6-track">
                  <Text weight="medium">{w6.track.title}</Text>
                  {w6.track.steps.map((label, i) => {
                    const on = scene >= TRACK_FROM[i] && (ready || scene > TRACK_FROM[i])
                    return (
                      <span key={label} className="w6-trackstep" data-on={on || undefined}>
                        {i > 0 && <Text>→</Text>}
                        <Text>{label}</Text>
                        <Heading level={3}>{on ? w6.track.unit(TRACK[i]) : "–"}</Heading>
                      </span>
                    )
                  })}
                  <Badge label={w6.sample} />
                </div>
              </>
            )}
          </div>
          <div ref={bench} className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-6 pt-1 pb-8">
            {(ready || scene === 2) && (
              <>
                {scene === 0 && <ReportScene />}
                {(scene === 1 || scene === 2) && <DiffScene fixed={scene === 2} />}
                {scene === 3 && <RetestScene />}
                {scene === 4 && <IdeasScene />}
                {scene === 5 && <CompareScene />}
                {scene === 6 && <RevisedScene />}
              </>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
