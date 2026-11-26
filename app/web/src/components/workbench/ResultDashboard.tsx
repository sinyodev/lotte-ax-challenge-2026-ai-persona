/**
 * 테스트 결과 화면: 머리(제품·대상·상태, 도는 중이면 진행 막대) → 본문(보고서 한 장, ResultReport) → 전체 결과 표(접힘).
 * 본문은 참가자가 승인한 견본(/proto/result)의 ResultReport를 그대로 쓴다. 다음 행동은 여기 두지 않는다(칠성이의 말과 대화의 버튼이 맡는다).
 * 숫자는 GET /api/runs/{id}의 view에서 그대로 읽는다. 결과(view.result)가 없을 때는 부르는 쪽(ShelfCards)이 자리만 그린다.
 */
import { Badge } from "@astryxdesign/core/Badge"
import { Button } from "@astryxdesign/core/Button"
import { Collapsible } from "@astryxdesign/core/Collapsible"
import { Heading } from "@astryxdesign/core/Heading"
import { ProgressBar } from "@astryxdesign/core/ProgressBar"
import { Table, TableBody, TableCell, TableHeader, TableHeaderCell, TableRow } from "@astryxdesign/core/Table"
import { Text } from "@astryxdesign/core/Text"
import type { RunQuote, RunResult } from "../../chat/contract"
import type { ShelfRunView } from "../../chat/contract-shelf"
import { dashCopy as t } from "../../copy/result-dashboard"
import { copy } from "../../copy"
import { resultCopy } from "../../copy/result"
import { shelfCopy } from "../../copy/shelf"
import { ResultReport } from "./ResultReport"
import { RunUsageLine } from "./RunUsageLine"
import "./ResultDashboard.css"

type AskFor = (q: RunQuote) => (() => void) | null | undefined

/** "pos:MK01:밀키스 …" 같은 앞머리를 떼어 화면의 이름으로. */
function clean(name: string) {
  return name.replace(/^pos:[^:]+:/, "")
}

function pct(k: number, n: number) {
  if (!n) return "0"
  const v = (100 * k) / n
  return v > 0 && v < 10 ? v.toFixed(1) : String(Math.round(v))
}

// ---------- 가상 소비자의 말(전체 결과 표 안) ----------

function QuoteCard({ q, onAsk }: { q: RunQuote; onAsk?: (() => void) | null }) {
  return (
    <figure className="rd-quote">
      <blockquote>
        <Text>{`“${q.said}”`}</Text>
      </blockquote>
      <figcaption className="rd-quote-who">
        <span className="rd-quote-meta">
          <Text weight="medium">{q.who}</Text>
          {q.occasion && <Text>{q.occasion}</Text>}
          <Text>{q.chose === t.noPurchase ? t.choseNothing : t.chose(clean(q.chose))}</Text>
        </span>
        {onAsk !== undefined && (
          <Button label={copy.workbench.result.ask} variant="secondary" size="sm" onClick={onAsk ?? undefined} isDisabled={!onAsk} />
        )}
      </figcaption>
    </figure>
  )
}

// ---------- 전체 결과 표 ----------

