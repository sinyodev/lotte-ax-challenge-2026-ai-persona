import { useEffect, useRef, useState } from "react"
import { Button } from "@astryxdesign/core/Button"
import { Badge } from "@astryxdesign/core/Badge"
import { Heading } from "@astryxdesign/core/Heading"
import { Spinner } from "@astryxdesign/core/Spinner"
import { PaperClipIcon, XMarkIcon } from "@heroicons/react/20/solid"
import { ideaCheckKeys, ideaRequest, type IdeaChecks, type IdeaLog, type IdeaPatch, type IdeaRow } from "../../chat/contract-ideas"
import { ideasCopy as c } from "../../copy/ideas"
import { chatHref, EditableChecks, formatDate, formatPercent, formatWorkText, IdeaField, StatusOptions } from "./IdeaFields"

async function fileContent(file: File) {
  if (file.size > 8 * 1024 * 1024) throw new Error(c.fileLimit)
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(",")[1])
    reader.onerror = () => reject(new Error(c.saveError))
    reader.readAsDataURL(file)
  })
}

function reasonLabel(status: IdeaRow["status"]) {
  switch (status) {
    case "폐기": return c.stoppedReason
    case "단종": return c.discontinuedReason
    case "보류": return c.heldReason
    case "출시": return c.launchReason
    default: return c.fields.reason
  }
}

