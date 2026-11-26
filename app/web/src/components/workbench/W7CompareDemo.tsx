import { useId, useState } from "react"
import { Button } from "@astryxdesign/core/Button"
import { Heading } from "@astryxdesign/core/Heading"
import { Table, TableBody, TableCell, TableHeader, TableHeaderCell, TableRow } from "@astryxdesign/core/Table"
import { Text } from "@astryxdesign/core/Text"
import type { ComparisonKind, ComparisonPayload, ComparisonQuote, ComparisonSelection } from "../../chat/contract-diagnose"
import { improveCopy as c } from "../../copy/improve"
import "./diagnosis-demo.css"

const kinds = ["form", "flavor", "price"] as const

function quoteKind(quote: NonNullable<ComparisonQuote>): ComparisonKind {
  const topic = quote.topic ?? ""
  if (/price|cost|가격|지불/i.test(topic)) return "price"
  if (/form|fizz|carbon|texture|제형|탄산/i.test(topic)) return "form"
  if (/taste|flavou?r|맛|향/i.test(topic)) return "flavor"

  const words = quote.text
  if (/가격|비싸|비쌌|싸면|싸서|저렴|가성비|돈을|\d[\d,]*\s*원/.test(words)) return "price"
  if (/탄산|기포|톡\s*쏘|톡톡|청량|무탄산/.test(words)) return "form"
  if (/맛|향|달콤|단맛|달면|달 것|달까|달아|달지|새콤/.test(words)) return "flavor"
  return "form"
}

function Selection({ selection }: { selection: ComparisonSelection }) {
  const { picked, n, rate, interval } = selection
  return (
    <div className="flex flex-col gap-1">
      <Text type="large" weight="semibold" hasTabularNumbers>{c.percent(rate)}</Text>
      <Text hasTabularNumbers>{c.tally(picked, n)}</Text>
      <Text type="label" hasTabularNumbers>{c.rateInterval(interval)}</Text>
    </div>
  )
}

function PriceChart({ comparison }: { comparison: ComparisonPayload }) {
  const { priceStep } = comparison
  return (
    <figure className="w7-demo-section flex flex-col gap-3 pt-4">
      <figcaption><Heading level={4}>{c.priceTitle}</Heading></figcaption>
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {comparison.pricePoints.map(({ price, selection }, index) => (
          <li key={price} className="w7-price-row" data-original={index === 1}>
            <Text>{c.pricePosition[index]} <Text weight="semibold" hasTabularNumbers>{c.won(price)}</Text></Text>
            <div className="w7-price-track" aria-hidden="true">
              <div className="w7-price-bar" style={{ width: `${selection.rate}%` }} />
            </div>
            <Text weight="semibold" hasTabularNumbers>{c.percent(selection.rate)}</Text>
          </li>
        ))}
      </ul>
      <Text as="p">{priceStep.source === "joined-shelf"
        ? c.joinedPriceStep(priceStep.step, priceStep.medianGap, priceStep.rivalCount, priceStep.distinctPrices)
        : c.demoPriceStep(priceStep.step)}</Text>
    </figure>
  )
}

function ComparisonResult({ comparison, kind }: { comparison: ComparisonPayload; kind: ComparisonKind }) {
  const { selection, paired } = comparison.variants[kind]
  return (
    <section className="w7-demo-section flex flex-col gap-4 pt-4">
      <div className="flex flex-col gap-1">
        <Heading level={4}>{c.result}</Heading>
        <Text as="p">{c.headcount(selection.n)}</Text>
      </div>
      <Table aria-label={c.result} density="compact" className="w-full table-fixed text-left">
        <TableHeader>
          <TableRow>
            <TableHeaderCell scope="col">{c.original}</TableHeaderCell>
            <TableHeaderCell scope="col">{c.variant}</TableHeaderCell>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableCell><Selection selection={comparison.base.selection} /></TableCell>
            <TableCell><Selection selection={selection} /></TableCell>
          </TableRow>
        </TableBody>
      </Table>
      <dl className="w7-pair-outcomes m-0">
        <div className="flex flex-col gap-1">
          <dt><Text>{c.lost}</Text></dt>
          <dd className="m-0"><Text type="large" weight="semibold" hasTabularNumbers>{c.people(paired.lost)}</Text></dd>
        </div>
        <div className="flex flex-col gap-1">
          <dt><Text>{c.gained}</Text></dt>
          <dd className="m-0"><Text type="large" weight="semibold" hasTabularNumbers>{c.people(paired.gained)}</Text></dd>
        </div>
        <div className="flex flex-col gap-1">
          <dt><Text>{c.changeLabel}</Text></dt>
          <dd className="m-0 flex flex-col gap-1">
            <Text type="large" weight="semibold" hasTabularNumbers>{c.delta(paired.difference)}</Text>
            <Text type="label" hasTabularNumbers>{c.deltaInterval(paired.interval)}</Text>
          </dd>
        </div>
      </dl>
      <details>
        <summary className="w7-interval-summary py-2"><Text weight="semibold">{c.intervalLabel}</Text></summary>
        <Text as="p">{c.intervalInfo}</Text>
      </details>
    </section>
  )
}

