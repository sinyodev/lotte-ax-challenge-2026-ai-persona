import type { ReactNode } from "react"
import { ideaCheckKeys, ideaStatuses, type IdeaChecks, type IdeaStatus } from "../../chat/contract-ideas"
import { ideasCopy as c } from "../../copy/ideas"

const percent = new Intl.NumberFormat("ko-KR", { style: "percent", maximumFractionDigits: 1 })
const workDay = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul", dateStyle: "short" })
export const formatPercent = (value: number | undefined | null) => value == null ? c.blank : percent.format(value)
export function formatDate(value: string | null | undefined) {
  if (!value) return c.blank
  const timestamp = value.includes("T") ? Date.parse(value) : NaN
  return Number.isFinite(timestamp) ? workDay.format(timestamp) : value.split("T")[0]
}
export function formatWorkText(text: string) {
  const auditPrefix = "단계: "
  return text.split("\n").map(line => {
    if (!line.startsWith(auditPrefix)) return line
    const status = line.slice(auditPrefix.length) as IdeaStatus
    return Object.hasOwn(c.statuses, status) ? c.workStage(c.statuses[status]) : line
  }).join("\n")
}
export const chatHref = (id: string) => `/concept/${encodeURIComponent(id)}`
export type IdeaDetailHref = (id: string) => string
export const ideaDetailLinkState = { ideasDetail: true }

export function IdeaField({ label, children }: { label: string; children: ReactNode }) {
  return <label className="idea-field"><span>{label}</span>{children}</label>
}

export function StatusOptions() {
  return <>{ideaStatuses.map((status) => <option key={status} value={status}>{c.statuses[status]}</option>)}</>
}

export function EditableChecks({ checks, onChange }: {
  checks: IdeaChecks; onChange: (checks: IdeaChecks, changed: keyof IdeaChecks) => void
}) {
  return <fieldset className="idea-edit-checks">
    <legend>{c.fields.checks}</legend>
    {ideaCheckKeys.map((key) => <label key={key}>
      <input type="checkbox" checked={checks[key]} onChange={(event) => onChange({ ...checks, [key]: event.target.checked }, key)} />
      {c.checks[key]}
    </label>)}
  </fieldset>
}
