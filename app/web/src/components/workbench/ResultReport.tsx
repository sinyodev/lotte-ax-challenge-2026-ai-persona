/**
 * 테스트 결과의 새 화면: 보고서 한 장(컨셉 보드 분석과 같은 문법).
 * 결론 한 문장 → 숫자 줄 → 구역 넷(매대 순위, 수요 유입 경로, 비구매 요인, 음용 상황별 선택률) → 가상 소비자의 말.
 * 구역마다 이름 → 알게 된 것 한 문장 → 근거의 표(막대 표)의 차례로 읽힌다. 옆 구역과 줄이 맞는다.
 * 다음 행동은 여기 두지 않는다. 칠성이의 말과 대화의 버튼이 맡는다.
 * 숫자는 GET /api/runs/{id}의 view에서 그대로 읽는다.
 */
import type { ReactNode } from "react"
import { ExclamationCircleIcon } from "@heroicons/react/20/solid"
import { Button } from "@astryxdesign/core/Button"
import { Text } from "@astryxdesign/core/Text"
import type { RunQuote } from "../../chat/contract"
import type { ShelfRunView } from "../../chat/contract-shelf"
import { dashCopy as d } from "../../copy/result-dashboard"
import { resultReportCopy as t } from "../../copy/result-report"
import { copy } from "../../copy"
import { BarTable, PartitionBar, type BarRow, type Tone } from "./ResultCharts"
import "./analysis-report.css"
import "./result-report.css"

/** 이만큼 답하지 않은 음용 상황은 선택률을 견주지 않는다(그리지 않는다). 서버 result_brief.OCCASION_MIN과 같다. */
const OCCASION_MIN = 10

const clean = (name: string) => name.replace(/^pos:[^:]+:/, "")
const pct = (k: number, n: number) => (n ? Math.round((100 * k) / n) : 0)
const sum = (xs: { count: number }[]) => xs.reduce((a, x) => a + x.count, 0)

function Figure({ name, value, caption, flag }: { name: string; value: string; caption: string; flag?: boolean }) {
  return (
    <div className="cba-figure">
      <div className="cba-figure__name">
        {flag && <ExclamationCircleIcon className="cba-mark" data-flag aria-hidden="true" />}
        <Text weight="medium">{name}</Text>
      </div>
      <div className="cba-figure__value">{value}</div>
      <Text as="p" display="block">{caption}</Text>
    </div>
  )
}

/** 구역 하나: 이름(오른쪽에 범례) → 알게 된 것 한 문장 → 근거. 세 줄의 높이는 옆 구역과 맞춘다(subgrid). */
function Section({ name, title, keys, children }: { name: string; title: string; keys?: ReactNode; children: ReactNode }) {
  return (
    <section className="rr-cell">
      <div className="rr-cell__head">
        <span className="rr-eyebrow">{name}</span>
        {keys && <div className="cba-keys">{keys}</div>}
      </div>
      <h3 className="cba-finding__title">{title}</h3>
      <div className="rr-cell__body">{children}</div>
    </section>
  )
}

