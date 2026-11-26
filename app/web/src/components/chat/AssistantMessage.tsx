import { InterviewInvitation } from "./InterviewInvitation"
import type { LiveGroupPayload } from "../../chat/contract-group"
import { groupLiveCopy } from "../../copy/group-live"
import type { ImprovePayload } from "../../chat/contract-improve"
import type { ReactNode } from "react"
import { isKnownPart, speakerOf, type ChilseongMessage, type Speaker } from "../../chat/contract"
import { useWorkbench } from "../../chat/workbenchStore"
import {
  ActionButtons,
  ActivityLine,
  ChilseongTurn,
  ChoiceChips,
  ConfirmCard,
  OnCardPrompt,
  RetryStoppedButton,
  SayText,
  ShopperTurn,
  StoppedLine,
  SummaryCard,
  TurnBlock,
  type OnReply,
  type ReplyState,
} from "./ChatParts"

type Props = {
  message: ChilseongMessage
  /** 마지막 차례이고 칠성이가 말을 마쳤으면 답을 누를 수 있다. */
  isActive: boolean
  isThinking: boolean
  /** 이 메시지가 마지막이고 대화가 지금 흘러오는 중인가. 하는 일 표시는 이때만 돈다(지시서 11). */
  isStreaming: boolean
  /** 이 차례에 기획자가 답한 것(다음 기획자 말의 metadata.reply). */
  reply?: { to: string; ids: string[] }
  onReply: OnReply
  /** 멈춘 마지막 차례 아래의 "다시 하기"(같은 말을 다시 보낸다). 없으면 버튼을 두지 않는다. */
  onRetryStopped?: () => void
}

/**
 * 칠성이의 한 차례를 놓는 순서(약속 2절의 "놓이는 곳"): 하는 일 → 말 → 요약 → 답을 받는 부품.
 * 단계(stage)와 카드(card), 세션(session)은 대화에 그리지 않는다.
 * 칩은 권하는 것이다. 지난 차례의 답 부품은 고른 것만 남기고, 고른 것이 없으면(직접 써서 답했으면) 조용히 접는다.
 * 물음도 칩도 없는 차례는 말만 놓는다.
 * 멈춘 차례는 하는 일 표시 자리에 멈춤 아이콘과 "멈춤"을 붙이고, 마지막 차례면 아래에 "다시 하기"를 둔다.
 */
