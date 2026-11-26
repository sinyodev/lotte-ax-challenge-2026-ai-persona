import { useEffect, useState } from "react"
import { Button } from "@astryxdesign/core/Button"
import { Heading } from "@astryxdesign/core/Heading"
import { Spinner } from "@astryxdesign/core/Spinner"
import { ArrowDownTrayIcon, PlusIcon } from "@heroicons/react/20/solid"
import { Link, useLocation, useNavigate, useSearchParams } from "react-router"
import { ideaRequest, type IdeaPatch, type IdeaRow, type IdeasDashboard as Dashboard } from "../chat/contract-ideas"
import { IdeasDashboard } from "../components/ideas/IdeasDashboard"
import { IdeasImport } from "../components/ideas/IdeasImport"
import { IdeasBoard } from "../components/ideas/IdeasBoard"
import { IdeasCases } from "../components/ideas/IdeasCases"
import { IdeaDetail } from "../components/ideas/IdeaDetail"
import { ideaDetailLinkState, IdeaField } from "../components/ideas/IdeaFields"
import { ideasCopy as c } from "../copy/ideas"
import "../components/ideas/ideas.css"

type View = "board" | "dashboard" | "import"

function useIdeasResource<T>(path: string, enabled: boolean, version: number) {
  const [data, setData] = useState<T>()
  const [read, setRead] = useState<{ version: number; failed: boolean }>()

  useEffect(() => {
    if (!enabled) return
    const controller = new AbortController()
    ideaRequest<T>(path, { signal: controller.signal }).then(value => {
      if (controller.signal.aborted) return
      setData(value)
      setRead({ version, failed: false })
    }).catch(() => {
      if (!controller.signal.aborted) setRead({ version, failed: true })
    })
    return () => controller.abort()
  }, [enabled, path, version])

  const settled = read?.version === version
  return { data, setData, settled, failed: settled && read.failed }
}