function Key({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className="cba-key rr-key" data-tone={tone}><i aria-hidden="true" /><Text>{children}</Text></span>
}

function Quote({ q, onAsk }: { q: RunQuote; onAsk?: (() => void) | null }) {
  return (
    <figure className="rr-quote">
      <blockquote><Text as="p" display="block">{`“${q.said}”`}</Text></blockquote>
      <figcaption>
        <div className="rr-quote__who">
          <Text weight="medium">{q.who}</Text>
          <Text>{q.chose === d.noPurchase ? d.choseNothing : d.chose(clean(q.chose))}</Text>
        </div>
        {onAsk && <Button label={copy.workbench.result.ask} variant="secondary" size="sm" onClick={onAsk} />}
      </figcaption>
    </figure>
  )
}

export function ResultReport({ view, askFor }: { view: ShelfRunView; askFor?: (q: RunQuote) => (() => void) | null | undefined }) {
  const res = view.result!
  const brief = view.brief
  const running = view.status === "running"
  const group = brief?.group ?? view.who.label.replace(/\s*손님$/, "")
  const lo = Math.floor((res.low * res.n) / 100)
  const hi = Math.ceil((res.high * res.n) / 100)
  const headline = brief?.headline ?? d.headline(group, res.n, res.picked, res.rank, res.products, running)
  const own = sum(res.from.own)
  const rival = sum(res.from.rival)
  const passed = res.n - res.picked
  const barrier = res.barriers[0]
  const rate = pct(res.picked, res.n)

  // ① 매대 순위
  const top = (brief?.top ?? res.neighbors).map((p) => ({ ...p, name: clean(p.name) }))
  const best = top.find((p) => !p.self)
  const rankTitle = !res.picked ? d.shelfNone
    : best && best.picked > 0 && res.picked > best.picked ? d.shelfTimes(best.name, best.picked, (res.picked / best.picked).toFixed(1))
      : best && best.picked >= res.picked && best.picked > 0 ? d.shelfBehind(best.name, best.picked, res.picked)
        : res.rank ? d.shelfRankOnly(res.products, res.rank) : d.shelfTitle
  const topMax = Math.max(...top.map((p) => p.picked), 1)
  const rankRows: BarRow[] = top.map((p) => ({
    name: p.name, share: p.picked / topMax, cells: [t.people(p.picked)], tone: p.self ? "accent" : p.ours ? "ink" : "faint", strong: p.self,
  }))

  // ② 수요 유입 경로
  const sources = [...res.from.own.map((s) => ({ ...s, tone: "ink" as Tone })), ...res.from.rival.map((s) => ({ ...s, tone: "faint" as Tone }))]
    .sort((a, b) => b.count - a.count).slice(0, 5)
  const sourceMax = Math.max(...sources.map((s) => s.count), 1)
  const sourceRows: BarRow[] = sources.map((s) => ({ name: clean(s.name), share: s.count / sourceMax, cells: [t.people(s.count)], tone: s.tone }))

  // ③ 비구매 요인: 막대의 바탕은 고르지 않은 사람 전체
  const barrierRows: BarRow[] = res.barriers.map((b, i) => ({
    name: b.label, share: passed ? b.count / passed : 0, cells: [t.people(b.count), t.pct(pct(b.count, passed))], tone: i === 0 ? "ink" : "faint", strong: i === 0,
  }))

  // ④ 음용 상황별 선택률: 막대의 바탕은 100%, 세로 점선은 전체 선택률
  const occasions = [...(res.by_occasion ?? [])].filter((o) => o.n >= OCCASION_MIN).sort((a, b) => b.picked / b.n - a.picked / a.n)
  const bestOcc = occasions.find((o) => o.picked > 0)
  const occRows: BarRow[] = occasions.map((o) => ({
    name: o.occasion, share: o.picked / o.n, cells: [t.pct(pct(o.picked, o.n)), t.of(o.n, o.picked)], tone: o === bestOcc ? "ink" : "faint", strong: o === bestOcc,
  }))
  const occTotal: BarRow = { name: t.total, share: rate / 100, cells: [t.pct(rate), t.of(res.n, res.picked)], tone: "accent" }

  const picks = res.quotes?.picked.slice(0, 2) ?? []
  const passes = res.quotes?.passed.slice(0, 2) ?? []
  return (
    <article className="cba rr">
      <h2 className="cba-headline">{`${headline.replace(/[.。]$/, "")}.`}</h2>
      <div className="cba-figures">
        <Figure name={d.tileRate} value={d.rate(String(rate))} caption={t.rateOf(res.n, res.picked, lo, hi)} />
        <Figure name={d.tileRank} value={res.rank ? d.rank(res.rank) : d.noRank} caption={d.rankOf(res.products)} />
        <Figure name={d.tileOwn} value={t.people(own)} caption={t.ownShare(res.picked, pct(own, res.picked))} flag={res.picked > 0 && own * 2 >= res.picked} />
        <Figure name={d.tileBarrier} value={barrier ? t.people(barrier.count) : t.people(0)} caption={barrier?.label ?? ""} flag={!!barrier} />
      </div>

      <div className="rr-grid">
        {rankRows.length > 0 && (
          <Section name={d.shelfTitle} title={rankTitle}
            keys={<><Key tone="accent">{t.keySelf}</Key><Key tone="ink">{t.keyOwn}</Key><Key tone="faint">{t.keyRival}</Key></>}>
            <BarTable label={d.shelfTitle} head={[t.colProduct, t.colPicked]} rows={rankRows} />
          </Section>
        )}
        {res.picked > 0 && own + rival > 0 && (
          <Section name={d.fromTitle} title={own >= rival ? d.fromOwn(res.picked, own) : d.fromRivalMost(res.picked, rival)}>
            <PartitionBar label={d.fromTitle} parts={[
              { name: d.segOwn, value: own, label: t.share(own, pct(own, res.picked)), tone: "ink" },
              { name: d.segRival, value: rival, label: t.share(rival, pct(rival, res.picked)), tone: "faint" },
            ]} />
            <BarTable label={t.fromList} head={[t.fromList, t.colMoved]} rows={sourceRows} dots />
          </Section>
        )}
        {barrier && (
          <Section name={d.barrierTitle} title={d.barrierLine(passed, barrier.count, barrier.label)}>
            <BarTable label={d.barrierTitle} head={[t.colBarrier, t.colAnswered, t.colShare(passed)]} rows={barrierRows} track />
          </Section>
        )}
        {bestOcc && (
          <Section name={d.occasionTitle} title={d.occasionLine(bestOcc.occasion)}
            keys={<span className="cba-key" data-kind="dash"><i aria-hidden="true" /><Text>{t.average(rate)}</Text></span>}>
            <BarTable label={d.occasionTitle} head={[t.colOccasion, t.colRate, t.colPicked]} rows={occRows} foot={occTotal} track mark={rate} />
          </Section>
        )}
      </div>

      {(picks.length > 0 || passes.length > 0) && (
        <section className="rr-voices">
          <span className="rr-eyebrow">{d.quotes}</span>
          <div className="rr-quotes">
            <div><div className="rr-quotes__head">{d.quotesPicked}</div>{picks.map((q) => <Quote key={q.visitor} q={q} onAsk={askFor?.(q)} />)}</div>
            <div><div className="rr-quotes__head">{d.quotesPassed}</div>{passes.map((q) => <Quote key={q.visitor} q={q} onAsk={askFor?.(q)} />)}</div>
          </div>
        </section>
      )}
    </article>
  )
}
