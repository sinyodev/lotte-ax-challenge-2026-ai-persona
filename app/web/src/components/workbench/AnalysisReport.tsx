/**
 * 컨셉 보드 분석의 새 화면: 보고서 한 장.
 * 결론 한 문장 → 숫자 줄(살펴볼 점은 표시로) → 살펴볼 점마다 큰 그림 하나 → 비슷한 과거 사례의 표.
 * 다음 행동(어떤 가격으로 테스트할지)은 여기 두지 않는다. 칠성이의 말과 대화의 버튼이 맡는다.
 * 숫자와 문장은 모두 payload에서 코드가 계산한다(analysisModel).
 */
import { CheckCircleIcon, ExclamationCircleIcon } from "@heroicons/react/20/solid"
import { Text } from "@astryxdesign/core/Text"
import type { DiagnosisPayload, DiagnosisPrice } from "../../chat/contract-diagnose"
import { analysisReportCopy as t } from "../../copy/analysis-report"
import { diagnoseCopy as c } from "../../copy/diagnose"
import {
  historyRows, insight, isEnded, priceFacts, priceGap, priceTitle, sectionOf, shelfShare, trendKeyword, trendPair, type Status,
} from "./analysisModel"
import { yearPeaks } from "./chartParts"
import { WtpHistogram, YearOverYearChart } from "./ReportCharts"
import { Tag } from "./OriginTag"
import "./analysis-report.css"

// ---------- 숫자 줄 ----------

function Mark({ status }: { status: Status | null }) {
  if (status === "flag") return <ExclamationCircleIcon className="cba-mark" data-flag aria-label={t.flag} />
  if (status === "ok") return <CheckCircleIcon className="cba-mark" aria-label={t.ok} />
  return null
}

function Figure({ name, value, caption, status }: { name: string; value: string | null; caption: string; status: Status | null }) {
  return (
    <div className="cba-figure" data-flag={status === "flag" || undefined}>
      <div className="cba-figure__name"><Mark status={status} /><Text weight="medium">{name}</Text></div>
      <div className="cba-figure__value">{value ?? c.noData}</div>
      <Text as="p" display="block">{caption}</Text>
    </div>
  )
}

function Figures({ payload }: { payload: DiagnosisPayload }) {
  const trend = sectionOf(payload, "trend")
  const pair = trend && trend.status !== "missing" ? trendPair(trend) : null
  const price = sectionOf(payload, "price")
  const gap = price && price.status !== "missing" ? priceGap(priceFacts(price, payload)) : null
  const history = sectionOf(payload, "history")
  const rows = historyRows(history)
  const ended = rows.filter(isEnded).length
  const dist = sectionOf(payload, "distribution")
  const shelf = dist?.rate != null ? shelfShare(dist) : null
  return (
    <div className="cba-figures">
      <Figure name={c.trend} status={trend?.status ?? null} value={pair ? c.tile.pct(pair.change) : null}
        caption={c.tile.trendVs(pair?.season ?? null)} />
      <Figure name={c.price} status={price?.status ?? null} value={gap ? c.tile.gap(gap.gap) : null}
        caption={gap?.caption ?? c.tile.priceVs} />
      <Figure name={c.history} status={history?.status ?? null} value={rows.length ? c.tile.cases(ended || rows.length) : null}
        caption={ended ? t.historyEnded : c.tile.similar} />
      <Figure name={c.distribution} status={dist?.status ?? null} value={shelf ? c.tile.share(shelf.share) : dist?.storage ?? null}
        caption={dist?.storage === "상온" && !shelf ? t.shelfRoom : c.tile.shelf} />
    </div>
  )
}

// ---------- 가격 옆의 표: 우리 가격, 소비자가 내겠다는 값, 같은 용량의 다른 제품 ----------

/** 이름 끝의 용기·용량("페트 500ml")은 묶음의 이름이 이미 말하므로 뗀다. */
const shortName = (name: string) => name.replace(/\s*(?:페트|PET|캔|병|pet)?\s*\d+\s*m[lL]\s*$/, "").trim() || name

function PriceList({ price, payload }: { price: DiagnosisPrice; payload: DiagnosisPayload }) {
  const f = priceFacts(price, payload)
  const points = [...(f.points ?? [])].sort((a, b) => a.price - b.price)
  return (
    <table className="cba-prices">
      <tbody>
        {f.current != null && <tr data-ours><th scope="row">{t.ours}</th><td>{t.won(f.current)}</td></tr>}
        {f.wtp && <tr><th scope="row">{t.wtpMedian}</th><td>{t.won(f.wtp.median)}</td></tr>}
        {f.wtp && <tr><th scope="row">{t.wtpHalf}</th><td>{t.range(f.wtp.p25, f.wtp.p75)}</td></tr>}
        {points.length > 0 && <tr data-group><th scope="rowgroup" colSpan={2}>{t.sameGroup}</th></tr>}
        {points.map((q) => <tr key={q.name}><th scope="row">{shortName(q.name)}</th><td>{t.won(q.price)}</td></tr>)}
        {!points.length && f.same && <tr><th scope="row">{t.sameRange(f.same.count)}</th><td>{t.range(f.same.low, f.same.high)}</td></tr>}
      </tbody>
    </table>
  )
}

// ---------- 화면 ----------

function Finding({ title, source, children }: { title: string; source?: string | null; children: React.ReactNode }) {
  return (
    <section className="cba-finding">
      <div className="cba-finding__head">
        <h3 className="cba-finding__title">{title}</h3>
        {source && <Tag>{source}</Tag>}
      </div>
      {children}
    </section>
  )
}

export function AnalysisReport({ payload }: { payload: DiagnosisPayload }) {
  const trend = sectionOf(payload, "trend")
  const price = sectionOf(payload, "price")
  const history = sectionOf(payload, "history")
  const rows = historyRows(history)
  const peaks = trend?.series?.length ? yearPeaks(trend.series, "search_index").slice(-2) : []
  const peakMonth = peaks.length === 2 ? trend!.series![peaks[0].i].month : null
  return (
    <article className="cba">
      <h2 className="cba-headline">{insight(payload)}</h2>
      <Figures payload={payload} />
      {trend && trend.status !== "missing" && peakMonth && (
        <Finding title={c.chart.searchPeak(trendKeyword(trend), peakMonth)} source={trend.source}>
          <YearOverYearChart trend={trend} label={trendKeyword(trend)} />
        </Finding>
      )}
      {price && price.status !== "missing" && price.current != null && (
        <Finding title={priceTitle(priceFacts(price, payload))} source={price.source}>
          {price.wtp?.accept ? (
            <div className="cba-split">
              <WtpHistogram wtp={price.wtp} current={price.current} />
              <PriceList price={price} payload={payload} />
            </div>
          ) : <PriceList price={price} payload={payload} />}
        </Finding>
      )}
      {rows.length > 0 && (
        <Finding title={t.historyTitle(rows.length)} source={history?.source}>
          <table className="cba-table">
            <thead>
              <tr>{[c.table.product, c.table.year, c.table.result, c.table.reason].map((h) => <th key={h} scope="col">{h}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.name}-${r.year}`}>
                  <th scope="row">{r.name}</th>
                  <td>{r.year ?? ""}</td>
                  <td>{r.status ?? ""}</td>
                  <td>{r.reasons == null ? c.reasonNone : r.reasons.join(", ") || c.reasonOther}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Finding>
      )}
    </article>
  )
}
