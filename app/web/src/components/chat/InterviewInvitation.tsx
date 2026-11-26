import type { ReactNode } from "react"
import { Button } from "@astryxdesign/core/Button"
import type { ShelfRunView } from "../../chat/contract-shelf"
import { useRun } from "../../chat/runs"
import { groupLiveCopy as c } from "../../copy/group-live"
import { SayText, type OnReply } from "./ChatParts"

/** 저장한 개선안도 원래 매대의 응답에서 질문을 가져온다. */
export function InterviewInvitation({ runId, isActive, onReply, fallback }: {
  runId: string; isActive: boolean; onReply: OnReply; fallback: ReactNode
}) {
  const { view }: { view: ShelfRunView | null } = useRun(runId)
  const topics = (view?.brief?.actions ?? []).flatMap(action => {
    const command = action.do
    if (!action.reason || !("to" in command) || command.to !== "w7-group") return []
    const label = command.ids[2] === "own" ? c.askSwitch : c.askBarrier
    return [{ reason: action.reason, command, label }]
  })
  if (!topics.length) return fallback
  return <div className="flex flex-col gap-3">
    <SayText text={topics.map(t => t.reason).join(" ") + "\n\n" + c.interviewFirst} />
    {isActive && <div className="flex flex-wrap gap-2">
      {topics.map(({ command, label }, i) => <Button key={label} label={label} variant={i ? "secondary" : "primary"}
        onClick={() => onReply(command.to, command.ids, [label])} />)}
      <Button label={c.customQuestion} variant="secondary" onClick={() => onReply("w7-group", ["edit", runId], [c.customQuestion])} />
    </div>}
  </div>
}
