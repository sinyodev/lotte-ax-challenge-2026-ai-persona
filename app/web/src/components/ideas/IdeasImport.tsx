import { useState } from "react"
import { Button } from "@astryxdesign/core/Button"
import { Heading } from "@astryxdesign/core/Heading"
import { Text } from "@astryxdesign/core/Text"
import { ideaRequest, type IdeaImportPreview, type IdeaRow } from "../../chat/contract-ideas"
import { ideasCopy as c } from "../../copy/ideas"
import { EditableChecks, IdeaField, StatusOptions } from "./IdeaFields"

const fields = ["name", "brand", "category", "pack", "price", "owner", "verdict", "trend", "started", "updated"] as const

type Draft = IdeaImportPreview["items"][number] & { included: boolean }

function fileBody(file: File): Promise<{ filename: string; content_base64: string }> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = reject
    reader.onload = () => {
      if (typeof reader.result !== "string") return reject()
      resolve({ filename: file.name, content_base64: reader.result.slice(reader.result.indexOf(",") + 1) })
    }
    reader.readAsDataURL(file)
  })
}

function ImportRecord({ draft, onChange }: { draft: Draft; onChange: (next: Draft) => void }) {
  const { row, missing, duplicates, included } = draft
  const changeRow = (patch: Partial<IdeaRow>) => onChange({ ...draft, row: { ...row, ...patch } })
  return (
    <section className="idea-import-record">
      <label className="idea-include">
        <input type="checkbox" checked={included} onChange={(event) => onChange({ ...draft, included: event.target.checked })} />
        <Text weight="medium">{c.include}</Text>
        <Text>{row.name}</Text>
      </label>
      {missing.length > 0 && <Text as="p" type="supporting">
        {c.missing} · {missing.map((key) => c.fields[key as keyof typeof c.fields] ?? key).join(", ")}
      </Text>}
      {duplicates.length > 0 && <div>
        <Text type="supporting" weight="medium">{c.duplicates}</Text>
        <ul className="idea-import-notes">{duplicates.map((duplicate) => <li key={duplicate.id}>{duplicate.name}</li>)}</ul>
      </div>}
      <fieldset className="idea-edit-fields" disabled={!included}>
        {fields.map((key) => <IdeaField key={key} label={c.fields[key]}>
          <input value={row[key] ?? ""} required={key === "name"} maxLength={key === "name" ? 300 : undefined}
            onChange={(event) => changeRow({ [key]: event.target.value })} />
        </IdeaField>)}
        <IdeaField label={c.fields.status}>
          <select value={row.status} onChange={(event) => changeRow({ status: event.target.value as IdeaRow["status"] })}>
            <StatusOptions />
          </select>
        </IdeaField>
        {(row.status === "출시" || row.status === "단종") && <IdeaField label={c.fields.launched_on}>
          <input type="date" value={row.launched_on ?? ""} onChange={(event) => changeRow({ launched_on: event.target.value || null })} />
        </IdeaField>}
        <IdeaField label={c.fields.concept}>
          <textarea rows={2} value={row.concept ?? ""} onChange={(event) => changeRow({ concept: event.target.value })} />
        </IdeaField>
        <IdeaField label={c.fields.reason}>
          <textarea rows={2} value={row.reason ?? ""} onChange={(event) => changeRow({ reason: event.target.value })} />
        </IdeaField>
        <EditableChecks checks={row.checks} onChange={(checks) => changeRow({ checks })} />
      </fieldset>
    </section>
  )
}

