/**
 * 컨셉 보드 분석의 숫자. 화면이 그리는 숫자와 핵심 인사이트 한 문장은 모두 여기서 payload로 계산한다(모델이 짓지 않는다).
 * 옛 payload(달별 값, 가격 목록, 표의 줄이 없음)도 받는다.
 */
import type {
  DiagnosisHistoryRow, DiagnosisPayload, DiagnosisPeak, DiagnosisPrice, DiagnosisSection, DiagnosisTrend,
} from "../../chat/contract-diagnose"
import { diagnoseCopy as c } from "../../copy/diagnose"
import { yearPeaks } from "./chartParts"

export type Status = DiagnosisSection["status"]
export type HistorySection = Extract<DiagnosisSection, { id: "history" | "distribution" }>

type SectionOf<T> = T extends "trend" ? DiagnosisTrend : T extends "price" ? DiagnosisPrice : HistorySection

export function sectionOf<T extends DiagnosisSection["id"]>(payload: DiagnosisPayload, id: T) {
  return payload.sections.find((s) => s.id === id) as SectionOf<T> | undefined
}

/** 옛 요약 문장(저장된 대화)의 판정 이름과 조사 용어를 쉬운 말로 바꾼다. */
export function plain(text: string) {
  return c.plain.reduce((out, [pattern, to]) => out.replace(pattern, to), text).trim()
}

// ---------- 트렌드 ----------

export function trendKeyword(trend: DiagnosisTrend) {
  return trend.keyword || trend.summary.match(/^(.+?)(?:의 (?:여름\()?6~8월| 검색)/)?.[1] || ""
}

export type TrendPair = { before: number; now: number; change: number; season: string | null }

/** 작년과 올해의 정점. 강조 계절(여름)이 있으면 그 계절끼리, 없으면 달별 값에서 해마다의 정점끼리. */
export function trendPair(trend: DiagnosisTrend): TrendPair | null {
  const seasonal = (trend.peaks || []).filter((p) => p.season === trend.highlight)
  const now = seasonal[seasonal.length - 1]
  const before = now && seasonal.find((p) => p.year === now.year - 1)
  if (now && before && before.peak > 0) return pairOf(before.peak, now.peak, now.season)
  const peaks = trend.series?.length ? yearPeaks(trend.series, "search_index") : []
  if (peaks.length >= 2) {
    const [a, b] = peaks.slice(-2)
    if (a.v > 0) return pairOf(a.v, b.v, null)
  }
  return null
}

function pairOf(before: number, now: number, season: string | null): TrendPair {
  return { before, now, change: Math.round((now / before - 1) * 100), season }
}

/** 옛 payload의 막대: 강조 계절의 해별 정점(강조 계절이 없으면 해마다 가장 큰 계절). */
export function yearBars(trend: DiagnosisTrend): DiagnosisPeak[] {
  const peaks = trend.peaks || []
  if (trend.highlight) return peaks.filter((p) => p.season === trend.highlight)
  const best = new Map<number, DiagnosisPeak>()
  for (const p of peaks) if (!best.has(p.year) || best.get(p.year)!.peak < p.peak) best.set(p.year, p)
  return [...best.values()]
}

// ---------- 가격 ----------

export type PriceFacts = {
  current: number | null
  fix: number | null
  wtp: DiagnosisPrice["wtp"]
  same: DiagnosisPrice["same"]
  rivals: DiagnosisPrice["rivals"]
  points: { name: string; price: number }[] | null
}

export function priceFacts(price: DiagnosisPrice | undefined, payload: DiagnosisPayload): PriceFacts {
  const fix = payload.fixes.find((f) => typeof f.values.price === "number")?.values.price ?? null
  return {
    current: price?.current ?? null,
    fix,
    wtp: price?.wtp ?? null,
    same: price?.same ?? null,
    rivals: price?.rivals ?? null,
    points: price?.points?.length ? price.points : null,
  }
}

/** 가격 타일: 소비자가 내겠다는 값의 가운데와의 차이. 조사가 없으면 같은 용량 제품의 최저가와의 차이. */
export function priceGap(f: PriceFacts): { gap: number; caption: string } | null {
  if (f.current == null) return null
  if (f.wtp) return { gap: f.current - f.wtp.median, caption: c.tile.priceVs }
  if (f.same) return { gap: f.current - f.same.low, caption: c.tile.priceVsLow }
  return null
}

export function priceTitle(f: PriceFacts) {
  if (f.current == null) return c.chart.priceOnly
  if (f.wtp) {
    const gap = f.current - f.wtp.median
    return gap > 0 ? c.chart.priceOver(gap) : gap < 0 ? c.chart.priceUnder(-gap) : c.chart.priceSame
  }
  const span = f.same ?? f.rivals
  if (!span) return c.chart.priceOnly
  return f.current > span.high ? c.chart.priceAboveAll : f.current < span.low ? c.chart.priceBelowAll : c.chart.priceAmong
}

// ---------- 비슷한 과거 사례 ----------

// 받침이 있으면 true. 한글이 아닌 끝 글자는 읽는 소리로 본다(500mL → 엘, PET → 티).
function batchim(word: string) {
  const last = word.trim().slice(-1)
  const code = last.charCodeAt(0) - 0xac00
  if (code >= 0 && code < 11172) return code % 28 !== 0
  return /[013678LMNRlmnr]/.test(last)
}

/** 아주 옛 줄 "이름 · 2021년 출시 · 단종 · 시즌 한정 · 사유 기록 없음"을 문장으로. 새 서버는 이미 문장으로 보낸다. */
function historySentence(line: string) {
  if (!line.includes(" · ")) return plain(line)
  const [rawName, ...parts] = line.split(" · ")
  const name = rawName.replace(/\s*\((?:여름|시즌|계절)\s*한정\)/, "").trim()
  const year = parts.map((p) => p.match(/^(\d{4})년/)?.[1]).find(Boolean)
  const seasonal = parts.includes("시즌 한정") || rawName !== name
  const status = parts.find((p) => p === "단종" || p === "개발 중단") ?? (parts.some((p) => p.endsWith("출시")) ? "출시" : "")
  const reason = parts.filter((p) => !/^\d{4}년/.test(p) && !["단종", "개발 중단", "시즌 한정", "출시"].includes(p))
  const note = [year && `${year}년`, seasonal && "시즌 한정"].filter(Boolean).join(", ")
  const head = note ? `${name}(${note})` : name
  const [ida, eunNeun] = batchim(name) ? ["이", "은"] : ["가", "는"]
  const said = status === "단종" ? `${head}${ida} 단종된 적이 있어요.`
    : status === "개발 중단" ? `${head}${eunNeun} 개발을 중단했어요.`
      : status === "출시" ? `${head}${ida} 출시된 적이 있어요.` : `${head}의 기록이 있어요.`
  const why = reason[0] === "사유 기록 없음" ? "사유는 기록에 없어요." : reason.length ? `사유는 ${reason.join(", ")}예요.` : ""
  return [said, status === "단종" || status === "개발 중단" ? why : ""].filter(Boolean).join(" ")
}

/** 옛 payload의 문장 "밀키스 수박 500mL(2021년, 시즌 한정)이 단종된 적이 있어요. 사유는 …예요."를 표의 한 줄로. */
function parseHistory(line: string): DiagnosisHistoryRow | null {
  const s = historySentence(line)
  const m = s.match(/^(.+?)(?:\(([^)]*)\))?(?:이|가|은|는) (단종된 적이|개발을 중단했|출시된 적이)/)
  if (!m) return null
  const year = m[2]?.match(/(\d{4})년/)?.[1]
  const status = m[3].startsWith("단종") ? "단종" : m[3].startsWith("개발") ? "개발 중단" : "출시"
  const ended = status !== "출시"
  const said = s.match(/사유는 (.+?)예요\./)?.[1]
  const reasons = !ended || /사유는 기록에 없어요/.test(s) ? null : said ? said.split(", ") : []
  return { name: m[1].trim(), year: year ? Number(year) : null, status, reasons }
}

