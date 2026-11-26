import { useEffect, useState, type ReactNode } from "react"
import { Badge } from "@astryxdesign/core/Badge"
import { Card } from "@astryxdesign/core/Card"
import { Heading } from "@astryxdesign/core/Heading"
import { HStack } from "@astryxdesign/core/HStack"
import { Icon } from "@astryxdesign/core/Icon"
import { SegmentedControl, SegmentedControlItem } from "@astryxdesign/core/SegmentedControl"
import { Text } from "@astryxdesign/core/Text"
import { VStack } from "@astryxdesign/core/VStack"
import { ArrowRightIcon } from "@heroicons/react/20/solid"
import { planCopy, w6 } from "./copy"
import { person, picks, said, SIZE, type Phase } from "./crowd"
import { plans, survey, type PlanId } from "./data"

function BenchCard({ title, mark, aside, children }: { title: string; mark?: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <div className="w6-in">
      <Card padding={5}>
        <VStack gap={4}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <HStack gap={2} vAlign="center">
              <Heading level={3}>{title}</Heading>
              {mark && <Badge label={mark} />}
            </HStack>
            {aside}
          </div>
          {children}
        </VStack>
      </Card>
    </div>
  )
}

export function ReportScene() {
  const c = w6.s0
  return (
    <div className="w6-in mx-auto max-w-3xl">
      <Card padding={8}>
        <VStack gap={5}>
          <HStack gap={2} vAlign="center"><Heading level={2}>{c.title}</Heading><Badge label={w6.sample} /></HStack>
          <Text weight="semibold">{c.verdict}</Text>
          <div className="w6-key">
            {c.key.map((k) => (
              <div key={k.label}><Text type="supporting">{k.label}</Text><Text weight="semibold">{k.value}</Text></div>
            ))}
          </div>
          <VStack gap={3}>
            <Heading level={4}>{c.askTitle}</Heading>
            <ol className="w6-asks">{c.asks.map((a) => <li key={a}><Text>{a}</Text></li>)}</ol>
          </VStack>
        </VStack>
      </Card>
    </div>
  )
}

function Words({ title, items }: { title: string; items: { text: string; n: number; want: number }[] }) {
  const c = w6.s1
  return (
    <VStack gap={2}>
      <Heading level={4}>{title}</Heading>
      <div>
        <div className="w6-word" data-head>{c.head.map((h) => <Text key={h} type="supporting" weight="medium">{h}</Text>)}</div>
        {items.map((x) => (
          <div className="w6-word" key={x.text}>
            <Text>{x.text}</Text>
            <Text weight="semibold">{c.people(x.n)}</Text>
            <Text>{c.want(x.want)}</Text>
          </div>
        ))}
      </div>
    </VStack>
  )
}

/** 가상 소비자와 실제 20대. fixed면 가상 소비자의 표시가 실제로 옮겨 간다. */
export function DiffScene({ fixed }: { fixed: boolean }) {
  const c = w6.s1
  const [moved, setMoved] = useState(false)
  useEffect(() => {
    const t = window.setTimeout(() => setMoved(fixed), 500)
    return () => window.clearTimeout(t)
  }, [fixed])
  return (
    <VStack gap={4}>
      <BenchCard title={c.diffTitle} aside={<Text>{c.diffUnit}</Text>}>
        <div>
          {c.diffs.map((d) => (
            <div className="w6-diff" key={d.text}>
              <Heading level={4}>{d.text}</Heading>
              <div className="w6-diffbars">
                <Text>{c.virtual}</Text>
                <div className="w6-bar"><i data-kind="virtual" style={{ width: `${moved ? d.r : d.v}%` }} /></div>
                <Text weight="semibold">{w6.track.unit(moved ? d.r : d.v)}</Text>
                <Text>{c.actual}</Text>
                <div className="w6-bar"><i data-kind="actual" style={{ width: `${d.r}%` }} /></div>
                <Text weight="semibold">{w6.track.unit(d.r)}</Text>
              </div>
              <div>{moved && <Badge label={c.done} />}</div>
            </div>
          ))}
        </div>
      </BenchCard>
      {fixed && (
        <BenchCard title={w6.s2.confirmTitle}>
          <div className="w6-rows">
            {w6.s2.rows.map((r) => <div key={r.k}><Text type="supporting">{r.k}</Text><Text>{r.v}</Text></div>)}
          </div>
        </BenchCard>
      )}
    </VStack>
  )
}