export function IdeaDetail({ row, version, close, save, refresh }: {
  row: IdeaRow; version: number; close: () => void; save: (id: string, patch: IdeaPatch) => Promise<void>; refresh: () => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const [draft, setDraft] = useState<IdeaPatch>({})
  const [editing, setEditing] = useState<"name" | "concept" | null>(null)
  const [logs, setLogs] = useState<IdeaLog[]>()
  const [text, setText] = useState("")
  const [file, setFile] = useState<File>()
  const [key, setKey] = useState(() => crypto.randomUUID())
  const [busy, setBusy] = useState(false)
  const [fieldsMessage, setFieldsMessage] = useState("")
  const [logMessage, setLogMessage] = useState("")
  const [logFailed, setLogFailed] = useState(false)
  const [logRetry, setLogRetry] = useState(0)
  const base = "/" + encodeURIComponent(row.id) + "/logs"
  const name = draft.name ?? row.name
  const status = draft.status ?? row.status
  const checks = { ...row.checks, ...draft.checks }
  const canEditLaunch = status === "출시" || status === "단종"

  function edit<K extends keyof Omit<IdeaPatch, "checks">>(field: K, value: NonNullable<IdeaPatch[K]>) {
    setDraft(current => {
      const next = { ...current, [field]: value }
      if (value === (row[field] ?? "")) delete next[field]
      return next
    })
  }

  function editCheck(next: IdeaChecks, phase: keyof IdeaChecks) {
    setDraft(current => {
      const changed = { ...current.checks, [phase]: next[phase] }
      if (next[phase] === row.checks[phase]) delete changed[phase]
      return { ...current, checks: changed }
    })
  }
  useEffect(() => {
    const el = dialog.current
    el?.showModal()
    return () => { el?.close() }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    ideaRequest<{ items: IdeaLog[] }>(base, { signal: controller.signal })
      .then(data => {
        if (controller.signal.aborted) return
        setLogs(data.items)
        setLogFailed(false)
      })
      .catch(() => { if (!controller.signal.aborted) setLogFailed(true) })
    return () => controller.abort()
  }, [base, logRetry, version])
  async function submitLog() {
    if (busy || (!text.trim() && !file)) return
    setBusy(true)
    setLogMessage("")
    try {
      const body = { key, text: text.trim(), filename: file?.name, content_base64: file ? await fileContent(file) : undefined }
      await ideaRequest(base, { method: "POST", body })
      setText("")
      setFile(undefined)
      setKey(crypto.randomUUID())
      setLogFailed(false)
      setLogMessage(c.saved)
      if (input.current) input.current.value = ""
      refresh()
    } catch (e) { setLogMessage(e instanceof Error && e.message || c.saveError) }
    finally { setBusy(false) }
  }
  async function submitFields() {
    if (!name.trim() || busy) return
    const patch: IdeaPatch = {}
    if (draft.name !== undefined && name.trim() !== row.name) patch.name = name.trim()
    for (const field of ["owner", "concept", "verdict", "reason"] as const) {
      if (draft[field] === undefined) continue
      const value = draft[field]?.trim() || null
      if (value !== (row[field] ?? null)) patch[field] = value
    }
    if (draft.status !== undefined && status !== row.status) patch.status = status
    if (canEditLaunch && draft.launched_on !== undefined && (draft.launched_on || null) !== (row.launched_on ?? null)) {
      patch.launched_on = draft.launched_on || null
    }
    for (const phase of ideaCheckKeys) {
      const value = draft.checks?.[phase]
      if (value !== undefined && value !== row.checks[phase]) (patch.checks ??= {})[phase] = value
    }
    if (!Object.keys(patch).length) {
      setDraft({})
      setEditing(null)
      return
    }
    setBusy(true)
    setFieldsMessage("")
    try {
      await save(row.id, patch)
      setDraft({})
      setEditing(null)
      setLogFailed(false)
      setFieldsMessage(c.saved)
    } catch { setFieldsMessage(c.saveError) }
    finally { setBusy(false) }
  }
  return <dialog ref={dialog} className="idea-drawer" aria-labelledby="idea-detail-heading"
    onCancel={e => { e.preventDefault(); close() }}>
    <header className="idea-drawer-heading">
      <Heading level={2} id="idea-detail-heading">{row.name}</Heading>
      <Button label={c.close} isIconOnly icon={<XMarkIcon width={18}/>} variant="ghost" onClick={close}/>
    </header>
    {!editing && <div className="idea-detail-overview">
      <div className="idea-section-heading">
        <div className="idea-toolbar">
          <Badge label={c.statuses[row.status]} variant="neutral"/>
          <span>{c.fields.owner} {row.owner || c.noOwner}</span>
        </div>
        <Button label={c.editIdea} variant="secondary" size="sm" onClick={() => {setFieldsMessage(""); setEditing("name")}}/>
      </div>
      <section className="idea-detail-block">
        <Heading level={3}>{c.fields.concept}</Heading>
        {row.concept ? <p>{row.concept}</p> : <button className="idea-add-concept" type="button"
          onClick={() => {setFieldsMessage(""); setEditing("concept")}}>{c.addConcept}</button>}
      </section>
      {row.launched_on && <p>{c.fields.launched_on} <time dateTime={row.launched_on}>{formatDate(row.launched_on)}</time></p>}
      {row.verdict && <section className="idea-detail-block"><Heading level={3}>{c.fields.verdict}</Heading><p>{row.verdict}</p></section>}
      {(row.reason || ["폐기", "단종", "보류"].includes(row.status)) && <section className="idea-detail-block">
        <Heading level={3}>{reasonLabel(row.status)}</Heading><p>{row.reason || c.unknownReason}</p>
      </section>}
      {row.last_test && <details className="idea-test-details">
        <summary>{c.testResult}</summary>
        <dl className="idea-result-metrics">
          <div><dt>{c.fields.selection_rate}</dt><dd>{formatPercent(row.last_test.selection_rate)}</dd></div>
          <div><dt>{c.fields.own_share}</dt><dd>{formatPercent(row.last_test.own_share)}</dd></div>
          <div><dt>{c.fields.virtual_sales}</dt><dd>{row.last_test.virtual_sales || c.blank}</dd></div>
        </dl>
      </details>}
      {row.chat_id && <div className="idea-toolbar">
        <Button label={c.originalChat} href={chatHref(row.chat_id)} variant="ghost" size="sm"/>
        <Button label={c.proposal} href={"/proposal/"+encodeURIComponent(row.chat_id)} variant="ghost" size="sm"/>
      </div>}
    </div>}
    {editing && <form className="idea-detail-form" onSubmit={e => { e.preventDefault(); void submitFields() }}>
      <fieldset className="idea-detail-fields" disabled={busy}>
        <div className="idea-edit-fields">
          <IdeaField label={c.nameLabel}><input autoFocus={editing === "name"} value={name} maxLength={300} required onChange={e => edit("name", e.target.value)}/></IdeaField>
          <IdeaField label={c.fields.status}><select value={status} onChange={e => edit("status", e.target.value as IdeaRow["status"])}><StatusOptions/></select></IdeaField>
          {row.source === "chat" ? <div className="idea-field">
            <span>{c.fields.owner}</span><span>{row.owner || c.noOwner}</span>
          </div> : <IdeaField label={c.fields.owner}><input value={draft.owner ?? row.owner ?? ""} placeholder={c.noOwner} onChange={e => edit("owner", e.target.value)}/></IdeaField>}
          {canEditLaunch ? <IdeaField label={c.fields.launched_on}>
            <input type="date" value={draft.launched_on ?? row.launched_on ?? ""} onChange={e => edit("launched_on", e.target.value)}/>
          </IdeaField> : row.launched_on && <div className="idea-field">
            <span>{c.fields.launched_on}</span><time dateTime={row.launched_on}>{formatDate(row.launched_on)}</time>
          </div>}
        </div>
        <IdeaField label={c.fields.concept}><textarea autoFocus={editing === "concept"} rows={4} value={draft.concept ?? row.concept ?? ""} onChange={e => edit("concept", e.target.value)}/></IdeaField>
        <IdeaField label={c.fields.verdict}><input value={draft.verdict ?? row.verdict ?? ""} onChange={e => edit("verdict", e.target.value)}/></IdeaField>
        <IdeaField label={reasonLabel(status)}><textarea rows={2} value={draft.reason ?? row.reason ?? ""}
          onChange={e => edit("reason", e.target.value)}/></IdeaField>
        <EditableChecks checks={checks} onChange={editCheck}/>
      </fieldset>
      <div className="idea-toolbar">
        <Button label={c.save} type="submit" variant="secondary" size="sm" isDisabled={busy || !name.trim()}/>
        <Button label={c.cancelEdit} variant="ghost" size="sm" isDisabled={busy}
          onClick={() => {setDraft({}); setEditing(null); setFieldsMessage("")}}/>
      </div>
    </form>}
    {fieldsMessage && <p role="status">{fieldsMessage}</p>}
    <section className="idea-section" aria-labelledby="idea-log-heading">
      <Heading level={3} id="idea-log-heading">{c.log}</Heading>
      <form className="idea-section" onSubmit={e => { e.preventDefault(); void submitLog() }}>
        <div className="idea-field"><textarea aria-label={c.log} rows={3} value={text} maxLength={8000}
          placeholder={c.logHint} onChange={e => setText(e.target.value)}/></div>
        <div className="idea-section-heading">
          <input type="file" ref={input} aria-label={c.chooseFile} hidden onChange={e => setFile(e.target.files?.[0])}/>
          <Button label={file?.name || c.chooseFile} variant="ghost" size="sm" icon={<PaperClipIcon width={16}/>} onClick={() => input.current?.click()}/>
          <Button label={c.addLog} type="submit" variant="primary" size="sm" isDisabled={busy || (!text.trim() && !file)}/>
        </div>
      </form>
      {logMessage && <p role="status">{logMessage}</p>}
      {logFailed && <div className="idea-inline" role="alert">
        <p>{c.detailError}</p>
        <Button label={c.retry} variant="secondary" size="sm" onClick={() => {
          setLogFailed(false)
          setLogRetry(previous => previous + 1)
        }}/>
      </div>}
      {!logs && !logFailed && <Spinner aria-label={c.loading}/>}
      {logs?.length === 0 && <p className="idea-muted">{c.emptyLog}</p>}
      <ol className="idea-log-list">{logs?.map(log => <li key={log.id}>
        <time dateTime={log.at}>{new Date(log.at).toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" })}</time>
        {log.text && <p>{log.id.startsWith("edit-") ? formatWorkText(log.text) : log.text}</p>}
        {log.filename && <a href={"/api/ideas"+base+"/"+encodeURIComponent(log.id)+"/file"} download><PaperClipIcon width={14}/>{log.filename}</a>}
      </li>)}</ol>
    </section>
  </dialog>
}
