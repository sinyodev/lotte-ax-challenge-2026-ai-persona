import { Fragment } from "react"
import { InterviewBubble, InterviewChat } from "../../components/workbench/InterviewChat"
import { Tag } from "../../components/workbench/OriginTag"
import { w7 } from "./copy"
import { questions, sessions, type QuestionId } from "./data"
import { BenchCard, personOf, speakerLabel } from "./parts"

export function SceneC({ method, question }: { method: "fgi" | "fgd"; question: QuestionId }) {
  const { turns } = sessions[method]
  const hasScript = questions.find(q => q.id === question)?.hasScript
  return <BenchCard title={w7.steps[2]} source="demo" aside={!hasScript && <Tag isDashed>{w7.c.noScript}</Tag>}>
    <InterviewChat title={w7.b.methods[method].name} detail={w7.c.honesty} count={turns.length}>
      <InterviewBubble text={w7.b.questions[question].q} />
      {turns.map((t, i) => <Fragment key={t.id}>
        {method === "fgd" && turns[i - 1]?.round !== t.round && <div className="interview-chat__divider">{w7.d.round(t.round)}</div>}
        <InterviewBubble guest={t.person !== "host"} name={speakerLabel(t)} text={t.text} reply={t.to && t.stance ?
          { label: w7.c.to(w7.personLabel(personOf(t.to)), t.stance === "agree" ? w7.c.agree : w7.c.rebut) } : undefined} />
      </Fragment>)}
    </InterviewChat>
  </BenchCard>
}
