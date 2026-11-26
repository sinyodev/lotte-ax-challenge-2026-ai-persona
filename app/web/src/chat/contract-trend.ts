export type TrendStage = "상승기" | "피크아웃" | "계절성 수요" | "광고성 바이럴" | "안정기"

export type TrendMonth = {
  month: string
  search_index: number | null
  sns_mentions: number | null
  sns_organic: number | null
  ad_share: number | null
}

export type TrendVerdict = {
  keyword: string
  stage: TrendStage[]
  reasons: string[]
  series: TrendMonth[]
  ad_share_peak: number | null
  product_search_share: number | null
  related: { related: string; share: number | null }[]
  source: string
}

export type TrendSource = {
  source: string
  date: string | null
  text: string
  url: string
}

type PressPhoto = {
  image?: string | null
  alt?: string | null
  photoCredit?: string | null
}

export type TrendItem = PressPhoto & {
  id?: string | null
  keyword: string
  title: string
  source: "web" | "internal"
  publisher: string | null
  url: string | null
  date: string | null
  verdict: TrendVerdict | null
  kind?: string | null
  summary?: string | null
  detail?: string | null
  sources?: TrendSource[]
  question?: string | null
}

export type TrendFeed = {
  items: TrendItem[]
  collected_at: string | null
}

export type TrendIssue = PressPhoto & {
  id: string
  date: string
  title: string
  observation: string
  menu: string | null
  question: string
  period: string | null
  ranks: { day: string; rank: number | null }[]
  searchUrl: string | null
  menuUrl: string | null
  topic: string
  sources: TrendSource[]
}

export type TrendChannel = {
  ok: boolean
  rows: { topic: string; when: string | null; label: string; url: string | null }[]
}

export type TrendTracking = {
  edition: {
    day: string
    collectedAt: string | null
    channels: { google: TrendChannel; naver: TrendChannel }
    issue: TrendIssue | null
  }
  nextAt: string | null
}
