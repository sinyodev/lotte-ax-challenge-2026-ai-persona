import { Text } from "@astryxdesign/core/Text"
import { ArrowUpRightIcon } from "@heroicons/react/20/solid"
import type { TrendSource } from "../../chat/contract-trend"
import { trendCopy as c } from "../../copy/trend"

const pressImageHosts = new Set([
  "origin.bgf.co.kr",
  "company.lottechilsung.co.kr",
  "www.shinsegaegroupnewsroom.com",
  "images.shinsegaegroupnewsroom.com",
])

export function externalUrl(value?: string | null): string | undefined {
  if (!value) return undefined
  try {
    const url = new URL(value)
    if (url.protocol === "https:" || url.protocol === "http:") return url.href
  } catch {
    return undefined
  }
}

export function photoUrl(value?: string | null): string | undefined {
  if (!value) return undefined
  if (/^\/api\/trends\/photos\/[\w.-]+$/.test(value)) return value
  try {
    const url = new URL(value)
    if (url.protocol === "https:" && !url.port && !url.username && !url.password && pressImageHosts.has(url.hostname)) {
      return url.href
    }
  } catch {
    return undefined
  }
}

export function ExternalLink({ label, url }: { label: string; url?: string | null }) {
  const href = externalUrl(url)
  if (!href) return <span>{label}</span>
  return <a className="news-external" href={href} target="_blank" rel="noreferrer">
    {label}<ArrowUpRightIcon aria-hidden="true" />
  </a>
}

export function TrendSources({
  sources, fallback, note,
}: {
  sources?: TrendSource[]
  fallback?: { url: string | null; source: string | null; date: string | null }
  note?: string | null
}) {
  const rows = sources?.length ? sources : fallback ? [{ ...fallback, text: "" }] : []
  if (!rows.length && !note) return null
  return (
    <details className="news-references">
      <summary>{c.sources}</summary>
      <ul>
        {rows.map((source, i) => <li key={`${source.url}-${i}`}>
          <ExternalLink url={source.url} label={source.source || c.sourceUnknown} />
          {source.date && <Text type="supporting">{source.date}</Text>}
          {source.text && <Text as="p">{source.text}</Text>}
        </li>)}
        {note && <li><Text as="p">{note}</Text></li>}
      </ul>
    </details>
  )
}
