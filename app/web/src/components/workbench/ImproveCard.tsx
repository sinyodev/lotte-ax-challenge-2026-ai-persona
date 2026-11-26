import { useEffect, useState } from "react"
import { Button } from "@astryxdesign/core/Button"
import { DropdownMenu, DropdownMenuRadioGroup, DropdownMenuRadioItem } from "@astryxdesign/core/DropdownMenu"
import { Heading } from "@astryxdesign/core/Heading"
import { TextArea } from "@astryxdesign/core/TextArea"
import { Text } from "@astryxdesign/core/Text"
import { VStack } from "@astryxdesign/core/VStack"
import type { RunResult, RunView } from "../../chat/contract"
import type { ImproveItem, ImproveKind, ImprovePaired, ImprovePayload } from "../../chat/contract-improve"
import { EARLY_RESULT_AT, RUN_POLL_MS } from "../../chat/runs"
import { improveCardCopy as t } from "../../copy/improve"
import { ImprovePairedResult, ImproveRunSummary } from "./ImproveResults"
import { ImprovePrices } from "./ImprovePrices"
import { AUTO_REPLY_TO, type CardSay } from "./ShelfCards"
import "./ImproveCard.css"


type RunRecord =
  | { state: "loaded"; view: RunView }
  | { state: "missing" | "unavailable"; view?: undefined }

