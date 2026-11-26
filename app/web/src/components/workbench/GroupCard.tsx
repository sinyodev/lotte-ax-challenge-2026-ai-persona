import { Fragment, useState } from "react"
import { Badge } from "@astryxdesign/core/Badge"
import { Button } from "@astryxdesign/core/Button"
import { DropdownMenu, DropdownMenuRadioGroup, DropdownMenuRadioItem } from "@astryxdesign/core/DropdownMenu"
import type { GroupMode, GroupPayload, GroupTurn } from "../../chat/contract-group"
import { groupCopy as c } from "../../copy/group"
import { InterviewBubble, InterviewChat } from "./InterviewChat"
import "./group-room.css"

type GroupRoomProps = {
  payload: GroupPayload
  onPickQuote: (turn: GroupTurn) => void
  initialMode?: GroupMode
}

const ALL = "all"

function TranscriptFilter({ label, options, value, onChange }: {
  label: string
  options: { value: string; label: string }[]
  value: string
  onChange: (value: string) => void
}) {
  return (
    <DropdownMenu button={{ label: options.find((option) => option.value === value)?.label ?? label, size: "sm" }}>
      <DropdownMenuRadioGroup label={label} value={value} onChange={onChange}>
        {options.map((option) => <DropdownMenuRadioItem key={option.value} {...option} />)}
      </DropdownMenuRadioGroup>
    </DropdownMenu>
  )
}

export function GroupRoom({ payload, onPickQuote, initialMode = "fgd" }: GroupRoomProps) {
  const [mode, setMode] = useState(initialMode)
  const [round, setRound] = useState(ALL)
  const [speaker, setSpeaker] = useState(ALL)
  const session = payload.modes[mode]
  const turns = [...session.turns].sort((a, b) => a.round - b.round)
  const name = (id: string) => payload.participants.find(p => p.id === id)?.label ?? id
  const visible = turns.filter(t => (round === ALL || String(t.round) === round) && (speaker === ALL || t.person === speaker))
  return <section className="group-room" aria-label={payload.concept}>
    <header className="group-room__header">
      <div className="group-room__modes" role="group" aria-label={c.method}>
        {(["fgd", "fgi"] as const).map(key => <Button key={key} label={c[key]} aria-pressed={mode === key} size="sm"
          onClick={() => { setMode(key); setRound(ALL); setSpeaker(ALL) }} />)}
      </div>
      <Badge label={c.demo} />
    </header>
    <InterviewChat key={mode} title={c[mode]} detail={payload.concept} count={visible.length}>
      <InterviewBubble text={session.question} />
      {visible.map((turn, i) => {
        const previous = turn.replyTo && turns.find(t => t.id === turn.replyTo)
        return <Fragment key={turn.id}>
          {mode === "fgd" && visible[i - 1]?.round !== turn.round && <div className="interview-chat__divider">{c.round(turn.round)}</div>}
          <InterviewBubble guest name={name(turn.person)} text={turn.text}
            reply={previous ? { label: c.reply(name(previous.person)), text: previous.text } : undefined}
            onQuote={() => onPickQuote(turn)} />
        </Fragment>
      })}
      {!visible.length && <p className="interview-chat__status">{turns.length ? c.noFilteredTurns : c.noTurns}</p>}
    </InterviewChat>
    <details className="group-room__disclosure">
      <summary>{c.transcript}</summary>
      <div className="group-room__record-actions">
        <TranscriptFilter label={c.roundFilter} value={round} onChange={setRound}
          options={[{ value: ALL, label: c.everyRound }, ...Array.from(new Set(turns.map(t => t.round)),
            r => ({ value: String(r), label: c.round(r) }))]} />
        <TranscriptFilter label={c.participants} value={speaker} onChange={setSpeaker}
          options={[{ value: ALL, label: c.everyParticipant }, ...payload.participants.map(p => ({ value: p.id, label: p.label }))]} />
      </div>
    </details>
    {session.summary.length > 0 && <details className="group-room__disclosure">
      <summary>{c.findings}</summary>
      <ul className="group-room__findings">{session.summary.map(item => <li key={item.title}>
        <h4>{item.title}</h4><p>{item.text}</p>
        {item.turnIds.map(id => {
          const turn = turns.find(t => t.id === id)
          return turn && <details key={id}><summary>{c.evidence(name(turn.person), turn.round)}</summary>
            <p>{turn.text}</p><Button size="sm" label={c.pickQuote} onClick={() => onPickQuote(turn)} /></details>
        })}
      </li>)}</ul>
    </details>}
  </section>
}
