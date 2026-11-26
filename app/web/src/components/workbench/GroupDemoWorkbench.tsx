import { useState } from "react"
import { Button } from "@astryxdesign/core/Button"
import type { GroupPayload, GroupTurn } from "../../chat/contract-group"
import { demoNavCopy } from "../../copy/group"
import { DiagnosisCard } from "./DiagnosisCard"
import { GroupRoom } from "./GroupCard"
import { W7CompareDemo } from "./W7CompareDemo"
import type { CardSay } from "./ShelfCards"
import { improveCopy } from "../../copy/improve"

type View = "room" | "diagnosis" | "compare"
type DemoPayload = GroupPayload & { view?: View; mode?: "fgi" | "fgd"; turn?: number; quoteId?: string }

export default function GroupDemoWorkbench({ payload, say }: { payload: DemoPayload; say: CardSay }) {
  const [view, setView] = useState<View>(payload.view ?? "room")
  const [quote, setQuote] = useState<GroupTurn | null>(() =>
    payload.modes[payload.mode ?? "fgd"].turns.find((t) => t.id === payload.quoteId) ?? null)
  const [hasOpenedRoom, setHasOpenedRoom] = useState(view === "room")

  function open(next: View) {
    if (next === "room") setHasOpenedRoom(true)
    setView(next)
  }

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <nav className="flex flex-wrap gap-2" aria-label={demoNavCopy.nav}>
        {(["diagnosis", "room", "compare"] as const).map((key) => (
          <Button key={key} size="sm" variant={view === key ? "primary" : "secondary"}
            label={demoNavCopy[key]} onClick={() => open(key)} aria-pressed={view === key} />
        ))}
      </nav>
      {view === "diagnosis" && <DiagnosisCard payload={payload.diagnosis} />}
      {hasOpenedRoom && (
        <div hidden={view !== "room"}>
          <GroupRoom payload={payload} initialMode={payload.mode ?? "fgd"} onPickQuote={(turn) => {
            if (say) {
              if (!say.isDisabled) say.onSay(improveCopy.useQuote(turn.round, turn.person),
                { to: "w7-demo-quote", ids: [`w7-quote/${turn.id}`] })
            } else {
              setQuote(turn)
              open("compare")
            }
          }} />
        </div>
      )}
      {view === "compare" && (
        <W7CompareDemo comparison={payload.comparison} quote={quote} onBack={() => open("room")} />
      )}
    </div>
  )
}
