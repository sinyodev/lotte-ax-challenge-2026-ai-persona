import { Fragment } from "react"
import { Button } from "@astryxdesign/core/Button"
import type { LiveGroupSession } from "../../chat/contract-group"
import { groupLiveCopy as c } from "../../copy/group-live"
import { GroupLiveConclusion } from "./GroupLiveConclusion"
import { InterviewBubble, InterviewChat } from "./InterviewChat"
import type { CardSay } from "./ShelfCards"

export function GroupLiveSession({ session, runId, say }: {
  session: LiveGroupSession; runId: string; say: CardSay
}) {
  const { mode, turns, participants, status } = session
  const answered = new Set(turns.map(t => t.person)).size
  const detail = mode === "fgi" ? c.answers(answered, participants.length) : `가상 소비자 ${participants.length}명 · 칠성이 진행`
  return <>
    <InterviewChat title={c.methods[mode].label} detail={detail} count={turns.length}>
      <InterviewBubble text={session.question} />
      {turns.map((turn, i) => {
        const who = participants.find(p => p.id === turn.person)?.who ?? c.unknownSpeaker
        const prior = turn.reply_to && turns.find(t => t.id === turn.reply_to)
        const target = prior && participants.find(p => p.id === prior.person)
        const reply = prior && target ? {
          label: turn.stance === "agree" ? c.agree(target.who) : turn.stance === "disagree" ? c.disagree(target.who) : c.respondingTo(target.who),
          text: prior.text,
        } : undefined
        return <Fragment key={turn.id}>
          {mode === "fgd" && turns[i - 1]?.round !== turn.round && <div className="interview-chat__divider">
            {c.round(turn.round)} · {turn.round === 1 ? c.firstRound : c.laterRound}
          </div>}
          <InterviewBubble guest name={who} text={turn.text} reply={reply}
            disabled={say?.isDisabled} onQuote={status === "done" && say ? () => say.onSay(c.quoteRequest(who, turn.text),
              { to: "w7-group", ids: ["quote", runId, session.id, turn.id] }) : undefined} />
        </Fragment>
      })}
      {status === "running" && <p className="interview-chat__status">{turns.length ? c.more : c.preparing}</p>}
    </InterviewChat>
    {status === "running" && say && !say.isDisabled && <div><Button label={c.saved} variant="ghost" size="sm"
      onClick={() => say.onSay(c.saved, { to: "w7-group", ids: ["reopen", runId, session.id] })} /></div>}
    {status === "error" && <div className="group-live__row" role="status">{c.failed}
      {say && <Button label={c.retry} variant="secondary" isDisabled={say.isDisabled} size="sm"
        onClick={() => say.onSay(c.failedRetry, { to: "w7-group", ids: ["open", runId, session.question_id] })} />}
    </div>}
    {status === "done" && <GroupLiveConclusion session={session} runId={runId} say={say} />}
  </>
}
