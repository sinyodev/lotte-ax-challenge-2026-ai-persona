import { Heading } from "@astryxdesign/core/Heading"
import { ProgressBar } from "@astryxdesign/core/ProgressBar"
import { Text } from "@astryxdesign/core/Text"
import { VStack } from "@astryxdesign/core/VStack"
import type { RunView } from "../../chat/contract"
import type { ImproveGroup, ImprovePaired } from "../../chat/contract-improve"
import { improveCardCopy as t } from "../../copy/improve"

const SEGMENTS = ["both", "gained", "lost", "neither"] as const

function Flow({ paired }: { paired: ImprovePaired }) {
  return (
    <div>
      <div className="improve-flow" aria-hidden="true">
        {SEGMENTS.map((key) => paired[key] > 0 && (
          <span key={key} data-segment={key} style={{ flexGrow: paired[key] }} />
        ))}
      </div>
      <dl className="improve-flow-legend">
        {SEGMENTS.map((key) => (
          <div key={key}>
            <dt><span data-segment={key} aria-hidden="true" /><Text>{t.segments[key]}</Text></dt>
            <dd><Text weight="semibold" hasTabularNumbers>{t.people(paired[key])}</Text></dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function Rate({ title, n, picked, rate }: { title: string; n: number; picked: number; rate: number }) {
  return (
    <div className="improve-rate">
      <div className="improve-rate-label">
        <Text weight="semibold">{title}</Text>
        <Text hasTabularNumbers>{t.tally(picked, n)} · {t.percent(rate)}</Text>
      </div>
      <div className="improve-rate-track" aria-hidden="true"><span style={{ width: `${rate}%` }} /></div>
    </div>
  )
}

function GroupList({ title, groups, total }: { title: string; groups?: ImproveGroup[]; total: number }) {
  return (
    <div className="improve-groups">
      <Heading level={5}>{title}</Heading>
      {groups?.length ? (
        <dl>
          {groups.map(({ label, count }, index) => (
            <div key={`${label}:${index}`}>
              <dt><Text>{label}</Text></dt>
              <dd><Text weight="semibold" hasTabularNumbers>{t.people(count)}</Text></dd>
            </div>
          ))}
        </dl>
      ) : total > 0 ? <Text as="p">{t.noGroups}</Text> : null}
    </div>
  )
}

export function ImprovePairedResult({ paired, partial }: { paired: ImprovePaired; partial: boolean }) {
  const { n, gained, lost, delta_pp, low_pp, high_pp, verdict } = paired
  return (
    <section className="improve-comparison" aria-label={t.pairedTitle}>
      <VStack gap={3}>
        <Heading level={4}>{partial ? t.provisional : t.verdict[verdict]}</Heading>
        <Text as="p">{t.turnover(gained, lost)}</Text>
        <details className="improve-sales">
          <summary>{t.pairDetails}</summary>
          <VStack gap={3}>
            <Text as="p">{t.pairedDenominator(n)}</Text>
            <Flow paired={paired} />
            <Text as="p">{t.deltaTitle} {t.delta(delta_pp)} ({t.deltaInterval([low_pp, high_pp])})</Text>
            <Text as="p">{t.intervalMeaning}</Text>
            <div className="improve-group-grid">
              <GroupList title={t.gainedTitle(gained)} groups={paired.gained_groups} total={gained} />
              <GroupList title={t.lostTitle(lost)} groups={paired.lost_groups} total={lost} />
            </div>
          </VStack>
        </details>
      </VStack>
    </section>
  )
}

/** 같은 사람의 두 선택을 짝짓기 전에는 응답 현황과 각 매대에서 관찰한 값만 보여준다. */
export function ImproveRunSummary({ base, changed, noPairs }: {
  base?: RunView; changed: RunView; noPairs: boolean
}) {
  const gathering = changed.status === "running"
  const active = gathering ? changed : base?.status === "running" ? base : null
  const original = base?.result
  const result = changed.result
  return (
    <section className="improve-comparison" aria-label={active ? t.responses : t.rateTitle}>
      <VStack gap={3}>
        {active ? <>
          <Heading level={4}>{gathering ? t.waitChanged : t.waitOriginal}</Heading>
          <div className="improve-rate" role="status">
            <Text hasTabularNumbers>{t.progress(active.asked, active.total)}</Text>
            <ProgressBar label={t.responses} isLabelHidden variant="neutral" value={active.asked} max={Math.max(active.total, 1)} />
          </div>
          {gathering && base?.status === "done" && !!original?.n && (
            <Text as="p">{t.baselinePicked(original.picked, original.n)}</Text>
          )}
        </> : <>
          <Heading level={4}>{t.independentTitle}</Heading>
          {!!original?.n && <Rate title={t.original} n={original.n} picked={original.picked} rate={100 * original.picked / original.n} />}
          {!!result?.n && <Rate title={t.changed} n={result.n} picked={result.picked} rate={100 * result.picked / result.n} />}
          <Text as="p">{noPairs ? t.noPairs : t.separateBasis}</Text>
        </>}
      </VStack>
    </section>
  )
}
