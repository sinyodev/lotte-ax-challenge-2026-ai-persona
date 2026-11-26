import { useState } from "react"
import { Button } from "@astryxdesign/core/Button"
import { Heading } from "@astryxdesign/core/Heading"
import { Icon } from "@astryxdesign/core/Icon"
import { Text } from "@astryxdesign/core/Text"
import type { LiveGroupSession, LiveGroupTurn } from "../../chat/contract-group"
import { groupLiveCopy as c } from "../../copy/group-live"
import type { CardSay } from "./ShelfCards"
import { Tag } from "./OriginTag"

const CATEGORIES = ["independent", "agreed", "split", "changed"] as const

export function GroupLiveConclusion({ session, runId, say }: {
  session: LiveGroupSession
  runId: string
  say: CardSay
}) {
  const [selection, setSelection] = useState<string>()
  const [round, setRound] = useState("")
  const [speaker, setSpeaker] = useState("")
  const personById = new Map(session.participants.map((p) => [p.id, p]))
  const turnById = new Map(session.turns.map((t) => [t.id, t]))
  const filterRounds = [...new Set(session.turns.map((turn) => turn.round))].sort((a, b) => a - b)
  const filterSpeakers = new Set(session.turns.map((turn) => turn.person))
  const visible = session.turns.filter((t) => (!round || String(t.round) === round) && (!speaker || t.person === speaker))
  const hasFindings = CATEGORIES.some((key) => session.findings[key]?.length)
  const showAnswers = session.mode === "fgi"

  function quoteRow(turn: LiveGroupTurn, location: string) {
    const key = `${location}:${turn.id}`
    const person = personById.get(turn.person)
    const who = person?.who ?? c.unknownSpeaker
    const selected = selection === key
    return (
      <li key={turn.id} className="group-live__quote">
        <button className="group-live__option" type="button" aria-pressed={selected}
          onClick={() => setSelection(selected ? undefined : key)}>
          <span className="group-live__option-mark" aria-hidden="true" />
          <span>
            <span className="group-live__row">
              <Text weight="semibold">{who}</Text>
              <Tag>{c.round(turn.round)}</Tag>
              {person && <Tag isDashed={!person.picked}>{person.picked ? c.picked : c.passed}</Tag>}
              {turn.changed && <Tag>{c.changed}</Tag>}
            </span>
            <Text as="span" display="block">{turn.text}</Text>
          </span>
        </button>
        {selected && say && (
          <Button label={c.quote} variant="primary" isDisabled={say.isDisabled}
            onClick={() => say.onSay(c.quoteRequest(who, turn.text), {
              to: "w7-group", ids: ["quote", runId, session.id, turn.id],
            })} />
        )}
      </li>
    )
  }

  return (
    <>
      <div className="group-live__row group-live__spread">
        <Heading level={4} tabIndex={-1} data-group-live-focus>{c.conclusion}</Heading>
      </div>
      {!hasFindings && !showAnswers && <Text as="p">{c.noFinding}</Text>}
      {CATEGORIES.map((category) => {
        const findings = session.findings[category]
        if (category === "changed" && session.mode === "fgd" && session.status === "done" && !findings?.length) {
          return (
            <section key={category} className="group-live__section">
              <Heading level={5}>{c.categories.changed}</Heading>
              <Text as="p">{c.noRecordedChange}</Text>
            </section>
          )
        }
        if (!findings?.length) return null
        return (
          <section key={category} className="group-live__section">
            <Heading level={5}>{c.categories[category]}</Heading>
            {findings.map((finding, i) => {
              const evidence = [...new Set(finding.turn_ids)].flatMap((id) => {
                const turn = turnById.get(id)
                return turn ? [turn] : []
              })
              return (
                <details key={`${i}:${finding.text}`} className="group-live__disclosure">
                  <summary className="group-live__finding">
                    <Icon icon="chevronRight" size="sm" aria-hidden="true" />
                    <Text weight="semibold">{finding.text}</Text>
                    <Text hasTabularNumbers>{c.count(finding.count)}</Text>
                  </summary>
                  {evidence.length > 0 ? (
                    <>
                      <Text as="p" type="supporting" color="primary">{c.evidence} · {c.selectEvidence}</Text>
                      <ul className="group-live__choices">{evidence.map((turn) => quoteRow(turn, `${category}:${i}`))}</ul>
                    </>
                  ) : <Text as="p">{c.empty}</Text>}
                </details>
              )
            })}
          </section>
        )
      })}

      {session.turns.length > 0 && (
        <details className="group-live__disclosure">
          <summary className="group-live__transcript-head">
            <Icon icon="chevronRight" size="sm" aria-hidden="true" />
            <Text weight="semibold">{c.transcript}</Text>
          </summary>
          <div className="group-live__row group-live__filters">
            <label>
              <Text type="supporting" color="primary" weight="semibold">{c.rounds}</Text>
              <select value={round} onChange={(event) => setRound(event.target.value)}>
                <option value="">{c.allRounds}</option>
                {filterRounds.map((n) => <option key={n} value={n}>{c.round(n)}</option>)}
              </select>
            </label>
            <label>
              <Text type="supporting" color="primary" weight="semibold">{c.speakers}</Text>
              <select value={speaker} onChange={(event) => setSpeaker(event.target.value)}>
                <option value="">{c.allSpeakers}</option>
                {[...filterSpeakers].map((id) => (
                  <option key={id} value={id}>{personById.get(id)?.who ?? c.unknownSpeaker}</option>
                ))}
              </select>
            </label>
          </div>
          {visible.length > 0
            ? <ul className="group-live__choices group-live__transcript">{visible.map((turn) => quoteRow(turn, "transcript"))}</ul>
            : <Text as="p" role="status">{c.emptyFilter}</Text>}
        </details>
      )}
    </>
  )
}
