import { useEffect, useRef, useState } from "react"
import { Link } from "react-router"
import { Button } from "@astryxdesign/core/Button"
import { Heading } from "@astryxdesign/core/Heading"
import { Text } from "@astryxdesign/core/Text"
import type { TrendChannel, TrendIssue, TrendTracking } from "../../chat/contract-trend"
import { trendCopy as c } from "../../copy/trend"
import { ExternalLink, photoUrl, TrendSources } from "./TrendSources"

function dayLabel(value: string) {
  return new Intl.DateTimeFormat("ko-KR", { month: "long", day: "numeric", timeZone: "UTC" })
    .format(new Date(`${value}T00:00:00Z`))
}

function useTracking(onEditionPublished: () => void) {
  const [packet, setPacket] = useState<TrendTracking>()
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const lastEdition = useRef<string>(undefined)
  useEffect(() => {
    const controller = new AbortController()
    let timer = 0
    let nextAt = 0
    let loading = false
    let retriedDay: string | undefined
    async function read() {
      if (loading || controller.signal.aborted || Date.now() < nextAt) return
      loading = true
      try {
        const resp = await fetch("/api/trends/tracking", { signal: controller.signal })
        if (!resp.ok) throw new Error()
        const data: TrendTracking = await resp.json()
        if (controller.signal.aborted) return
        setPacket(data)
        setFailed(false)
        const { day, collectedAt } = data.edition
        const edition = `${day}:${collectedAt ?? ""}`
        if (lastEdition.current && lastEdition.current !== edition && collectedAt) onEditionPublished()
        lastEdition.current = edition
        nextAt = data.nextAt ? Date.parse(data.nextAt) : 0
        // 서버의 발행이 늦으면 같은 발행일에 한 번만 더 확인한다.
        if (!collectedAt && retriedDay !== day) {
          retriedDay = day
          nextAt = Date.now() + 15_000
        }
        if (nextAt > Date.now()) {
          timer = window.setTimeout(read, nextAt - Date.now() + 1000)
        }
      } catch {
        if (!controller.signal.aborted) setFailed(true)
      } finally {
        loading = false
      }
    }
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        window.clearTimeout(timer)
        if (nextAt > Date.now()) {
          timer = window.setTimeout(read, nextAt - Date.now() + 1000)
        } else {
          void read()
        }
      }
    }
    void read()
    document.addEventListener("visibilitychange", onVisible)
    return () => {
      controller.abort()
      window.clearTimeout(timer)
      document.removeEventListener("visibilitychange", onVisible)
    }
  }, [attempt, onEditionPublished])
  return { packet, failed, retry: () => setAttempt((n) => n + 1) }
}

function Channel({ channel, name, url }: { channel: TrendChannel; name: string; url: string }) {
  if (!channel.ok) return null
  return (
    <div className="news-channel">
      <ExternalLink label={name} url={url} />
      {channel.rows.length > 0 && <ul>
        {channel.rows.map((row, i) => <li key={`${row.topic}-${i}`}>
          <ExternalLink label={row.topic} url={row.url} />
          <Text type="supporting">{row.label}</Text>
        </li>)}
      </ul>}
    </div>
  )
}

export function DailyTrend({ full, onStart, onEditionPublished }: {
  full: boolean
  onStart: (issue: TrendIssue) => void
  onEditionPublished: () => void
}) {
  const { packet, failed, retry } = useTracking(onEditionPublished)
  const issue = packet?.edition.issue
  const date = issue?.date ?? packet?.edition.day
  const isLatest = issue?.date === packet?.edition.day
  const image = photoUrl(issue?.image)
  const rankNote = issue?.ranks.length ? [
    issue.period,
    issue.ranks.map((rank) => c.naverRanks(Number(rank.day.slice(-2)), rank.rank)).join(", "),
  ].filter(Boolean).join(" · ") : null
  const channels = packet?.edition.channels
  const status = failed
    ? packet ? c.trackingStale : c.trackingError
    : packet && !issue
      ? channels?.naver.ok && channels?.google.ok ? c.trackingEmpty : c.trackingUnavailable
      : packet ? null : c.trackingLoading

  return (
    <section className="news-digest" aria-label={c.daily}>
      <div className="news-source">
        {date && <Text type="supporting" weight="medium">
          {isLatest ? c.latestEdition(dayLabel(date)) : issue ? c.previousEdition(dayLabel(date)) : dayLabel(date)}
        </Text>}
        <Text type="supporting">{c.schedule}</Text>
      </div>
      {status && <div className="news-status" role="status">
        <Text type="supporting">{status}</Text>
        {(failed || (packet && !packet.edition.collectedAt)) && <Button size="sm" variant="secondary" label={c.retry} onClick={retry} />}
      </div>}
      {issue && full && <article className="news-daily-article">
        {!isLatest && <Text as="p" type="supporting">
          {channels?.naver.ok && channels?.google.ok ? c.previousNotice : c.previousUnavailable}
        </Text>}
        <Heading level={2}>{issue.title}</Heading>
        <Text as="p">{[issue.observation, issue.menu].filter(Boolean).join(" ")}</Text>
        <Text as="p" weight="medium">{issue.question}</Text>
        {image && <figure className="news-photo">
          <img src={image} alt={issue.alt ?? ""} referrerPolicy="no-referrer" />
          {issue.photoCredit && <figcaption>
            <ExternalLink label={c.photoCredit(issue.photoCredit)} url={issue.menuUrl} />
          </figcaption>}
        </figure>}
        <TrendSources sources={issue.sources} note={rankNote} />
        <Button label={c.start} variant="primary" onClick={() => onStart(issue)} />
      </article>}
      {issue && !full && <Link to="/trends?view=tracking" className="news-headline" data-photo={Boolean(image)} aria-label={issue.title}>
        <div className="news-copy">
          <Heading level={2}>{issue.title}</Heading>
          <Text as="p">{[issue.observation, issue.menu].filter(Boolean).join(" ")}</Text>
        </div>
        {image && <img className="news-thumb" src={image} alt={issue.alt ?? ""} referrerPolicy="no-referrer" />}
      </Link>}
      {full && channels && !issue && (channels.google.ok || channels.naver.ok) && (
        <details className="news-references">
          <summary>{c.sources}</summary>
          <Channel channel={channels.google} {...c.google} />
          <Channel channel={channels.naver} {...c.naver} />
        </details>
      )}
    </section>
  )
}