export function historyRows(section: HistorySection | undefined): DiagnosisHistoryRow[] {
  if (!section || section.status === "missing") return []
  if (section.rows) return section.rows
  return [section.summary, ...section.details].map(parseHistory).filter((r): r is DiagnosisHistoryRow => r !== null)
}

export const isEnded = (row: DiagnosisHistoryRow) => row.status === "단종" || row.status === "개발 중단"

// ---------- 유통 ----------

/** 진열할 수 있는 편의점의 비율(%). 상온 제품은 100. 모르면 null. */
export function shelfShare(section: HistorySection | undefined): { share: number; storage: string } | null {
  if (!section || section.status === "missing") return null
  const storage = section.storage ?? section.summary.match(/상온|냉동|냉장/)?.[0] ?? ""
  if (typeof section.rate === "number") return { share: section.rate * 100, storage }
  if (storage === "상온") return { share: 100, storage }
  return null
}

// ---------- 핵심 인사이트 ----------

/** 걸린 점의 조합으로 한 문장. 걸린 점마다 [이어지는 꼴, 끝나는 꼴]을 골라 이어 붙인다. */
export function insight(payload: DiagnosisPayload) {
  const clauses: string[][] = []
  const trend = sectionOf(payload, "trend")
  if (trend?.status === "flag") {
    const pair = trendPair(trend)
    const stages = trend.stages || []
    clauses.push(stages.includes("피크아웃") || (pair && pair.change < 0) ? c.insight.cooled
      : stages.includes("광고성 바이럴") ? c.insight.promoted : c.insight.trend)
  }
  const price = sectionOf(payload, "price")
  if (price?.status === "flag") {
    const f = priceFacts(price, payload)
    const gap = f.wtp && f.current != null ? f.current - f.wtp.median : null
    clauses.push(gap != null && gap > 0 ? c.insight.priceHigh(gap <= f.wtp!.median * 0.1) : c.insight.price)
  }
  const dist = sectionOf(payload, "distribution")
  if (dist?.status === "flag") {
    const shelf = shelfShare(dist)
    if (shelf) clauses.push(c.insight.shelf(shelf.share))
  }
  if (sectionOf(payload, "history")?.status === "flag") clauses.push(c.insight.history)
  if (!clauses.length) return c.insight.clear
  return clauses.map((pair, i) => pair[i === clauses.length - 1 ? 1 : 0]).join(", ") + "."
}
