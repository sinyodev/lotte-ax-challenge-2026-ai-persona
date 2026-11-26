import { Collapsible } from "@astryxdesign/core/Collapsible"
import { Text } from "@astryxdesign/core/Text"
import { VStack } from "@astryxdesign/core/VStack"
import type { TrendItem, TrendMonth, TrendVerdict } from "../../chat/contract-trend"
import { researchCopy as c } from "../../copy/trend"
import { SourceTag, Tag } from "./OriginTag"
import "./trend.css"
import { Axis, linePath, useWidth, xOf, yearPeaks } from "./chartParts"

type Field = "search_index" | "sns_mentions" | "sns_organic"
const columns: [Field, string][] = [
  ["search_index", c.search],
  ["sns_mentions", c.mentions],
  ["sns_organic", c.organic],
]

const fmt = (n: number) => Math.round(n).toLocaleString("ko-KR")

/** 검색 지수: 카드 너비 가득, 해마다의 정점에 "달 · 값". */
function SearchChart({ months }: { months: TrendMonth[] }) {
  const [ref, W] = useWidth()
  const values = months.flatMap((m) => (m.search_index == null ? [] : [m.search_index]))
  if (!values.length) return null
  const high = Math.max(1, ...values)
  const top = 22
  const bottom = 104
  const line = linePath(months, "search_index", top, bottom, high, W)
  const area = `${line} L ${xOf(months.length - 1, months.length, W)} ${bottom} L ${xOf(0, months.length, W)} ${bottom} Z`
  return (
    <figure className="trend-figure" ref={ref}>
      <figcaption>
        <Text type="label">{c.search}</Text>
      </figcaption>
      <svg viewBox={`0 0 ${W} 128`} width="100%" role="img" aria-label={c.search} className="trend-svg">
        <path d={area} className="trend-area" />
        <path d={line} className="trend-line trend-line--accent" />
        {yearPeaks(months, "search_index").map(({ i, v }) => {
          const x = xOf(i, months.length, W)
          const y = bottom - (v / high) * (bottom - top)
          return (
            <g key={i} className="trend-peak">
              <circle cx={x} cy={y} r={3} />
              <text x={x} y={y - 8} textAnchor={i < 2 ? "start" : i > months.length - 3 ? "end" : "middle"}>
                {c.peak(months[i].month, fmt(v))}
              </text>
            </g>
          )
        })}
        <Axis months={months} y={bottom} W={W} />
      </svg>
    </figure>
  )
}

/** SNS 언급과 광고·협찬을 뺀 언급을 한 그림에 겹친다. 둘 다 없으면 그리지 않는다. */
function MentionsChart({ months }: { months: TrendMonth[] }) {
  const [ref, W] = useWidth()
  const values = months.flatMap((m) => [m.sns_mentions, m.sns_organic].filter((v): v is number => v != null))
  if (!values.length) return null
  const high = Math.max(1, ...values)
  const top = 8
  const bottom = 72
  return (
    <figure className="trend-figure" ref={ref}>
      <figcaption className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <span className="trend-key trend-key--accent"><Text type="label">{c.mentions}</Text></span>
        <span className="trend-key trend-key--muted"><Text type="label">{c.organic}</Text></span>
        <span className="trend-high"><Text type="label">{c.highest(fmt(high))}</Text></span>
      </figcaption>
      <svg viewBox={`0 0 ${W} 96`} width="100%" role="img" aria-label={`${c.mentions}, ${c.organic}`} className="trend-svg">
        <path d={linePath(months, "sns_mentions", top, bottom, high, W)} className="trend-line trend-line--accent" />
        <path d={linePath(months, "sns_organic", top, bottom, high, W)} className="trend-line trend-line--muted" />
        <Axis months={months} y={bottom} W={W} />
      </svg>
    </figure>
  )
}

