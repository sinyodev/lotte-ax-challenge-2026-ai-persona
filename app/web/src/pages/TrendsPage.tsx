import { useCallback, useEffect, useRef, useState } from "react"
import { generateId } from "ai"
import { Link, useNavigate, useSearchParams } from "react-router"
import { Button } from "@astryxdesign/core/Button"
import { Heading } from "@astryxdesign/core/Heading"
import { Spinner } from "@astryxdesign/core/Spinner"
import { Text } from "@astryxdesign/core/Text"
import { useTooltip } from "@astryxdesign/core/Tooltip"
import { ArrowLeftIcon } from "@heroicons/react/20/solid"
import { QuestionMarkCircleIcon } from "@heroicons/react/24/outline"
import type { TrendFeed, TrendIssue, TrendItem, TrendSource } from "../chat/contract-trend"
import { DailyTrend } from "../components/trend/DailyTrend"
import { ExternalLink, externalUrl, photoUrl, TrendSources } from "../components/trend/TrendSources"
import { trendCopy as c } from "../copy/trend"
import "../components/trend/trends.css"

function useFeed() {
  const [feed, setFeed] = useState<TrendFeed>()
  const [attempt, setAttempt] = useState(0)
  const [pending, setPending] = useState(true)
  const [failed, setFailed] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    fetch("/api/trends", { signal: controller.signal })
      .then((response) => response.ok ? response.json() as Promise<TrendFeed> : Promise.reject())
      .then((value) => {
        if (!controller.signal.aborted) {
          setFeed(value)
          setFailed(false)
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true)
      })
      .finally(() => {
        if (!controller.signal.aborted) setPending(false)
      })
    return () => controller.abort()
  }, [attempt])
  const refresh = async () => {
    setRefreshing(true)
    try {
      const response = await fetch("/api/trends/refresh", { method: "POST" })
      if (!response.ok) throw new Error()
      setFeed(await response.json() as TrendFeed)
      setFailed(false)
    } catch {
      setFailed(true)
    } finally {
      setRefreshing(false)
    }
  }
  const reload = useCallback(() => setAttempt((n) => n + 1), [])
  const retry = () => {
    setPending(true)
    reload()
  }
  return { feed, pending, failed, refreshing, refresh, retry, reload }
}

function FeedHeading({ daily }: { daily: boolean }) {
  const help = useTooltip({ touchTrigger: "tap", focusTrigger: "always", placement: "below" })
  return (
    <div className="news-heading">
      <Heading level={1}>{c.title}</Heading>
      <button className="news-help" type="button" ref={help.ref} aria-describedby={help.describedBy}
        aria-label={daily ? c.dailyHelp : c.feedHelp} onClick={(event) => { if (event.detail === 0) help.show() }}>
        <QuestionMarkCircleIcon aria-hidden="true" />
      </button>
      {help.renderTooltip(
        <span className="news-tip">
          <span>{c.collectionHelp}</span>
          <span>{daily ? c.dailyHelpDetail : c.newsroomHelp}</span>
        </span>
      )}
    </div>
  )
}

function SourceLine({ item }: { item: TrendItem }) {
  return <div className="news-source">
    <Text type="supporting" weight="medium">{item.publisher || c.sourceUnknown}</Text>
    {item.date && <time>{item.date.replaceAll("-", ".")}</time>}
  </div>
}

function contextFor(sources: TrendSource[] | undefined, fallback: string): string[] {
  return sources?.length
    ? sources.map((source) => [source.source, externalUrl(source.url)].filter(Boolean).join(" "))
    : [fallback || c.sourceUnknown]
}

function storyId(item: TrendItem) {
  return item.id || item.url || item.title
}

function hasSummary(item: TrendItem) {
  const normalize = (text: string) => text.replace(/\s+/g, " ").trim()
  const summary = normalize(item.summary ?? "")
  return Boolean(summary && summary !== normalize(item.title))
}

function StoryDetail({ item, onStart }: { item: TrendItem; onStart: () => void }) {
  const image = photoUrl(item.image)
  return (
    <article className="news-article">
      <Link className="news-back" to="/trends"><ArrowLeftIcon aria-hidden="true" />{c.back}</Link>
      <SourceLine item={item} />
      <Heading level={1}>{item.title}</Heading>
      {item.summary && <Text as="p">{item.summary}</Text>}
      {item.detail && <Text as="p">{item.detail}</Text>}
      {image && <figure className="news-photo">
        <img src={image} alt={item.alt ?? ""} referrerPolicy="no-referrer" />
        {item.photoCredit && <figcaption>
          <ExternalLink url={item.url} label={c.photoCredit(item.photoCredit)} />
        </figcaption>}
      </figure>}
      <TrendSources
        sources={item.sources}
        fallback={{ source: item.publisher, url: item.url, date: item.date }}
      />
      <div className="news-actions">
        <Button label={c.start} variant="primary" onClick={onStart} />
        {externalUrl(item.url) && <ExternalLink label={c.original} url={item.url} />}
      </div>
    </article>
  )
}

