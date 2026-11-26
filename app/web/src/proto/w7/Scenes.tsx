import { useState } from "react"
import { Button } from "@astryxdesign/core/Button"
import { HStack } from "@astryxdesign/core/HStack"
import { Icon } from "@astryxdesign/core/Icon"
import { Text } from "@astryxdesign/core/Text"
import { Token } from "@astryxdesign/core/Token"
import { VStack } from "@astryxdesign/core/VStack"
import { Tag } from "../../components/workbench/OriginTag"
import type { DiagnosisPayload } from "../../chat/contract-diagnose"
import { DiagnosisCard } from "../../components/workbench/DiagnosisCard"
import { diagnoseCopy } from "../../copy/diagnose"
import { w7 } from "./copy"
import {
  compare,
  concept,
  methods,
  panel,
  questions,
  sessions,
  shelfResult,
  variant,
  type Finding,
  type Turn,
} from "./data"
import { BenchCard, RadioMark, SubHead, personOf, quoteLabel, speakerLabel } from "./parts"
import type { ProtoState } from "./W7ProtoPage"

const pct = (n: number, total: number) => `${(n / total) * 100}%`

/* ═════════════ 장면 A. 컨셉 진단 ═════════════ */

export function SceneA({ payload, failed, retry }: {
  payload: DiagnosisPayload | null
  failed: boolean
  retry: () => void
}) {
  return (
    <BenchCard title={diagnoseCopy.title}
      source={payload?.sections.some(section => section.source?.startsWith("제공") || section.source?.includes("정량조사"))
        ? "provided" : undefined}>
      {payload ? <DiagnosisCard payload={payload} /> : (
        <div role="status" className="flex flex-col items-start gap-3">
          <Text>{failed ? diagnoseCopy.unavailable : diagnoseCopy.loading}</Text>
          {failed && <Button label={diagnoseCopy.retry} variant="secondary" onClick={retry} />}
        </div>
      )}
    </BenchCard>
  )
}

/* ═════════════ 장면 B. 테스트 결과 ═════════════ */

function CountBar({ label, n, total, isSelf }: { label: string; n: number; total: number; isSelf?: boolean }) {
  return (
    <div className="w7-countbar">
      <Text>{label}</Text>
      <div className="w7-bar" aria-hidden="true">
        <span data-fill={isSelf ? "strong" : "soft"} style={{ width: pct(n, total) }} />
      </div>
      <Text hasTabularNumbers weight="semibold">
        {w7.b.people(n)}
      </Text>
    </div>
  )
}

export function SceneB({ state, set }: { state: ProtoState; set: (p: Partial<ProtoState>) => void }) {
  const r = shelfResult
  return (
    <VStack gap={4}>
      <BenchCard
        title={w7.b.resultTitle}
        source="demo"
        aside={<Tag>{w7.b.rank(r.rank, r.shelfSize)}</Tag>}
      >
        <Text type="large" weight="semibold">
          {w7.b.picked(panel.total, r.picked)}
        </Text>
        <VStack gap={2}>
          <CountBar label={w7.b.original} n={r.picked} total={panel.total} isSelf />
          {state.aChoice !== "original" && <CountBar label={w7.b.fixed} n={r.fixPicked} total={panel.total} />}
        </VStack>
        <div>
          <SubHead>{w7.b.from}</SubHead>
          <div className="w7-cells pt-2">
            {[
              [w7.b.fromOwn, r.fromOwn],
              [w7.b.fromRival, r.fromRival],
              [w7.b.fromNone, r.fromNone],
            ].map(([k, v]) => (
              <div key={k as string} className="w7-cell">
                <Text type="supporting" color="primary">{k as string}</Text>
                <Text type="large" weight="semibold" hasTabularNumbers>
                  {w7.b.people(v as number)}
                </Text>
              </div>
            ))}
          </div>
        </div>
      </BenchCard>
      <BenchCard title={w7.b.askTitle} source="demo">
        <div role="radiogroup" aria-label={w7.b.askTitle} className="w7-options">
          {questions.map((q) => {
            const on = state.question === q.id
            return (
              <button
                key={q.id}
                type="button"
                role="radio"
                aria-checked={on}
                data-proto-option
                data-on={on || undefined}
                onClick={() => set({ question: q.id })}
              >
                <RadioMark isOn={on} />
                <span className="flex min-w-0 flex-col gap-0.5">
                  <Text weight="semibold">{w7.b.questions[q.id].q}</Text>
                  <Text>{w7.b.questions[q.id].basis}</Text>
                </span>
              </button>
            )
          })}
        </div>
        <SubHead>{w7.b.methodTitle}</SubHead>
        <div role="radiogroup" aria-label={w7.b.methodTitle} className="w7-options" data-cols="3">
          {methods.map((m) => {
            const on = state.method === m.id
            return (
              <button
                key={m.id}
                type="button"
                role="radio"
                aria-checked={on}
                aria-disabled={!m.isReady || undefined}
                title={m.isReady ? undefined : w7.b.notReady}
                data-proto-option
                data-on={on || undefined}
                data-disabled={!m.isReady || undefined}
                onClick={() => m.isReady && set({ method: m.id })}
              >
                <RadioMark isOn={on} />
                <span className="flex min-w-0 flex-col gap-0.5">
                  <Text weight="semibold">{w7.b.methods[m.id].name}</Text>
                  <Text>{w7.b.methods[m.id].when}</Text>
                </span>
              </button>
            )
          })}
        </div>
      </BenchCard>
    </VStack>
  )
}

