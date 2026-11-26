/**
 * 컨셉 보드 분석의 차트 둘(Recharts). 형식은 21st.dev의 레퍼런스를 따른다.
 * - 검색 추이: "Metric Trend Chart"(이번 기간은 면, 지난 기간은 점선, 강조 구간은 띠)
 * - 가격: 가격 분포 막대("Range Slider"의 히스토그램)에 우리 가격의 세로줄
 * 색과 글씨 크기는 테마의 값(var(--…))과 analysis-report.css의 클래스로만 정한다.
 */
import {
  Area, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Line, ReferenceArea, ReferenceDot, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts"
import { Text } from "@astryxdesign/core/Text"
import type { DiagnosisTrend, DiagnosisWtp } from "../../chat/contract-diagnose"
import { analysisReportCopy as t } from "../../copy/analysis-report"

const ink = "var(--color-text-primary)"
const soft = "var(--color-text-secondary)"
const line = "var(--color-border)"
const faint = "var(--color-border-emphasized)"
const accent = "var(--color-accent)"
const surface = "var(--color-background-surface)"

function Key({ kind, children }: { kind: "area" | "dash" | "bar" | "bar-soft" | "accent"; children: React.ReactNode }) {
  return <span className="cba-key" data-kind={kind}><i aria-hidden="true" /><Text>{children}</Text></span>
}

type TipProps = { active?: boolean; label?: string | number; payload?: { name?: string; value?: number | string; dataKey?: string | number }[] }

function Tip({ active, label, payload, title, name }: TipProps & { title: (label: string | number) => string; name: (key: string) => string }) {
  if (!active || !payload?.length || label == null) return null
  return (
    <div className="cba-tip">
      <Text weight="semibold">{title(label)}</Text>
      {payload.filter((p) => p.value != null).map((p) => (
        <div key={String(p.dataKey)} className="cba-tip__row"><Text>{name(String(p.dataKey))}</Text><Text hasTabularNumbers weight="medium">{p.value}</Text></div>
      ))}
    </div>
  )
}

// ---------- 검색 추이: 최근 1년(면)과 그 전 1년(점선)을 같은 달끼리 겹친다 ----------

const SUMMER = [6, 7, 8]

export function YearOverYearChart({ trend, label }: { trend: DiagnosisTrend; label: string }) {
  const months = (trend.series ?? []).filter((m) => typeof m.search_index === "number")
  if (months.length < 2) return null
  const recent = months.slice(-12)
  const earlier = months.length >= 24 ? months.slice(-24, -12) : []
  const monthOf = (m: { month: string }) => Number(m.month.slice(5, 7))
  const rows = recent.map((m, i) => ({
    month: t.monthShort(monthOf(m)),
    now: m.search_index as number,
    before: earlier[i] && monthOf(earlier[i]) === monthOf(m) ? (earlier[i].search_index as number) : null,
  }))
  const top = (key: "now" | "before") => rows.reduce<(typeof rows)[number] | null>(
    (best, r) => (r[key] != null && (best == null || (r[key] as number) > (best[key] as number)) ? r : best), null)
  const nowPeak = top("now")
  const beforePeak = earlier.length ? top("before") : null
  const same = nowPeak && beforePeak && nowPeak.month === beforePeak.month && (beforePeak.before as number) > 0
  const change = same ? Math.round((nowPeak.now / (beforePeak.before as number) - 1) * 100) : null
  const high = Math.max(...rows.map((r) => Math.max(r.now, r.before ?? 0)), 1)
  const summer = trend.highlight === t.summer ? rows.filter((r) => SUMMER.some((n) => t.monthShort(n) === r.month)) : []
  const span = (list: { month: string }[]) => t.period(list[0].month, list[list.length - 1].month)
  return (
    <div className="cba-chart">
      <div className="cba-keys">
        <Key kind="area">{span(recent)}</Key>
        {earlier.length > 0 && <Key kind="dash">{span(earlier)}</Key>}
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={rows} margin={{ top: 28, right: 24, bottom: 0, left: 0 }} accessibilityLayer>
          <defs>
            <linearGradient id="cba-now" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={ink} stopOpacity={0.16} />
              <stop offset="100%" stopColor={ink} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          {summer.length > 1 && (
            <ReferenceArea x1={summer[0].month} x2={summer[summer.length - 1].month} fill={faint} fillOpacity={0.28} ifOverflow="visible"
              label={{ value: t.summer, position: "insideTopLeft", fill: soft, className: "cba-chart__note" }} />
          )}
          <CartesianGrid vertical={false} stroke={line} />
          <XAxis dataKey="month" tickLine={false} axisLine={{ stroke: faint }} tickMargin={10} />
          <YAxis width={40} tickLine={false} axisLine={false} domain={[0, Math.ceil(high / 50) * 50]} tickCount={3} />
          <Tooltip cursor={{ stroke: faint }} content={<Tip title={(m) => String(m)} name={(k) => (k === "now" ? span(recent) : span(earlier))} />} />
          {earlier.length > 0 && <Line dataKey="before" name={label} type="monotone" stroke={soft} strokeWidth={2} strokeDasharray="5 5" dot={false} isAnimationActive={false} connectNulls />}
          <Area dataKey="now" name={label} type="monotone" stroke={ink} strokeWidth={2.5} fill="url(#cba-now)" dot={false} isAnimationActive={false} />
          {same && change != null && (
            <ReferenceLine segment={[{ x: nowPeak.month, y: beforePeak.before as number }, { x: nowPeak.month, y: nowPeak.now }]} stroke={accent} strokeWidth={2}
              label={{ value: t.change(change), position: "right", offset: 12, fill: accent, className: "cba-chart__change" }} />
          )}
          {beforePeak && (
            <ReferenceDot x={beforePeak.month} y={beforePeak.before as number} r={5} fill={soft} stroke={surface} strokeWidth={2}
              label={{ value: Math.round(beforePeak.before as number), position: "top", offset: 10, fill: ink, className: "cba-chart__value" }} />
          )}
          {nowPeak && (
            <ReferenceDot x={nowPeak.month} y={nowPeak.now} r={6} fill={accent} stroke={surface} strokeWidth={2}
              label={{ value: Math.round(nowPeak.now), position: "bottom", offset: 10, fill: accent, className: "cba-chart__value cba-chart__value--accent" }} />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

// ---------- 가격: 소비자가 내겠다는 값의 분포(100원 칸) + 우리 가격의 세로줄 ----------

export function WtpHistogram({ wtp, current }: { wtp: DiagnosisWtp; current: number }) {
  const steps = wtp.accept ?? []
  if (steps.length < 2) return null
  const rows = steps.map(([price, atLeast], i) => ({
    price,
    count: atLeast - (steps[i + 1]?.[1] ?? 0),
    ok: price >= current,
  }))
  const at = (v: number) => steps.find(([p]) => p >= v)?.[1] ?? 0
  const yes = at(current)
  const ours = rows.reduce((best, r) => (r.price <= current ? r.price : best), rows[0].price)
  return (
    <div className="cba-chart">
      <div className="cba-keys">
        <Key kind="bar">{t.wouldPay(current, yes, wtp.n)}</Key>
        <Key kind="bar-soft">{t.wouldNot(wtp.n - yes)}</Key>
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={rows} margin={{ top: 30, right: 24, bottom: 0, left: 0 }} barCategoryGap="12%" accessibilityLayer>
          <CartesianGrid vertical={false} stroke={line} />
          <XAxis dataKey="price" tickLine={false} axisLine={{ stroke: faint }} tickMargin={10} interval={0}
            tickFormatter={(v: number) => (v % 500 === 0 ? t.won(v) : "")} />
          <YAxis width={40} tickLine={false} axisLine={false} allowDecimals={false} tickCount={4} tickFormatter={(v: number) => t.people(v)} />
          <Tooltip cursor={{ fill: line, fillOpacity: 0.5 }} content={<Tip title={(v) => t.binTitle(Number(v))} name={() => t.binName} />} />
          <Bar dataKey="count" radius={[3, 3, 0, 0]} isAnimationActive={false}>
            {rows.map((r) => <Cell key={r.price} fill={r.ok ? ink : faint} />)}
          </Bar>
          <ReferenceLine x={ours} stroke={accent} strokeWidth={2} ifOverflow="visible"
            label={{ value: t.oursAt(current), position: "top", offset: 12, fill: accent, className: "cba-chart__value cba-chart__value--accent" }} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
