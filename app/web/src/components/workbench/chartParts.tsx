/**
 * 달별 선 그래프의 조각. 트렌드 조사 카드(TrendCard)와 컨셉 보드 분석(AnalysisCharts)이 같이 쓴다.
 * 모양은 trend.css에 있다.
 */
import { useLayoutEffect, useRef, useState } from "react"
import "./trend.css"

/** 달 하나. 트렌드 조사의 TrendMonth와 분석 payload의 series가 모두 이 모양을 품는다. */
export type MonthPoint = { month: string } & Partial<Record<string, number | null | string>>

/** 그림의 좌표. 너비는 viewBox 기준이고 실제로는 카드 너비에 맞춰 늘어난다. */
export const PAD_X = 6

/** 그림이 놓인 자리의 실제 너비(px). 글자와 점이 늘어나지 않게 viewBox를 이 너비로 맞춘다. */
export function useWidth<T extends HTMLElement = HTMLDivElement>(initial = 600) {
  const [width, setWidth] = useState(initial)
  const ref = useRef<T>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(240, Math.round(e.contentRect.width))))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, width] as const
}

export function xOf(index: number, count: number, W: number, pad = PAD_X) {
  return pad + (index / Math.max(1, count - 1)) * (W - pad * 2)
}

function valueOf(m: MonthPoint, field: string) {
  const v = m[field]
  return typeof v === "number" ? v : null
}

export function linePath(months: MonthPoint[], field: string, top: number, bottom: number, high: number, W: number, pad = PAD_X) {
  let fresh = true
  const parts: string[] = []
  months.forEach((m, i) => {
    const v = valueOf(m, field)
    if (v == null) {
      fresh = true
      return
    }
    parts.push(`${fresh ? "M" : "L"} ${xOf(i, months.length, W, pad).toFixed(1)} ${(bottom - (Math.min(high, Math.max(0, v)) / high) * (bottom - top)).toFixed(1)}`)
    fresh = false
  })
  return parts.join(" ")
}

/** 달의 축: 처음 달, 해가 바뀌는 달(1월), 끝 달만 글로. */
export function axisTicks(months: MonthPoint[]) {
  const last = months.length - 1
  return months.flatMap((m, i) => {
    if (i === 0 || i === last) return [{ i, label: m.month }]
    if (m.month.endsWith("-01") && i > 1 && i < last - 1) return [{ i, label: m.month }]
    return []
  })
}

/** 해마다의 정점(그 해의 가장 큰 값). 자료가 여섯 달이 안 되는 해는 정점이라 할 수 없어 뺀다. */
export function yearPeaks(months: MonthPoint[], field: string) {
  const best = new Map<string, { i: number; v: number; n: number }>()
  months.forEach((m, i) => {
    const v = valueOf(m, field)
    if (v == null) return
    const y = m.month.slice(0, 4)
    const cur = best.get(y)
    if (!cur) best.set(y, { i, v, n: 1 })
    else best.set(y, v > cur.v ? { i, v, n: cur.n + 1 } : { ...cur, n: cur.n + 1 })
  })
  return [...best.values()].filter((p) => p.v > 0 && p.n >= 6)
}

export function Axis({ months, y, W, pad = PAD_X }: { months: MonthPoint[]; y: number; W: number; pad?: number }) {
  return (
    <g className="trend-axis">
      <line x1={pad} x2={W - pad} y1={y} y2={y} />
      {axisTicks(months).map(({ i, label }) => {
        const x = xOf(i, months.length, W, pad)
        const anchor = i === 0 ? "start" : i === months.length - 1 ? "end" : "middle"
        return (
          <g key={label}>
            <line x1={x} x2={x} y1={y} y2={y + 4} />
            <text x={x} y={y + 16} textAnchor={anchor}>{label}</text>
          </g>
        )
      })}
    </g>
  )
}