/* ═════════════ 장면 D. 결론과 근거 발언 ═════════════ */

function QuoteRow({ turn, isOn, onPick }: { turn: Turn; isOn: boolean; onPick: () => void }) {
  const p = turn.person === "host" ? null : personOf(turn.person)
  return (
    <button type="button" role="radio" aria-checked={isOn} data-proto-option data-on={isOn || undefined} onClick={onPick}>
      <RadioMark isOn={isOn} />
      <span className="flex min-w-0 flex-col gap-1">
        <HStack gap={2} vAlign="center" wrap="wrap">
          <Text type="supporting" weight="semibold" color="primary">
            {speakerLabel(turn)}
          </Text>
          <Tag>{w7.d.round(turn.round)}</Tag>
          {p && <Tag isDashed={!p.picked}>{p.picked ? w7.c.picked : w7.c.passed}</Tag>}
          {turn.changed && <Tag>{w7.c.changed}</Tag>}
        </HStack>
        <Text>{turn.text}</Text>
      </span>
    </button>
  )
}

function FindingRow({
  f,
  turns,
  quote,
  onQuote,
}: {
  f: Finding
  turns: Turn[]
  quote: string | null
  onQuote: (id: string) => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className="w7-finding" data-open={open || undefined}>
      <button type="button" className="w7-finding__head" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <Icon icon={open ? "chevronDown" : "chevronRight"} size="sm" />
        <span className="min-w-0 flex-1">
          <Text weight="semibold">{f.text}</Text>
        </span>
        <Text hasTabularNumbers weight="semibold">
          {w7.d.count(f.count)}
        </Text>
      </button>
      {open && (
        <div role="radiogroup" aria-label={f.text} className="w7-options pt-2 pb-1">
          {f.turnIds.map((id) => {
            const t = turns.find((x) => x.id === id)!
            return <QuoteRow key={id} turn={t} isOn={quote === id} onPick={() => onQuote(id)} />
          })}
        </div>
      )}
    </div>
  )
}

type Filter = "all" | "picked" | "passed"

