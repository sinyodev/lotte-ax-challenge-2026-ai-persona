import { Link } from "@astryxdesign/core/Link"
import { Text } from "@astryxdesign/core/Text"
import { ideasHistoryCopy as c } from "../../copy/ideas-history"
import { Tag } from "./OriginTag"
import "./history.css"

type HistoryItem = {
  id: string
  name: string
  status: keyof typeof c.status
  reason: string | null
  has_original: boolean
  concept_excerpt?: string | null
  conditions?: string[]
}

/** 이름표와 그 글 한 묶음. 이름표 모양은 제품 특징(SpecSheet)과 같다. */
function Field({ label, children }: { label: string; children: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <Text type="supporting" color="secondary">{label}</Text>
      <Text>{children}</Text>
    </div>
  )
}

export function HistoryCard({ items }: { items: HistoryItem[] }) {
  if (!items.length) return <Text as="p">{c.empty}</Text>

  return (
    <div className="history-cases">
      <ul className="history-grid">
        {items.map((item) => (
          <li key={item.id} className="history-case">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <span className="min-w-0">
                <Link href={`/ideas?idea=${encodeURIComponent(item.id)}`} hasUnderline weight="medium" color="primary">
                  {item.name}
                </Link>
              </span>
              <span className="shrink-0"><Tag>{c.status[item.status] ?? item.status}</Tag></span>
            </div>
            <Field label={c.concept}>{item.concept_excerpt || (item.has_original ? c.noConcept : c.noOriginal)}</Field>
            <Field label={c.reasonLabel}>{item.reason ?? c.noReason}</Field>
            {Boolean(item.conditions?.length) && (
              <div className="flex flex-col gap-1">
                <Text type="supporting" color="secondary">{c.overlapLabel}</Text>
                <div className="flex flex-wrap gap-1.5">
                  {item.conditions!.map((cond) => <Tag key={cond} isDashed>{cond}</Tag>)}
                </div>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