function Crowd({ phase, from, selected, onSelect }: { phase: Phase; from: Phase; selected: number | null; onSelect: (i: number) => void }) {
  const c = w6.s2b
  return (
    <VStack gap={3}>
      <div className="w6-crowd">
        {Array.from({ length: SIZE }, (_, i) => {
          const on = picks[phase].has(i)
          const was = picks[from].has(i)
          const state = on ? (was || phase === from ? "on" : "gain") : was && phase !== from ? "lost" : "off"
          return (
            <button
              key={i}
              type="button"
              data-state={state}
              data-selected={selected === i || undefined}
              aria-label={person(i).who}
              onClick={() => onSelect(i)}
            />
          )
        })}
      </div>
      <div className="w6-legend">
        {(["on", "gain", "lost"] as const).map((k) => (
          <span key={k}><i data-state={k} /><Text type="supporting">{c.legend[k]}</Text></span>
        ))}
      </div>
    </VStack>
  )
}

function PersonPanel({ id, phase, showReal = true }: { id: number | null; phase: Phase; showReal?: boolean }) {
  const c = w6.s2b
  if (id === null) return <div className="w6-person" data-empty><Text>{c.empty}</Text></div>
  const p = person(id)
  return (
    <div className="w6-person" key={id}>
      <Heading level={4}>{p.who}</Heading>
      {showReal && (
        <>
          <Text type="supporting" weight="medium">{c.realHead}</Text>
          <ul>{p.real.map((t) => <li key={t} data-added><Text weight="semibold">{t}</Text></li>)}</ul>
        </>
      )}
      <Text type="supporting" weight="medium">{c.pickHead}</Text>
      <div className="w6-said" data-on={picks[phase].has(id) || undefined}><Text weight="semibold">{said(id, phase)}</Text></div>
    </div>
  )
}

export function RetestScene() {
  const c = w6.s2b
  const [phase, setPhase] = useState<"prev" | "base">("prev")
  const [id, setId] = useState<number | null>(null)
  // 처음 결과를 잠깐 보인 뒤 다시 테스트한 결과로 바꾼다
  useEffect(() => {
    const t = window.setTimeout(() => {
      setPhase("base")
      setId([...picks.prev].find((i) => !picks.base.has(i) && person(i).kind === "price") ?? null)
    }, 1600)
    return () => window.clearTimeout(t)
  }, [])
  return (
    <VStack gap={4}>
      <BenchCard
        title={c.title}
        mark={w6.sample}
        aside={
          <HStack gap={4} vAlign="center">
            <Heading level={3}>{c.counts(picks[phase].size)}</Heading>
            <SegmentedControl label={c.title} value={phase} onChange={(v) => setPhase(v as "prev" | "base")}>
              <SegmentedControlItem value="prev" label={c.prev} />
              <SegmentedControlItem value="base" label={c.now} />
            </SegmentedControl>
          </HStack>
        }
      >
        <div className="w6-scene">
          <Crowd phase={phase} from="prev" selected={id} onSelect={setId} />
          <PersonPanel id={id} phase={phase} showReal={phase === "base"} />
        </div>
      </BenchCard>
      <BenchCard title={c.whyTitle} mark={w6.sample}>
        <div className="w6-facts">
          {c.whys.map((x) => <div key={x.t}><Heading level={3}>{x.n}</Heading><Text>{x.t}</Text></div>)}
        </div>
      </BenchCard>
    </VStack>
  )
}

export function IdeasScene() {
  const c = w6.s3
  const q = w6.s1
  const top = Math.max(...survey.curve.map((p) => p.money))
  return (
    <VStack gap={4}>
      <BenchCard title={c.title} mark={w6.real}>
        <div>
          {c.rows.map((r) => (
            <div className="w6-idea" key={r.tag}>
              <div><Heading level={4}>{r.tag}</Heading><Text type="supporting">{r.kind}</Text></div>
              <div><Text>{r.heard}</Text><Text weight="semibold">{r.n}</Text></div>
              <Icon icon={ArrowRightIcon} size="sm" />
              <div><span className="w6-to"><Text>{r.before}</Text></span><Heading level={4}>{r.after}</Heading></div>
              <Text>{r.why}</Text>
            </div>
          ))}
        </div>
      </BenchCard>
      <BenchCard title={q.priceTitle} mark={w6.real}>
        <div className="w6-cols">
          {survey.curve.map((p) => {
            const isPeak = p.money === top
            const isNow = p.price === 1800
            return (
              <div className="w6-col" key={p.price} data-peak={isPeak || undefined} data-now={isNow || undefined}>
                <em><Text type="supporting" weight="semibold">{isPeak ? q.peak : isNow ? q.now : ""}</Text></em>
                <Text weight="semibold">{q.man(p.money)}</Text>
                <i style={{ height: `${(p.money / top) * 6}rem` }} />
                <Text weight="semibold">{w6.won(p.price)}</Text>
                <Text type="supporting">{q.pay(p.share)}</Text>
              </div>
            )
          })}
        </div>
      </BenchCard>
      <BenchCard title={q.wordsTitle} mark={w6.real}>
        <div className="w6-words">
          <Words title={q.bad} items={q.bads} />
          <Words title={q.good} items={q.goods} />
        </div>
      </BenchCard>
    </VStack>
  )
}