export function TrendsPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const { feed, pending, failed, refreshing, refresh, retry, reload } = useFeed()
  const post = params.get("post")
  const daily = params.get("view") === "tracking"
  const scrollArea = useRef<HTMLElement>(null)
  useEffect(() => {
    scrollArea.current?.scrollTo(0, 0)
  }, [post, daily])
  const news = feed?.items.filter((item) => item.source === "web") ?? []
  const stories = news.filter(hasSummary)
  const recent = news.filter((item) => !hasSummary(item) && externalUrl(item.url))
  const selected = post ? stories.find((item) => storyId(item) === post) : undefined
  const start = (title: string, question: string, topic: string, sources: string[]) => {
    const text = [
      question,
      c.context(title, sources),
      c.internalEvidence(topic || title),
    ].join("\n\n")
    navigate(`/concept/${generateId()}`, { state: { text } })
  }
  const startDaily = (issue: TrendIssue) => start(issue.title, issue.question, issue.topic, contextFor(
    issue.sources, [externalUrl(issue.searchUrl), externalUrl(issue.menuUrl)].filter(Boolean).join(", "),
  ))

  return (
    <section className="news-feed" aria-label={c.title} ref={scrollArea}>
      <div className="news-width">
        {post && pending ? <Spinner /> : selected ? <StoryDetail item={selected} onStart={() => start(
          selected.title, selected.question || c.ask(selected.keyword || selected.title), selected.keyword,
          contextFor(selected.sources, [selected.publisher, externalUrl(selected.url)].filter(Boolean).join(" ")),
        )} /> : <>
          <FeedHeading daily={daily} />
          <nav className="news-tabs" aria-label={c.views}>
            <Link to="/trends" aria-current={!daily ? "page" : undefined}>{c.newsletter}</Link>
            <Link to="/trends?view=tracking" aria-current={daily ? "page" : undefined}>{c.daily}</Link>
          </nav>
          <DailyTrend full={daily} onStart={startDaily} onEditionPublished={reload} />
          {!daily && <>
            {pending && <Spinner />}
            {failed && <div className="news-status" role="status">
              <Text>{c.feedError}</Text>
              <Button label={c.retry} variant="secondary" size="sm" onClick={retry} />
            </div>}
            {post && feed && !pending && <Text as="p" role="status">{c.missingStory}</Text>}
            {stories.length > 0 && <div className="news-list">
              {stories.map((item) => {
                const image = photoUrl(item.image)
                return <article className="news-row" key={storyId(item)}>
                  <SourceLine item={item} />
                  <Link className="news-headline" data-photo={Boolean(image)} aria-label={item.title}
                    to={`/trends?post=${encodeURIComponent(storyId(item))}`}>
                    <div className="news-copy">
                      <Heading level={2}>{item.title}</Heading>
                      {item.summary && <Text as="p">{item.summary}</Text>}
                    </div>
                    {image && <img className="news-thumb" src={image} alt={item.alt ?? ""} loading="lazy" referrerPolicy="no-referrer" />}
                  </Link>
                </article>
              })}
            </div>}
            {recent.length > 0 && <details className="news-references news-recent">
              <summary>{c.recentReleases}</summary>
              <ul>{recent.map((item) => <li key={storyId(item)}>
                <ExternalLink label={item.title} url={item.url} />
                <SourceLine item={item} />
              </li>)}</ul>
            </details>}
            {!stories.length && !recent.length && !pending && !failed && <Text as="p">{c.feedEmpty}</Text>}
            <nav className="news-footer" aria-label={c.publicChannels}>
              <ExternalLink label={c.google.name} url={c.google.url} />
              <ExternalLink label={c.naver.name} url={c.naver.url} />
            </nav>
            <div className="news-footer">
              <Button label={c.refresh} variant="secondary" size="sm" isLoading={refreshing}
                isDisabled={pending || refreshing} onClick={() => void refresh()} />
              {feed?.collected_at && <Text type="supporting">{c.collected(
                new Date(feed.collected_at).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" }),
              )}</Text>}
            </div>
          </>}
        </>}
      </div>
    </section>
  )
}
