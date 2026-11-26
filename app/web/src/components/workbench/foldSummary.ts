import type { BriefPayload, EvidencePayload } from "../../chat/contract"
import type { TrendItem } from "../../chat/contract-trend"
import type { WorkCard } from "../../chat/workbenchStore"
import { foldCopy as f } from "../../copy/fold"
import { ideasHistoryCopy } from "../../copy/ideas-history"

/** 작업대에서 접히는 카드의 종류. 다른 종류는 늘 펼쳐 둔다. */
export const FOLDABLE_KINDS = new Set(["brief", "evidence", "trend", "history"])

/** 첫 문장만. */
const firstSentence = (text: string) => (/^.*?[.!?](?=\s|$)/.exec(text.trim())?.[0] ?? text.trim())

function briefLine(p: BriefPayload | null) {
  const fields = p?.fields ?? []
  const value = (key: string) => fields.find((x) => x.key === key)?.value
  const target = value("target")
  const occasion = value("occasion")
  if (target && occasion) return f.brief(target, occasion)
  return target ?? occasion ?? value("need") ?? value("product") ?? ""
}

/** 찾아본 것: 가장 앞에 온 근거의 첫 문장. */
function evidenceLine(p: EvidencePayload | null) {
  const first = p?.items?.[0]
  return first ? firstSentence(first.text) : ""
}

/** 트렌드 조사: 내부 자료의 판정. 판정이 없으면 첫 소식의 제목. */
function trendLine(p: { items?: TrendItem[] } | null) {
  const items = p?.items ?? []
  const judged = items.find((it) => it.verdict)
  if (judged?.verdict?.stage.length) return f.trend(judged.verdict.keyword || judged.keyword, judged.verdict.stage)
  return items[0]?.title ?? ""
}

/** 비슷한 과거 사례: 가장 앞에 온 사례가 어떻게 됐는지. */
function historyLine(p: { items?: { name: string; status: string }[] } | null) {
  const first = p?.items?.[0]
  if (!first) return ""
  const labels = ideasHistoryCopy.status as Record<string, string>
  return f.history(first.name, labels[first.status] ?? first.status)
}

/** 접힌 카드 머리에 붙는 결론 한 줄. 받은 값만으로 만든다. 건수를 가운뎃점으로 잇지 않는다(참가자의 검수). */
export function foldSummary(card: WorkCard): string {
  switch (card.kind) {
    case "brief":
      return briefLine(card.payload as BriefPayload | null)
    case "evidence":
      return evidenceLine(card.payload as EvidencePayload | null)
    case "trend":
      return trendLine(card.payload as { items?: TrendItem[] } | null)
    case "history":
      return historyLine(card.payload as { items?: { name: string; status: string }[] } | null)
    default:
      return ""
  }
}