export function IdeasImport({ onClose, onCommit }: {
  onClose: () => void
  onCommit: (rows: IdeaRow[]) => void
}) {
  const [method, setMethod] = useState<"text" | "file">("text")
  const [text, setText] = useState("")
  const [file, setFile] = useState<File>()
  const [guide, setGuide] = useState("")
  const [drafts, setDrafts] = useState<Draft[] | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])
  const [pending, setPending] = useState(false)
  const [feedback, setFeedback] = useState("")

  const copyGuide = async () => {
    setPending(true)
    setFeedback("")
    try {
      const { prompt } = await ideaRequest<{ prompt: string }>("/import/prompt")
      try {
        await navigator.clipboard.writeText(prompt)
        setFeedback(c.copyReady)
      } catch {
        setGuide(prompt)
        setFeedback(c.copyFallback)
      }
    } catch {
      setFeedback(c.copyError)
    } finally {
      setPending(false)
    }
  }
  const preview = async () => {
    if (method === "file" && !file) return
    setPending(true)
    setFeedback("")
    try {
      const body = method === "file" && file ? await fileBody(file) : { text: text.trim() }
      const result = await ideaRequest<IdeaImportPreview>("/import/preview", { method: "POST", body })
      setDrafts(result.items.map((item) => ({ ...item, included: item.duplicates.length === 0 })))
      setWarnings(result.warnings)
    } catch (error) {
      setFeedback(error instanceof Error && error.message ? error.message : c.previewError)
    } finally {
      setPending(false)
    }
  }
  const approve = async () => {
    const items = drafts?.filter((item) => item.included).map(({ row }) => row) ?? []
    if (!items.length) return
    setPending(true)
    setFeedback("")
    try {
      const result = await ideaRequest<{ items: IdeaRow[] }>("/import/commit", { method: "POST", body: { items } })
      onCommit(result.items)
    } catch (error) {
      setFeedback(error instanceof Error && error.message ? error.message : c.importError)
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="idea-section idea-import" aria-labelledby="idea-import-title">
      <div className="idea-section-heading">
        <Heading level={2} id="idea-import-title">{c.import}</Heading>
        <Button variant="secondary" size="sm" label={c.close} onClick={onClose} isDisabled={pending} />
      </div>
      {feedback && <Text as="p" role="status">{feedback}</Text>}
      {drafts === null ? (
        <form onSubmit={(event) => { event.preventDefault(); void preview() }}>
          <div className="idea-toolbar">
            <Button size="sm" label={c.importText} variant={method === "text" ? "secondary" : "ghost"}
              aria-pressed={method === "text"} onClick={() => setMethod("text")} isDisabled={pending} />
            <Button size="sm" label={c.importFile} variant={method === "file" ? "secondary" : "ghost"}
              aria-pressed={method === "file"} onClick={() => setMethod("file")} isDisabled={pending} />
            <Button size="sm" label={c.copyInstructions} variant="secondary" onClick={() => void copyGuide()} isDisabled={pending} />
          </div>
          {guide && <IdeaField label={c.copyInstructions}><textarea readOnly rows={5} value={guide} /></IdeaField>}
          {method === "text" ? (
            <IdeaField label={c.importText}>
              <textarea value={text} rows={6} onChange={(event) => setText(event.target.value)} disabled={pending} />
            </IdeaField>
          ) : (
            <IdeaField label={c.importFile}>
              <input type="file" accept=".xlsx,.docx,.pptx" onChange={(event) => setFile(event.target.files?.[0])} disabled={pending} />
              <Text type="supporting">{c.fileFormats}</Text>
            </IdeaField>
          )}
          <Button label={c.preview} type="submit" variant="primary" isLoading={pending}
            isDisabled={pending || (method === "text" ? !text.trim() : !file)} />
        </form>
      ) : (
        <form onSubmit={(event) => { event.preventDefault(); void approve() }}>
          <Heading level={3}>{drafts.length ? c.review : c.nothingToImport}</Heading>
          {warnings.length > 0 && <ul className="idea-import-notes">{warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul>}
          <fieldset className="idea-import-drafts" disabled={pending}>
            {drafts.map((draft, i) => <ImportRecord key={i} draft={draft}
              onChange={(next) => setDrafts((current) => current?.map((item, index) => index === i ? next : item) ?? null)} />)}
          </fieldset>
          <div className="idea-toolbar">
            <Button label={c.approve} type="submit" variant="primary" isLoading={pending}
              isDisabled={pending || !drafts.some((item) => item.included && item.row.name.trim())} />
            <Button label={c.back} variant="secondary" isDisabled={pending}
              onClick={() => { setDrafts(null); setWarnings([]); setFeedback(""); setFile(undefined) }} />
          </div>
        </form>
      )}
    </section>
  )
}
