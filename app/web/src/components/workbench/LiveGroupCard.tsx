import { Button } from "@astryxdesign/core/Button"
import { Fragment } from "react"
import type { LiveGroupPayload } from "../../chat/contract-group"
import { groupLiveCopy as c } from "../../copy/group-live"
import { InterviewBubble, InterviewChat } from "./InterviewChat"
import { GroupLiveSession } from "./GroupLiveSession"
import type { CardSay } from "./ShelfCards"
import "./GroupLive.css"

export function LiveGroupCard({ payload, say }: { payload: LiveGroupPayload; say: CardSay }) {
  const { session, individual } = payload
  if (payload.view === "setup") {
    const selected = payload.questions.find(q => q.id === payload.selected_question_id)
    const facts = selected ? [selected.basis] : payload.questions.slice(0, 2).map(q => q.basis)
    if (!facts.length) return <p>칠성이와 질문과 방식을 정하면 여기에 인터뷰 대화가 열려요.</p>
    return <div className="flex flex-col gap-2">
      <p className="font-semibold">{payload.concept} · 매대에서 확인한 점</p>
      {facts.filter(Boolean).map(fact => <p key={fact}>{fact}</p>)}
    </div>
  }
  if (payload.view === "individual" && individual) {
    const guest = payload.candidates[0]
    return <InterviewChat title={guest?.who ?? c.methods.one.label} detail={guest ? c.choice(guest.choice) : c.moderator}
      count={individual.qa.length}>
      {individual.qa.length === 0 && <InterviewBubble text={individual.question} />}
      {individual.qa.map(([q, a], i) => <Fragment key={i}>
        <InterviewBubble text={q} />
        <InterviewBubble guest name={guest?.who ?? c.unknownSpeaker} text={a} />
      </Fragment>)}
    </InterviewChat>
  }
  if (!session) return null
  return <section className="group-live group-live__stack" aria-label={c.methods[session.mode].label}>
    <GroupLiveSession key={session.id} session={session} runId={payload.run_id} say={say} />
    {session.status === "done" && say && <div><Button variant="ghost" size="sm" label={c.chooseAgain}
      isDisabled={say.isDisabled} onClick={() => say.onSay(c.chooseAgain, { to: "w7-group", ids: ["edit", payload.run_id] })} /></div>}
  </section>
}