export function SceneD({
  method,
  quote,
  onQuote,
}: {
  method: "fgi" | "fgd"
  quote: string | null
  onQuote: (id: string) => void
}) {
  const session = sessions[method]
  const [full, setFull] = useState(false)
  const [filter, setFilter] = useState<Filter>("all")
  const groups = (["agreed", "split", "changed"] as const).filter((g) => session.findings.some((f) => f.group === g))
  const shown = session.turns.filter((t) => {
    if (filter === "all") return true
    if (t.person === "host") return false
    return personOf(t.person).picked === (filter === "picked")
  })
  return (
    <VStack gap={4}>
      <BenchCard
        title={w7.steps[3]}
        source="demo"
        aside={
          <Button
            label={full ? w7.d.fullClose : w7.d.fullOpen}
            variant="ghost"
            size="sm"
            onClick={() => setFull((v) => !v)}
          />
        }
      >
        {groups.map((g) => (
          <div key={g}>
            <SubHead>{w7.d.groups[g]}</SubHead>
            <div className="pt-1">
              {session.findings
                .filter((f) => f.group === g)
                .map((f) => (
                  <FindingRow key={f.id} f={f} turns={session.turns} quote={quote} onQuote={onQuote} />
                ))}
            </div>
          </div>
        ))}
      </BenchCard>
      {full && (
        <BenchCard title={w7.d.fullOpen} source="demo">
          <HStack gap={2} wrap="wrap">
            {(["all", "picked", "passed"] as const).map((k) => (
              <Token
                key={k}
                label={k === "all" ? w7.d.filterAll : k === "picked" ? w7.d.filterPicked : w7.d.filterPassed}
                color={filter === k ? "gray" : "default"}
                onClick={() => setFilter(k)}
              />
            ))}
          </HStack>
          <div role="radiogroup" aria-label={w7.d.fullOpen} className="w7-options">
            {shown.map((t) => (
              <QuoteRow key={t.id} turn={t} isOn={quote === t.id} onPick={() => onQuote(t.id)} />
            ))}
          </div>
        </BenchCard>
      )}
    </VStack>
  )
}

/* ═════════════ 장면 E. 비교와 채택 ═════════════ */

function FlowBar() {
  const c = compare
  const segs = [
    { k: "both", n: c.both, isChanged: false },
    { k: "gained", n: c.gained, isChanged: true },
    { k: "lost", n: c.lost, isChanged: true },
    { k: "neither", n: c.neither, isChanged: false },
  ] as const
  return (
    <div>
      <div className="w7-flow" role="img" aria-label={segs.map((s) => `${w7.e.segments[s.k]} ${s.n}명`).join(", ")}>
        {segs.map((s) => (
          <span key={s.k} data-seg={s.k} data-w7-changed={s.isChanged || undefined} style={{ width: pct(s.n, c.total) }} />
        ))}
      </div>
      <div className="w7-flow__legend">
        {segs.map((s) => (
          <div key={s.k} data-w7-changed={s.isChanged || undefined}>
            <span className="w7-swatch" data-kind={s.k} />
            <Text type="supporting" color="primary" weight={s.isChanged ? "semibold" : "normal"}>
              {w7.e.segments[s.k]}
            </Text>
            <Text weight="semibold" hasTabularNumbers>
              {w7.b.people(s.n)}
            </Text>
          </div>
        ))}
      </div>
    </div>
  )
}

function RangeBar({ name, picked, range, isChanged }: { name: string; picked: number; range: readonly [number, number]; isChanged?: boolean }) {
  const t = compare.total
  return (
    <div className="w7-rangebar">
      <Text weight={isChanged ? "semibold" : "normal"}>{name}</Text>
      <div className="w7-range" aria-hidden="true">
        <span className="w7-range__span" style={{ left: pct(range[0], t), width: pct(range[1] - range[0], t) }} />
        <span className="w7-range__dot" data-w7-changed={isChanged || undefined} style={{ left: pct(picked, t) }} />
      </div>
      <div className="flex flex-col items-end">
        <Text weight="semibold" hasTabularNumbers>
          {w7.e.of(t, picked)}
        </Text>
        <Text type="supporting" hasTabularNumbers>
          {w7.e.range(range[0], range[1])}
        </Text>
      </div>
    </div>
  )
}

function Adopted({ quote }: { quote: Turn }) {
  const S = w7.adopted.spec
  const rows: [string, string, string | null][] = [
    [S.name, concept.name, null],
    [S.flavor, concept.flavor, null],
    [S.form, variant.change.to, variant.change.from],
    [S.pack, concept.pack, null],
    [S.price, w7.won(concept.price), null],
    [S.sale, concept.sale, null],
  ]
  return (
    <VStack gap={4}>
      <BenchCard title={concept.name}>
        <div className="w7-spec">
          {rows.map(([k, v, from]) => (
            <div key={k} className="w7-spec__row" data-w7-changed={from ? true : undefined}>
              <Text type="supporting" color="primary">{k}</Text>
              <HStack gap={2} vAlign="center" wrap="wrap">
                <Text weight={from ? "semibold" : "normal"}>{from ? w7.adopted.specChange(from, v) : v}</Text>
                {from && <Tag>{w7.adopted.changedMark}</Tag>}
              </HStack>
            </div>
          ))}
        </div>
      </BenchCard>
      <BenchCard title={w7.adopted.logTitle} source="demo">
        <VStack gap={2}>
          <Text weight="semibold">{w7.adopted.logWhat(variant.change.from, variant.change.to)}</Text>
          <Text>{w7.adopted.logWhy(compare.gained, compare.lost, compare.total)}</Text>
          <div className="w7-quote">
            <Text type="supporting" weight="semibold" color="primary">
              {w7.adopted.logQuote(quoteLabel(quote))}
            </Text>
            <Text as="p" display="block">
              {quote.text}
            </Text>
          </div>
        </VStack>
      </BenchCard>
    </VStack>
  )
}