export function IdeasPage() {
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  const requestedView = params.get("view")
  const view = requestedView === "dashboard" || requestedView === "import" ? requestedView : "board"
  const selected = params.get("idea")
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState("")
  const [key, setKey] = useState(() => crypto.randomUUID())
  const [message, setMessage] = useState("")
  const [version, setVersion] = useState(0)
  const [busy, setBusy] = useState(false)
  const board = useIdeasResource<{ items: IdeaRow[] }>("", view === "board" || Boolean(selected), version)
  const dashboard = useIdeasResource<Dashboard>("/dashboard", view === "dashboard", version)
  const items = board.data?.items
  const active = items?.find(row => row.id === selected)
  const mainResult = view === "dashboard" ? dashboard : board

  const refresh = () => setVersion(previous => previous + 1)

  useEffect(() => {
    if (view === "import") return
    function syncVisibleBoard() {
      if (document.visibilityState === "visible") setVersion(previous => previous + 1)
    }
    const timer = window.setInterval(syncVisibleBoard, 60_000)
    document.addEventListener("visibilitychange", syncVisibleBoard)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener("visibilitychange", syncVisibleBoard)
    }
  }, [view])

  function viewHref(next: View) {
    const nextParams = new URLSearchParams(params)
    nextParams.delete("idea")
    if (next === "board") nextParams.delete("view")
    else nextParams.set("view", next)
    const query = nextParams.toString()
    return query ? `/ideas?${query}` : "/ideas"
  }

  function detailHref(id: string) {
    const nextParams = new URLSearchParams(params)
    nextParams.set("idea", id)
    return `/ideas?${nextParams}`
  }

  function closeDetail() {
    if (location.state?.ideasDetail) {
      navigate(-1)
    } else {
      const nextParams = new URLSearchParams(params)
      nextParams.delete("idea")
      setParams(nextParams, { replace: true })
    }
  }

  function changeView(next: View) {
    setAdding(false)
    navigate(viewHref(next))
  }

  function startAdding() {
    if (view !== "board") navigate(viewHref("board"))
    setAdding(true)
    setMessage("")
  }

  async function save(id: string, patch: IdeaPatch) {
    const row = await ideaRequest<IdeaRow>("/" + encodeURIComponent(id), { method: "PATCH", body: patch })
    board.setData(current => current && { items: current.items.map(item => item.id === id ? row : item) })
    refresh()
  }

  async function create() {
    if (busy || !name.trim()) return
    setBusy(true)
    setMessage("")
    try {
      const row = await ideaRequest<IdeaRow>("", { method: "POST", body: { name: name.trim(), key } })
      board.setData(current => ({ items: [row, ...(current?.items ?? []).filter(item => item.id !== row.id)] }))
      setKey(crypto.randomUUID())
      setName("")
      setAdding(false)
      const nextParams = new URLSearchParams(params)
      nextParams.delete("view")
      nextParams.set("idea", row.id)
      setParams(nextParams, { state: ideaDetailLinkState })
      refresh()
    } catch {
      setMessage(c.saveError)
    } finally {
      setBusy(false)
    }
  }

  return <main className="ideas-page"><div className="ideas-width">
    <header className="idea-section-heading">
      <Heading level={1}>{c.title}</Heading>
      <div className="idea-toolbar">
        <Button label={c.import} variant="secondary" icon={<ArrowDownTrayIcon width={16}/>} onClick={() => changeView("import")}/>
        <Button label={c.add} variant="primary" icon={<PlusIcon width={16}/>} onClick={startAdding}/>
      </div>
    </header>
    {view === "import" ? <IdeasImport onClose={() => changeView("board")} onCommit={() => {
      changeView("board")
      refresh()
    }}/> : <>
      <nav className="idea-views" aria-label={c.viewLabel}>
        <Link to={viewHref("board")} aria-current={view === "board" ? "page" : undefined} onClick={() => setAdding(false)}>
          {c.boardTab}
        </Link>
        <Link to={viewHref("dashboard")} aria-current={view === "dashboard" ? "page" : undefined} onClick={() => setAdding(false)}>
          {c.dashboardTab}
        </Link>
      </nav>
      {mainResult.failed && <div className="idea-inline" role="alert">
        <p>{view === "dashboard" ? c.dashboardError : c.boardError}</p>
        <Button label={c.retry} variant="secondary" size="sm" onClick={refresh}/>
      </div>}
      {!mainResult.data && !mainResult.failed && <Spinner aria-label={c.loading}/>}
      {view === "dashboard" && dashboard.data && <IdeasDashboard data={dashboard.data} detailHref={detailHref}/>}
      {view === "board" && <>
        {adding && <form className="idea-inline idea-add-form" onSubmit={event => { event.preventDefault(); void create() }}>
          <IdeaField label={c.nameLabel}><input autoFocus maxLength={300} value={name} onChange={event => setName(event.target.value)} required/></IdeaField>
          <Button label={c.save} variant="primary" type="submit" isLoading={busy} isDisabled={busy || !name.trim()}/>
          <Button label={c.close} variant="ghost" onClick={() => setAdding(false)} isDisabled={busy}/>
          {message && <p role="alert">{message}</p>}
        </form>}
        <IdeasBoard items={items} openedStatus={active?.status} detailHref={detailHref} save={save} add={startAdding}/>
      </>}
      {view === "dashboard" && <IdeasCases detailHref={detailHref} version={version}/>}
    </>}
    {selected && !active && <div className="idea-inline" role="status">
      {board.settled ? <p>{board.failed ? c.boardError : c.ideaMissing}</p> : <Spinner aria-label={c.loading}/>}
      {board.failed && <Button label={c.retry} variant="secondary" size="sm" onClick={refresh}/>}
      <Button label={c.close} variant="ghost" size="sm" onClick={closeDetail}/>
    </div>}
    {active && <IdeaDetail key={active.id} row={active} version={version} close={closeDetail} save={save} refresh={refresh}/>}
  </div></main>
}