export function AssistantMessage({ message, isActive, isThinking, isStreaming, reply, onReply, onRetryStopped }: Props) {
  const pending = useWorkbench((s) => s.pending)
  const above: ReactNode[] = []
  const says: { node: ReactNode; speaker: Speaker | null }[] = []
  const below: ReactNode[] = []
  const replyBox: ReactNode[] = []
  let isRunning = false
  let hasHaltedActivity = false
  const isStopped = Boolean(message.metadata?.stopped)

  const setup = message.parts.find(p => p.type === "data-card" && p.data.kind === "group")
  const group = setup?.type === "data-card" ? setup.data.payload as LiveGroupPayload : undefined
  const legacy = group?.view === "setup" && message.parts.some(p => p.type === "data-choices" &&
    p.data.options.some(o => o.id.startsWith('w7-group:["start",')))
  const question = legacy ? group.questions.find(q => q.id === group.selected_question_id) : undefined
  const planning = question && (isActive || reply?.to === "w7-group")
  message.parts.forEach((p, i) => {
    if (!isKnownPart(p)) return
    const key = `${p.type}-${"id" in p && p.id ? p.id : i}`
    const state = (id: string): ReplyState => ({
      isActive,
      chosen: reply?.to === id ? reply.ids : [],
    })
    const isAnswered = (id: string) => isActive || state(id).chosen.length > 0
    switch (p.type) {
      case "text":
        if (p.text) says.push({ node: <SayText key={key} text={planning ? `질문은 “${question.text}”예요. 어떤 방식으로 들어볼까요?` : p.text} />, speaker: speakerOf(p) })
        break
      case "data-activity":
        if (p.data.status === "running") {
          if (isStreaming) isRunning = true
          else hasHaltedActivity = true
        }
        above.push(<ActivityLine key={key} data={p.data} isLive={isStreaming} isStopped={isStopped} />)
        break
      case "data-summary":
        below.push(<SummaryCard key={key} data={p.data} />)
        break
      case "data-choices": {
        if (!p.id || !isAnswered(p.id)) break
        const id = p.id
        if (planning && group) {
          const modes = ["one", "fgi", "fgd"] as const
          const options = modes.map(mode => ({ id: "w7-group:" + JSON.stringify(["method", group.run_id, question.id, mode]),
            label: groupLiveCopy.methods[mode].label }))
          options.push({ id: "w7-group:" + JSON.stringify(["edit", group.run_id]), label: "질문 바꾸기" })
          replyBox.push(<ChoiceChips key={key} id={id} data={{ ...p.data, options }} state={state(id)} onReply={onReply} />)
        } else if (p.data.on_card) {
          // 카드 안에서 고른다. 지난 차례에는 카드에 고른 표시가 남으므로 대화에는 그리지 않는다.
          if (!isActive) break
          const picked = pending[id] ?? []
          const labels = picked.map((x) => p.data.options.find((o) => o.id === x)?.label ?? x)
          replyBox.push(
            <OnCardPrompt key={key} count={picked.length} onSend={() => onReply(id, picked, labels)} />,
          )
        } else {
          replyBox.push(
            <ChoiceChips key={key} id={id} data={p.data} state={state(id)} onReply={onReply} />,
          )
        }
        break
      }
      case "data-actions": {
        if (!p.id) break
        const card = message.parts.find(part => part.type === "data-card" && part.data.kind === "improve")
        const plan = card?.type === "data-card" ? card.data.payload as ImprovePayload : null
        const actions = isActive ? p.data.actions.filter(action => action.id !== "group-questions") : p.data.actions
        // 이전에 끝낸 인터뷰도 저장된 대화에서 바로 다시 시작할 수 있다.
        if (isActive && p.id.startsWith("after-result-") && message.parts.some(part =>
          part.type === "text" && part.text === "인터뷰를 마쳤어요.") && !actions.some(a => a.id.startsWith("group-questions:"))) {
          const prior = useWorkbench.getState().cards.filter(card => card.kind === "group").at(-1)
          const run = (prior?.payload as LiveGroupPayload | undefined)?.run_id
          if (run) actions.splice(1, 0, { id: `group-questions:${run}`, label: groupLiveCopy.another })
        }
        const original = isAnswered(p.id) && <ActionButtons key={key} id={p.id} data={{ actions }} state={state(p.id)} onReply={onReply} />
        if (p.id.startsWith("improve-") && plan?.base_run && p.data.actions.some(a => a.id === "improve-all") &&
            !plan.items.some(item => item.run_id || item.evidence?.some(ev => ev.quote_id)) &&
            reply?.to === "w7-group") {
          replyBox.push(<InterviewInvitation key={key} runId={plan.base_run} isActive={isActive} onReply={onReply} fallback={original} />)
        } else if (original) replyBox.push(original)
        break
      }
      case "data-confirm":
        if (p.id) replyBox.push(<ConfirmCard key={key} id={p.id} data={p.data} state={state(p.id)} onReply={onReply} />)
        break
    }
  })

  if (isStopped && !hasHaltedActivity) above.push(<StoppedLine key="stopped" />)
  if (isStopped && onRetryStopped) replyBox.push(<RetryStoppedButton key="retry-stopped" onRetry={onRetryStopped} />)
  const isBusy = isThinking || isRunning
  // 손님의 말(지시서 17)은 칠성이와 다른 화자로 놓는다. 말이 모두 손님의 것이면 차례 전체(하는 일, 칩)가 손님의 차례다.
  // 칠성이의 말과 손님의 말이 섞이면 말의 차례대로 화자를 나눠 놓고, 하는 일은 첫 덩이에, 요약과 답의 부품은 마지막 덩이에 둔다.
  const groups: { speaker: Speaker | null; nodes: ReactNode[] }[] = []
  for (const s of says) {
    const last = groups[groups.length - 1]
    if (last && (last.speaker?.label ?? null) === (s.speaker?.label ?? null)) last.nodes.push(s.node)
    else groups.push({ speaker: s.speaker, nodes: [s.node] })
  }
  if (groups.length === 0) groups.push({ speaker: null, nodes: [] })
  groups[0].nodes.unshift(...above)
  groups[groups.length - 1].nodes.push(...below, ...replyBox)
  // 그릴 것이 없는 차례(카드만 온 차례 등)는 빈 줄을 남기지 않는다
  if (groups.every((g) => g.nodes.length === 0) && !isBusy) return null
  return (
    <>
      {groups.map((g, gi) => {
        const isLast = gi === groups.length - 1
        const blocks =
          g.nodes.length === 0
            ? [<TurnBlock key={0}>{null}</TurnBlock>]
            : g.nodes.map((b, i) => (
                <TurnBlock key={i} name={g.speaker && i === 0 ? g.speaker.label : undefined}>
                  {b}
                </TurnBlock>
              ))
        return g.speaker ? (
          <ShopperTurn key={gi}>{blocks}</ShopperTurn>
        ) : (
          <ChilseongTurn key={gi} isThinking={isBusy && isLast}>
            {blocks}
          </ChilseongTurn>
        )
      })}
    </>
  )
}