function useRuns(ids: string[], samples?: Record<string, RunView>) {
  const [records, setRecords] = useState<Record<string, RunRecord>>({})
  const key = [...new Set(ids.filter(Boolean))].sort().join(",")
  useEffect(() => {
    if (!key || samples) return
    const controller = new AbortController()
    let timer: number | undefined
    const read = async (pending: string[]) => {
      const readOne = async (id: string): Promise<[string, RunRecord]> => {
        try {
          const response = await fetch(`/api/runs/${encodeURIComponent(id)}`, { signal: controller.signal })
          if (response.status === 404) return [id, { state: "missing" }]
          if (response.ok) return [id, { state: "loaded", view: await response.json() as RunView }]
        } catch {
          // 응답을 받지 못했으면 잠시 뒤 다시 확인한다.
        }
        return [id, { state: "unavailable" }]
      }
      const received = await Promise.all(pending.map(readOne))
      if (controller.signal.aborted) return
      setRecords((prev) => ({ ...prev, ...Object.fromEntries(received) }))
      const next = received
        .filter(([, run]) => run.state === "unavailable" || run.view?.status === "running")
        .map(([id]) => id)
      if (next.length) timer = window.setTimeout(() => void read(next), RUN_POLL_MS)
    }
    void read(key.split(","))
    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [key, samples])
  if (!samples) return records
  return Object.fromEntries(key ? key.split(",").map((id) => {
    const view = samples[id]
    const record: RunRecord = view ? { state: "loaded", view } : { state: "missing" }
    return [id, record]
  }) : [])
}

function isReady(view: RunView | undefined): view is RunView & { result: RunResult } {
  return Boolean(view?.result?.n) && !!view && view.status !== "failed" &&
    (view.status !== "running" || view.asked >= Math.min(EARLY_RESULT_AT, view.total))
}

const KINDS = Object.keys(t.changePrefixes) as ImproveKind[]

function kindOf(item: ImproveItem): ImproveKind {
  if (item.kind && item.kind in t.kindNames) return item.kind
  return KINDS.find((kind) => item.change.startsWith(t.changePrefixes[kind])) ?? "promo"
}

/** 같은 종류가 둘이면 뒤의 것에 숫자를 붙인다. 서버 improve.plan_name과 맞춘다. */
export function planName(items: ImproveItem[], item: ImproveItem | null): string {
  if (!item) return t.baseName
  const kind = kindOf(item)
  const same = items.filter((candidate) => kindOf(candidate) === kind)
  const index = same.findIndex((candidate) => candidate.id === item.id)
  return index > 0 ? t.numbered(t.kindNames[kind], index + 1) : t.kindNames[kind]
}

function planLabel(item: ImproveItem) {
  const kind = t.kindNames[kindOf(item)].replace(/ 변경안$/, "")
  return item.after ? t.candidate(kind, item.after) : item.change
}

function EditCandidate({ item, baseId, say, close }: { item: ImproveItem; baseId: string; say: CardSay; close: () => void }) {
  const current = Object.fromEntries(Object.entries(item.edit_values ?? {}).map(([key, value]) => [key, String(value)]))
  const [draft, setDraft] = useState(current)
  const entries = Object.entries(draft)
  const canApply = entries.every(([, value]) => value.trim()) && entries.some(([key, value]) => current[key] !== value.trim())
  function apply() {
    if (!say || say.isDisabled || !canApply) return
    const summary = entries.map(([key, value]) => `${t.fields[key]} ${value.trim()}`).join(", ")
    say.onSay(t.editSay(summary), { to: `edit-candidate:${baseId}`, ids: [item.id, JSON.stringify(draft)] })
    close()
  }
  return <VStack gap={2}>
    {entries.map(([key, value]) => <TextArea key={key} label={t.fields[key]} value={value}
      rows={1} onChange={next => setDraft({ ...draft, [key]: next })} />)}
    <div className="improve-actions">
      <Button label={t.applyEdit} isDisabled={!canApply || !say || say.isDisabled} onClick={apply} />
      <Button variant="ghost" label={t.cancelEdit} onClick={close} />
    </div>
  </VStack>
}

function CandidateTable({ item, paired, baseId, say }: {
  item: ImproveItem; paired?: ImprovePaired; baseId: string; say: CardSay
}) {
  const [editing, setEditing] = useState(false)
  const field = t.kindNames[kindOf(item)].replace(/ 변경안$/, "")
  const edit = !editing && say && item.edit_values && <div className="improve-edit-action">
    <Button size="sm" variant="ghost" label={t.edit} isDisabled={say.isDisabled} onClick={() => setEditing(true)} />
  </div>
  return <table className="improve-table" aria-label={t.tableTitle}>
    <colgroup><col className="improve-field-col" /><col /><col /></colgroup>
    <thead><tr>
      <th scope="col"><Text type="label">{t.condition}</Text></th>
      <th scope="col"><Text type="label">{t.original}</Text></th>
      <th scope="col"><Text type="label" weight="semibold">{t.changed}</Text></th>
    </tr></thead>
    <tbody>
      <tr>
        <th scope="row"><Text>{field}</Text></th>
        {item.before && item.after ? <>
          <td><Text type="large">{item.before}</Text></td>
          <td><Text type="large" weight="semibold">{item.after}</Text>{edit}</td>
        </> : <td colSpan={2}><Text>{item.change}</Text>{edit}</td>}
      </tr>
      {editing && <tr><td colSpan={3}><EditCandidate item={item} baseId={baseId} say={say} close={() => setEditing(false)} /></td></tr>}
      {paired && <tr>
        <th scope="row"><Text>{t.picked}</Text></th>
        {[[paired.both + paired.lost, paired.original_rate], [paired.both + paired.gained, paired.changed_rate]].map(([picked, rate], idx) =>
          <td key={idx}><div className="improve-table-rate">
            <Text type="large" weight="semibold" hasTabularNumbers>{t.percent(rate)}</Text>
            <Text hasTabularNumbers>{t.tally(picked, paired.n)}</Text>
            <div className="improve-rate-track" aria-hidden="true"><span style={{ width: `${rate}%` }} /></div>
          </div></td>)}
      </tr>}
    </tbody>
  </table>
}

function ProposalEvidence({ item }: { item: ImproveItem }) {
  const evidence = item.evidence ?? []
  if (!evidence.length && !item.reason && !item.hypothesis) return null
  return (
    <details className="improve-sales improve-evidence-details">
      <summary>{t.evidenceDetails}</summary>
      {item.hypothesis && <Text as="p">{item.hypothesis}</Text>}
      {evidence.length ? (
        <ul className="improve-evidence">
          {evidence.map((entry, index) => {
            const isQuote = Boolean(entry.quote_id || entry.session_id)
            const origin = (Object.hasOwn(t.origins, entry.origin) ? t.origins[entry.origin] : entry.origin) || t.quote
            return (
              <li key={`${entry.session_id ?? ""}:${entry.quote_id ?? ""}:${index}`}>
                {isQuote ? (
                  <figure className="improve-quote">
                    <figcaption>
                      <Text weight="semibold">{origin}</Text>
                      <Text color="primary" type="supporting">{t.quoteRef(entry.session_id, entry.quote_id)}</Text>
                    </figcaption>
                    <blockquote><Text as="p">{entry.text}</Text></blockquote>
                  </figure>
                ) : (
                  <div className="improve-evidence-entry">
                    <Text weight="semibold">{origin}</Text>
                    <Text as="p">{entry.text}</Text>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      ) : <Text as="p">{item.reason}</Text>}
    </details>
  )
}

function RunState({ record }: { record?: RunRecord }) {
  let message = t.waiting
  const view = record?.view
  if (record?.state === "unavailable") message = t.runUnavailable
  if (record?.state === "missing") message = t.runMissing
  if (view?.status === "failed") message = t.failed
  if (view?.status === "stopped") message = t.stopped
  if (view?.status === "done") message = t.noResult
  return <div role="status"><Text>{message}</Text></div>
}

/** 새 카드의 완료된 비교를 세션에서 다시 열어도 실행마다 한 번만 요청한다. */
const requestedComparisons = new Set<string>()

export function ImproveBody({ payload, say, samples }: {
  payload: ImprovePayload
  say: CardSay
  samples?: Record<string, RunView>
}) {
  const { base_run: baseId, items, price_curve: priceCurve, adopted_item_id: adoptedId, focus_id: focusId } = payload
  const [previewId, setPreviewId] = useState<string>()
  const selectedId = samples || !say ? previewId ?? focusId : focusId
  const selected = items.find(item => item.id === selectedId) ?? items.find(item => item.id === adoptedId) ?? items[0]
  function choose(id: string) {
    if (id === selected?.id) return
    if (samples || !say) {
      setPreviewId(id)
      return
    }
    const item = items.find(it => it.id === id)
    if (item && !say.isDisabled) say.onSay(t.focusSay(planLabel(item)), { to: `compare-candidate:${baseId}`, ids: [id] })
  }
  const runIds = items.flatMap((item) => item.run_id ? [item.run_id] : [])
  const priceIds = priceCurve?.flatMap((point) => point.run_id && point.run_id !== baseId ? [point.run_id] : []) ?? []
  const runKey = [...new Set([...runIds, ...priceIds])].sort().join(",")
  const records = useRuns([baseId, ...runIds, ...priceIds], samples)
  const baseRecord = records[baseId]
  const base = baseRecord?.view
  const baseReady = isReady(base)
  const selectedRun = selected?.run_id ? records[selected.run_id] : undefined
  const canSay = !!say && !say.isDisabled
  // 도는 변경안 테스트를 멈추고 그때까지의 답으로 결과를 본다(매대 테스트의 "멈추고 결과 보기"와 같은 길)
  const runningIds = [...new Set([...runIds, ...priceIds])].filter((id) => records[id]?.view?.status === "running")
  const stopAndSee = async () => {
    await Promise.all(runningIds.map((id) => fetch(`/api/runs/${encodeURIComponent(id)}/stop`, { method: "POST" }).catch(() => null)))
    if (say && !say.isDisabled) say.onSay(t.compare, { to: AUTO_REPLY_TO, ids: [] })
  }
  const extended = adoptedId !== undefined || !!priceCurve || items.some((item) => item.hypothesis || item.evidence?.length || item.paired)
  useEffect(() => {
    if (samples || !say || !canSay || !extended || !selected?.run_id || !runKey || records[baseId]?.view?.status !== "done") return
    const ids = runKey.split(",")
    const settled = ids.every((id) => records[id]?.state === "missing" || (
      records[id]?.view && records[id].view?.status !== "running"
    ))
    if (!settled) return
    const missing = items.flatMap((item) => item.run_id && (!item.paired || (!priceCurve?.length && item.kind === "price")) ? [item.run_id] : [])
    for (const point of priceCurve ?? []) {
      if (point.rate == null && point.run_id && isReady(records[point.run_id]?.view)) missing.push(point.run_id)
    }
    const pending = missing.filter((id) => records[id]?.view?.status === "done")
      .map((id) => JSON.stringify([baseId, id]))
    if (pending.every((key) => requestedComparisons.has(key))) return
    for (const key of pending) requestedComparisons.add(key)
    say.onSay(t.compare, { to: AUTO_REPLY_TO, ids: [] })
  }, [baseId, canSay, extended, items, priceCurve, records, runKey, samples, say, selected?.run_id])

  const paired = selected?.paired
  const selectedView = selectedRun?.view
  const selectedReady = isReady(selectedView)
  const hasPairs = !!paired && paired.n > 0
  const partial = [selectedView?.status, base?.status].some((status) => status === "running" || status === "stopped")
  const canAdopt = hasPairs && !!baseId && (!selectedView || selectedView.status === "done") && !partial
  const name = planName(items, selected ?? null)
  return (
    <div className="improve-card">
      <VStack gap={5}>
        <div className="improve-toolbar">
          <div className="improve-context">
            <Heading level={3}>{base?.concept.name ?? t.tableTitle}</Heading>
            {base?.who.label && <Text>{base.who.label}</Text>}
          </div>
          {selected && items.length > 1 && (
            <DropdownMenu button={{ label: t.switchCandidate, size: "sm", isDisabled: !!say?.isDisabled }}
              menuWidth="min(20rem, calc(100vw - 3rem))">
              <DropdownMenuRadioGroup label={t.select} value={selected.id} onChange={choose}>
                {items.map(item => <DropdownMenuRadioItem key={item.id} value={item.id} label={planLabel(item)} />)}
              </DropdownMenuRadioGroup>
            </DropdownMenu>
          )}
        </div>
        {selected ? (
          <>
            <CandidateTable key={baseId + selected.id} item={selected} paired={hasPairs ? paired : undefined} baseId={baseId} say={say} />
            {selectedView && !hasPairs && (selectedView.status === "running" || selectedReady) && (
              <ImproveRunSummary base={base} changed={selectedView} noPairs={paired?.n === 0} />
            )}
            {runningIds.length > 0 && canSay && !samples && (
              <div><Button label={t.stopAndSee} variant="ghost" onClick={() => void stopAndSee()} /></div>
            )}
            {!hasPairs && baseId && !baseReady && baseRecord?.state === "missing" && <RunState record={baseRecord} />}
            {selected.run_id && !hasPairs && selectedView?.status !== "running" &&
              (!selectedReady || selectedView?.status === "stopped") && <RunState record={selectedRun} />}
            {hasPairs && <ImprovePairedResult paired={paired} partial={partial} />}
          </>
        ) : <Text as="p">{t.noItems}</Text>}
        {selected && kindOf(selected) === "price" && priceCurve?.some(point => point.run_id && point.run_id !== baseId) ? (
          <ImprovePrices points={priceCurve} baseId={baseId} basePrice={base?.concept.price}
            runStatus={(id) => records[id]?.state === "missing" ? "missing" : records[id]?.view?.status} />
        ) : null}
        {selected && <ProposalEvidence key={baseId + selected.id} item={selected} />}
        {selected && (selected.id === adoptedId || (canAdopt && !adoptedId)) && (
          <div className="improve-actions">
            <Button label={selected.id === adoptedId ? t.adopted : t.adopt} variant={paired?.verdict === "more" ? "primary" : "secondary"} size="lg"
              isDisabled={!canSay || Boolean(adoptedId)}
              onClick={() => say?.onSay(t.adoptSay(name), { to: "w7-adopt", ids: [baseId, selected.id] })} />
          </div>
        )}

      </VStack>
    </div>
  )
}
