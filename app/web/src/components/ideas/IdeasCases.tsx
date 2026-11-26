import { useEffect, useState } from "react"
import { Button } from "@astryxdesign/core/Button"
import { Heading } from "@astryxdesign/core/Heading"
import { Spinner } from "@astryxdesign/core/Spinner"
import { ChevronRightIcon } from "@heroicons/react/20/solid"
import { Link } from "react-router"
import { ideaRequest, type IdeaRow } from "../../chat/contract-ideas"
import { ideasCopy as c } from "../../copy/ideas"
import { ideaDetailLinkState, IdeaField, type IdeaDetailHref } from "./IdeaFields"

export function IdeasCases({ detailHref, version }: { detailHref: IdeaDetailHref; version: number }) {
  const [text, setText] = useState("")
  const [query, setQuery] = useState("")
  const [retry, setRetry] = useState(0)
  const [result, setResult] = useState<{ query: string; items: IdeaRow[] | null }>()
  const cases = result?.query === query ? result.items : undefined

  useEffect(() => {
    const controller = new AbortController()
    ideaRequest<{ items: IdeaRow[] }>("/cases?" + new URLSearchParams({ q: query }), { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setResult({ query, items: data.items }) })
      .catch(() => { if (!controller.signal.aborted) setResult({ query, items: null }) })
    return () => controller.abort()
  }, [query, retry, version])

  return <section className="idea-cases" aria-labelledby="idea-cases-title">
    <Heading level={2} id="idea-cases-title">{c.caseTitle}</Heading>
    <form className="idea-inline" role="search" aria-labelledby="idea-cases-title" onSubmit={event => {
      event.preventDefault()
      setQuery(text.trim())
      setRetry(previous => previous + 1)
    }}>
      <IdeaField label={c.caseSearch}>
        <input type="search" value={text} placeholder={c.caseSearchHint} onChange={event => setText(event.target.value)}/>
      </IdeaField>
      <Button type="submit" variant="secondary" label={c.findCases}/>
    </form>
    {cases === undefined && <Spinner aria-label={c.loading}/>}
    {cases === null && <div className="idea-inline" role="alert">
      <p>{c.caseError}</p>
      <Button label={c.retry} variant="secondary" size="sm" onClick={() => setRetry(previous => previous + 1)}/>
    </div>}
    {cases?.length === 0 && <p role="status" className="idea-muted">{c.caseEmpty}</p>}
    {cases && cases.length > 0 && <ul className="idea-case-list">
      {cases.map(row => <li key={row.id}>
        <Link to={detailHref(row.id)} state={ideaDetailLinkState} className="idea-case-link">
          <div className="idea-case-summary">
            <span className="idea-case-name">{row.name}</span>
            <span className="idea-case-status">
              {c.statuses[row.status === "폐기" || row.status === "단종" ? row.status : "출시"]}
            </span>
          </div>
          <p>{row.reason || c.unknownReason}</p>
          <ChevronRightIcon width={16} aria-hidden="true"/>
        </Link>
      </li>)}
    </ul>}
  </section>
}