type Props = {
  comparison: ComparisonPayload
  quote: ComparisonQuote
  onBack: () => void
}

function ComparePanel({ comparison, quote, onBack, initialKind }: Props & { initialKind: ComparisonKind }) {
  const [kind, setKind] = useState(initialKind)
  const [visibleResult, setVisibleResult] = useState<ComparisonKind | null>(null)
  const resultId = useId()
  const topic = c.topics[kind]
  const quoted = kind === initialKind ? quote : null
  const values = kind === "price"
    ? { before: c.won(comparison.base.price), after: c.won(comparison.pricePoints[0].price) }
    : c.values[kind]
  const showing = visibleResult === kind

  return (
    <section className="w7-compare flex min-w-0 flex-col gap-4">
      <header className="flex flex-col gap-1">
        <Heading level={3}>{c.title}</Heading>
        <Text as="p">{c.source}</Text>
      </header>
      <div className="flex flex-wrap gap-2" role="group" aria-label={c.comparisonOptions}>
        {kinds.map(option => (
          <Button key={option} size="md" variant={kind === option ? "secondary" : "ghost"}
            label={c.topics[option].label} aria-pressed={kind === option} onClick={() => setKind(option)} />
        ))}
      </div>
      <div className="w7-diagnosis-proposal flex flex-col gap-3 p-4">
        <div className="flex flex-col gap-1">
          <Heading level={4}>{c.hypothesis}</Heading>
          <Text as="p">{topic.hypothesis}</Text>
        </div>
        {quoted ? (
          <figure className="w7-demo-quote m-0 flex flex-col gap-1 pl-3">
            <figcaption><Text type="label" weight="semibold">{c.quoteLabel(quoted.person)}</Text></figcaption>
            <blockquote className="m-0"><Text as="p">{quoted.text}</Text></blockquote>
          </figure>
        ) : <Text as="p">{topic.evidence}</Text>}
        <div className="flex flex-col gap-1">
          <Text weight="semibold">{c.change}</Text>
          <Text type="large" weight="semibold">{values.before} → {values.after}</Text>
          <Text>{c.conditions(comparison.volumeMl, kind === "price" ? undefined : comparison.base.price)}</Text>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button size="lg" label={showing ? c.hide : c.run} variant={showing ? "secondary" : "primary"}
          aria-expanded={showing} aria-controls={resultId} onClick={() => setVisibleResult(showing ? null : kind)} />
        <Button size="lg" label={c.back} variant="ghost" onClick={onBack} />
      </div>
      <p className="sr-only" role="status">{showing ? c.resultReady : ""}</p>
      <div id={resultId} hidden={!showing}>
        {showing && (
          <div className="flex flex-col gap-5">
            <ComparisonResult comparison={comparison} kind={kind} />
            <PriceChart comparison={comparison} />
          </div>
        )}
      </div>
    </section>
  )
}

export function W7CompareDemo({ comparison, quote, onBack }: Props) {
  const initialKind = quote ? quoteKind(quote) : comparison.focus ?? "form"
  return <ComparePanel key={`${quote?.id ?? "default"}:${initialKind}`} initialKind={initialKind}
    comparison={comparison} quote={quote} onBack={onBack} />
}