function Monthly({ months }: { months: TrendMonth[] }) {
  return (
    <Collapsible defaultIsOpen={false} chevronPosition="start" className="trend-more" trigger={<Text type="label">{c.monthly}</Text>}>
      <div className="overflow-x-auto pt-2">
        <table className="trend-table">
          <thead>
            <tr>
              <th scope="col"><Text type="label">{c.month}</Text></th>
              {columns.map(([, label]) => (
                <th key={label} scope="col"><Text type="label">{label}</Text></th>
              ))}
            </tr>
          </thead>
          <tbody>
            {months.map((m) => (
              <tr key={m.month}>
                <th scope="row"><Text>{m.month}</Text></th>
                {columns.map(([field]) => (
                  <td key={field}><Text>{m[field] == null ? "—" : fmt(m[field])}</Text></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Collapsible>
  )
}

function Related({ related }: { related: TrendVerdict["related"] }) {
  const high = Math.max(0.0001, ...related.map((r) => r.share ?? 0))
  return (
    <Collapsible defaultIsOpen={false} chevronPosition="start" className="trend-more" trigger={<Text type="label">{c.composition}</Text>}>
      <ul className="trend-bars pt-2">
        {related.map((r) => (
          <li key={r.related}>
            <Text maxLines={1}>{r.related}</Text>
            <span className="trend-bar" aria-hidden="true">
              <span style={{ inlineSize: `${((r.share ?? 0) / high) * 100}%` }} />
            </span>
            <Text>{r.share == null ? "—" : r.share.toLocaleString("ko-KR", { style: "percent", maximumFractionDigits: 1 })}</Text>
          </li>
        ))}
      </ul>
    </Collapsible>
  )
}

function Verdict({ item, verdict }: { item: TrendItem; verdict: TrendVerdict }) {
  return (
    <section className="trend-verdict">
      <VStack gap={3}>
        <div className="flex flex-wrap items-center gap-2">
          <Text weight="semibold">{item.title}</Text>
          {verdict.stage.map((s) => <Tag key={s}>{s}</Tag>)}
        </div>
        {verdict.reasons.length > 0 && (
          <ul className="trend-reasons">
            {verdict.reasons.map((r) => <li key={r}><Text>{r}</Text></li>)}
          </ul>
        )}
        {verdict.series.length > 0 && (
          <>
            <SearchChart months={verdict.series} />
            <MentionsChart months={verdict.series} />
          </>
        )}
        {(verdict.series.length > 0 || verdict.related.length > 0) && (
          <div className="flex flex-col">
            {verdict.series.length > 0 && <Monthly months={verdict.series} />}
            {verdict.related.length > 0 && <Related related={verdict.related} />}
          </div>
        )}
        <div className="flex items-center gap-2">
          <SourceTag source={item.publisher || c.internal} isWeb={false} />
          {item.date && <Text type="supporting">{item.date}</Text>}
        </div>
      </VStack>
    </section>
  )
}

function News({ items }: { items: TrendItem[] }) {
  return (
    <section className="trend-news">
      <VStack gap={2}>
        <Text type="label">{c.news}</Text>
        <ul className="flex flex-col">
          {items.map((item, i) => (
            <li key={item.url ?? `${item.keyword}-${i}`} className="trend-news-row">
              <span className="min-w-0 flex-1"><Text maxLines={1}>{item.title}</Text></span>
              <SourceTag
                source={item.publisher || c.internal}
                isWeb={item.source === "web"}
                url={item.url && /^https?:\/\//i.test(item.url) ? item.url : undefined}
              />
              {item.date && <span className="shrink-0 tabular-nums"><Text type="supporting">{item.date}</Text></span>}
            </li>
          ))}
        </ul>
      </VStack>
    </section>
  )
}

export function TrendCard({ items }: { items: TrendItem[] }) {
  if (!items.length) return <Text color="secondary">{c.emptyTrend}</Text>
  const judged = items.filter((it) => it.verdict)
  const news = items.filter((it) => !it.verdict)
  return (
    <VStack gap={5}>
      {judged.map((item, i) => <Verdict key={item.url ?? `${item.keyword}-${i}`} item={item} verdict={item.verdict!} />)}
      {news.length > 0 && <News items={news} />}
    </VStack>
  )
}