export function SceneE({ quote, adopted }: { quote: Turn; method: "fgi" | "fgd"; adopted: boolean }) {
  if (adopted) return <Adopted quote={quote} />
  const c = compare
  const g = c.gainedWho
  const maxGroup = Math.max(...g.groups.map((x) => x.count))
  return (
    <VStack gap={4}>
      <BenchCard
        title={w7.e.title}
        source="demo"
        aside={
          <span data-proto-verdict={c.verdict} className="inline-flex items-center gap-1">
            <Icon icon={c.verdict === "better" ? "arrowUp" : c.verdict === "worse" ? "arrowDown" : "info"} size="sm" />
            <Text weight="semibold">{w7.e.verdict[c.verdict]}</Text>
          </span>
        }
      >
        <Text type="large" weight="semibold">
          {w7.e.headline(c.total, c.original.picked, c.changed.picked, c.gained, c.lost)}
        </Text>
        <FlowBar />
        <Text weight="semibold" hasTabularNumbers>
          {w7.e.net(c.net.value, c.net.range[0], c.net.range[1])}
        </Text>
        <div>
          <SubHead>{w7.e.countsTitle}</SubHead>
          <VStack gap={2}>
            <RangeBar name={w7.e.originalName} picked={c.original.picked} range={c.original.range} />
            <RangeBar name={w7.e.changedName} picked={c.changed.picked} range={c.changed.range} isChanged />
          </VStack>
        </div>
      </BenchCard>
      <div className="w7-two">
        <BenchCard title={w7.e.whoTitle(c.gained)} source="demo">
          <VStack gap={2}>
            {g.groups.map((x) => (
              <CountBar key={x.label} label={x.label} n={x.count} total={maxGroup} />
            ))}
          </VStack>
          <div>
            <SubHead>{w7.e.usualTitle}</SubHead>
            <div className="w7-split pt-2" aria-hidden="true">
              <span data-fill="strong" style={{ width: pct(g.usualOwn, c.gained) }} />
              <span data-fill="soft" style={{ width: pct(g.usualRival, c.gained) }} />
            </div>
            <div className="flex justify-between pt-1">
              <Text type="supporting" color="primary">{`${w7.e.own} ${g.usualOwn}명`}</Text>
              <Text type="supporting" color="primary">{`${w7.e.rival} ${g.usualRival}명`}</Text>
            </div>
          </div>
          <Text>{w7.e.lostNote(c.lost, c.lostWho.usualOwn, c.lostWho.usualRival)}</Text>
        </BenchCard>
        <BenchCard title={w7.e.basisTitle} source="demo">
          <div className="w7-quote">
            <Text type="supporting" weight="semibold" color="primary">
              {quoteLabel(quote)}
            </Text>
            <Text as="p" display="block">
              {quote.text}
            </Text>
          </div>
          <div className="w7-hypo">
            <SubHead>{w7.e.hypothesis}</SubHead>
            <Text>{w7.e.hypothesisText}</Text>
            <SubHead>{w7.e.evidence}</SubHead>
            <Text>{w7.e.evidenceCount(c.reasonCount, c.reasonOf)}</Text>
            <SubHead>{w7.e.changeOne}</SubHead>
            <Text weight="semibold">{w7.e.changeLine(variant.change.from, variant.change.to)}</Text>
            <Text>{w7.e.keepLine}</Text>
          </div>
        </BenchCard>
      </div>
    </VStack>
  )
}