export function CompareScene() {
  const c = w6.s4
  const top = Math.max(...plans.map((p) => p.net))
  const [plan, setPlan] = useState<PlanId>("base")
  const [auto, setAuto] = useState(true)
  const [id, setId] = useState<number | null>(() => [...picks.ab].find((i) => !picks.base.has(i) && person(i).kind === "price") ?? null)
  // 처음에는 안을 차례로 보여 준다. 하나를 누르면 멈춘다
  useEffect(() => {
    if (!auto) return
    const order: PlanId[] = ["base", "a", "b", "c", "ab"]
    const next = order[order.indexOf(plan) + 1]
    if (!next) return
    const t = window.setTimeout(() => setPlan(next), 1300)
    return () => window.clearTimeout(t)
  }, [auto, plan])
  return (
    <VStack gap={4}>
      <BenchCard title={c.title} mark={w6.sample}>
        <div className="w6-scene" data-compare>
          <div className="w6-plans">
            <div className="w6-planhead"><span /><Text type="supporting">{c.cols[1]}</Text><Text type="supporting">{c.cols[2]}</Text></div>
            {plans.map((p) => (
              <button
                key={p.id}
                type="button"
                className="w6-planrow"
                data-on={plan === p.id || undefined}
                onClick={() => {
                  setAuto(false)
                  setPlan(p.id)
                }}
              >
                <span><Text weight="semibold">{planCopy[p.id].tag}</Text><Text>{planCopy[p.id].name}</Text></span>
                <span><Text weight="semibold">{c.picked(p.picked)}</Text><Text>{p.verdict ? c.verdict[p.verdict] : ""}</Text></span>
                <span>
                  <Text weight="semibold">{c.eok(p.net)}{p.net === top ? ` (${c.best})` : ""}</Text>
                  <span className="w6-bar" data-best={p.net === top || undefined}><i style={{ width: `${(p.net / 60) * 100}%` }} /></span>
                </span>
              </button>
            ))}
          </div>
          <VStack gap={3}>
            <Crowd phase={plan} from="base" selected={id} onSelect={setId} />
            <PersonPanel id={id} phase={plan} />
          </VStack>
        </div>
      </BenchCard>
    </VStack>
  )
}

export function RevisedScene() {
  const c = w6.s5
  return (
    <VStack gap={4}>
      <BenchCard title={c.title} mark={w6.sample}>
        <div className="w6-stats">
          {c.stats.map((s) => (
            <div key={s.label}><Text type="supporting">{s.label}</Text><Heading level={2}>{s.a} → {s.b}</Heading></div>
          ))}
        </div>
        <div className="w6-board">
          <div data-head />
          <div data-head><Text weight="semibold">{c.v1}</Text></div>
          <div data-head><Text weight="semibold">{c.v2}</Text></div>
          {c.rows.map((r) => [
            <div key={`${r.k}k`}><Text type="supporting">{r.k}</Text></div>,
            <div key={`${r.k}a`}><Text>{r.a}</Text></div>,
            <div key={`${r.k}b`} data-changed={r.changed || undefined}>
              <Text weight={r.changed ? "semibold" : "normal"}>{r.b}</Text>
              {r.why && <Text>{r.why}</Text>}
            </div>,
          ])}
        </div>
      </BenchCard>
      <BenchCard title={c.leftTitle}>
        <ol className="w6-asks">{c.left.map((a) => <li key={a}><Text>{a}</Text></li>)}</ol>
      </BenchCard>
    </VStack>
  )
}