function AllTables({ view, res, askFor, shownQuotes }: {
  view: ShelfRunView
  res: RunResult
  askFor: AskFor
  shownQuotes: Set<string>
}) {
  const fromRows = [
    ...res.from.own.map((x) => ({ kind: t.segOwn, ...x })),
    ...res.from.rival.map((x) => ({ kind: t.segRival, ...x })),
    ...(res.from.none ? [{ kind: t.segNone, name: "", count: res.from.none }] : []),
    ...((res.from.pending ?? 0) > 0 ? [{ kind: t.segPending, name: "", count: res.from.pending ?? 0 }] : []),
  ]
  const restQuotes = [...res.quotes.picked, ...res.quotes.passed].filter((q) => !shownQuotes.has(q.visitor))
  const who = view.who.label.replace(/\s*손님$/, "")
  return (
    <div className="rd-tables">
      <Table aria-label={t.tNeighbors} density="compact" className="w-full text-left">
        <TableHeader>
          <TableRow>
            <TableHeaderCell scope="col">{t.tNeighbors}</TableHeaderCell>
            <TableHeaderCell scope="col">{t.tPeople}</TableHeaderCell>
          </TableRow>
        </TableHeader>
        <TableBody>
          {res.neighbors.map((x) => (
            <TableRow key={x.name}>
              <TableCell><Text weight={x.self ? "semibold" : "normal"}>{clean(x.name)}</Text></TableCell>
              <TableCell><Text hasTabularNumbers>{t.people(x.picked)}</Text></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {fromRows.length > 0 && (
        <div className="rd-section">
        <Heading level={5}>{t.tFrom}</Heading>
        <Table aria-label={t.tFrom} density="compact" className="w-full text-left">
          <TableHeader>
            <TableRow>
              <TableHeaderCell scope="col">{t.tKind}</TableHeaderCell>
              <TableHeaderCell scope="col">{t.tProduct}</TableHeaderCell>
              <TableHeaderCell scope="col">{t.tPeople}</TableHeaderCell>
            </TableRow>
          </TableHeader>
          <TableBody>
            {fromRows.map((x, i) => (
              <TableRow key={`${x.kind}-${x.name}-${i}`}>
                <TableCell><Text>{x.kind}</Text></TableCell>
                <TableCell><Text>{clean(x.name)}</Text></TableCell>
                <TableCell><Text hasTabularNumbers>{t.people(x.count)}</Text></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        </div>
      )}
      {res.barriers.length > 0 && (
        <Table aria-label={t.tBarriers} density="compact" className="w-full text-left">
          <TableHeader>
            <TableRow>
              <TableHeaderCell scope="col">{t.tBarriers}</TableHeaderCell>
              <TableHeaderCell scope="col">{t.tPeople}</TableHeaderCell>
            </TableRow>
          </TableHeader>
          <TableBody>
            {res.barriers.map((b) => (
              <TableRow key={b.label}>
                <TableCell><Text>{b.label}</Text></TableCell>
                <TableCell><Text hasTabularNumbers>{t.people(b.count)}</Text></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {(res.by_occasion ?? []).length > 0 && (
        <Table aria-label={t.tOccasions} density="compact" className="w-full text-left">
          <TableHeader>
            <TableRow>
              <TableHeaderCell scope="col">{t.tOccasion}</TableHeaderCell>
              <TableHeaderCell scope="col">{t.tAsked}</TableHeaderCell>
              <TableHeaderCell scope="col">{t.tPicked}</TableHeaderCell>
              <TableHeaderCell scope="col">{t.tRate}</TableHeaderCell>
            </TableRow>
          </TableHeader>
          <TableBody>
            {res.by_occasion.map((o) => (
              <TableRow key={o.occasion}>
                <TableCell><Text>{o.occasion}</Text></TableCell>
                <TableCell><Text hasTabularNumbers>{t.people(o.n)}</Text></TableCell>
                <TableCell><Text hasTabularNumbers>{t.people(o.picked)}</Text></TableCell>
                <TableCell><Text hasTabularNumbers>{`${pct(o.picked, o.n)}%`}</Text></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {restQuotes.length > 0 && (
        <div className="rd-section">
          <Heading level={5}>{t.tQuotes}</Heading>
          <div className="rd-quotes-rest">
            {restQuotes.map((q) => <QuoteCard key={q.visitor} q={q} onAsk={askFor(q)} />)}
          </div>
        </div>
      )}
      <div className="rd-section">
        <Heading level={5}>{t.tRecords}</Heading>
        <Text hasTabularNumbers>{resultCopy.asked(who, res.n)}</Text>
        {view.skipped > 0 && <Text>{resultCopy.skipped(view.skipped)}</Text>}
        {view.placement && (
          <Text>{view.placement.store_rate == null ? shelfCopy.placement.storage(view.placement.storage)
            : shelfCopy.placement.rate(view.placement.storage, view.placement.store_rate)}</Text>
        )}
        {view.target_basis && <Text>{`${shelfCopy.targetBasis} ${view.target_basis}`}</Text>}
        <RunUsageLine view={view} />
      </div>
    </div>
  )
}

// ---------- 화면 ----------

export function ResultDashboard({ view, askFor }: { view: ShelfRunView; askFor: AskFor }) {
  const res = view.result!
  const brief = view.brief
  const running = view.status === "running"
  const group = brief?.group ?? view.who.label.replace(/\s*손님$/, "")
  const eta = running ? brief?.eta_s : null
  const status = running ? t.running : view.status === "done" ? t.done : view.status === "stopped" ? t.stopped : t.failed
  // 위(ResultReport)에 보이는 말: 고른 가상 소비자 둘, 고르지 않은 가상 소비자 둘. 나머지는 전체 결과 표에
  const shown = new Set([...(res.quotes?.picked.slice(0, 2) ?? []), ...(res.quotes?.passed.slice(0, 2) ?? [])].map((q) => q.visitor))
  return (
    <div className="rd" data-result-dashboard>
      <header className="rd-head">
        <div className="rd-title">
          <Heading level={3}>{view.concept.name}</Heading>
          <Text>{t.spec(view.concept.pack, view.concept.price)}</Text>
          <span className="rd-badge">
            <Badge label={status} variant={running ? "neutral" : view.status === "failed" ? "warning" : "neutral"} />
          </span>
        </div>
        <Text>{group ? t.who(group, view.total) : t.whoAll(view.total)}</Text>
        {running && (
          <div className="rd-progress">
            <Text weight="medium" hasTabularNumbers>{t.answered(view.asked, view.total)}</Text>
            <span className="rd-progress-bar">
              <ProgressBar label={t.progress} isLabelHidden value={view.asked} max={Math.max(1, view.total)} variant="neutral" />
            </span>
            {eta != null && <Text hasTabularNumbers>{t.eta(eta)}</Text>}
          </div>
        )}
      </header>

      <ResultReport view={view} askFor={askFor} />

      <div className="rd-all">
        <Collapsible trigger={<Text weight="medium">{t.all}</Text>} defaultIsOpen={false}>
          <AllTables view={view} res={res} askFor={askFor} shownQuotes={shown} />
        </Collapsible>
      </div>
    </div>
  )
}
