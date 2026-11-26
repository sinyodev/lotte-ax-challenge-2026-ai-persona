import { Fragment, useState } from "react"
import { Button } from "@astryxdesign/core/Button"
import { Badge } from "@astryxdesign/core/Badge"
import { Heading } from "@astryxdesign/core/Heading"
import { Link } from "react-router"
import { ArrowDownIcon, ArrowUpIcon, ArrowsUpDownIcon, ChevronDownIcon, PaperClipIcon } from "@heroicons/react/20/solid"
import { ideaStatuses, type IdeaPatch, type IdeaRow, type IdeaStatus } from "../../chat/contract-ideas"
import { ideasCopy as c } from "../../copy/ideas"
import { formatDate, formatWorkText, ideaDetailLinkState, IdeaField, StatusOptions, type IdeaDetailHref } from "./IdeaFields"
import { IdeaOwnerMenu, type OwnerOrder } from "./IdeaOwnerMenu"

const archivedStatuses: IdeaStatus[] = ["출시", "보류", "폐기", "단종"]

function compareWorkDate(a: IdeaRow, b: IdeaRow, newestFirst: boolean) {
  const first = Date.parse(a.work_date ?? "")
  const second = Date.parse(b.work_date ?? "")
  if (!Number.isFinite(first)) return Number.isFinite(second) ? 1 : 0
  if (!Number.isFinite(second)) return -1
  return newestFirst ? second - first : first - second
}

const ownerNames = new Intl.Collator("ko", { numeric: true })

function compareOwner(a: IdeaRow, b: IdeaRow, order: OwnerOrder) {
  if (!a.owner) return b.owner ? 1 : compareWorkDate(a, b, true)
  if (!b.owner) return -1
  const compared = ownerNames.compare(a.owner, b.owner)
  return (order === "ownerAsc" ? compared : -compared) || compareWorkDate(a, b, true)
}

function BoardRow({ row, detailHref, changeStage }: {
  row: IdeaRow; detailHref: IdeaDetailHref; changeStage: (id: string, status: IdeaStatus) => Promise<void>
}) {
  const [saving, setSaving] = useState(false)

  async function update(status: IdeaStatus) {
    setSaving(true)
    try {
      await changeStage(row.id, status)
    } finally {
      setSaving(false)
    }
  }

  const href = detailHref(row.id)
  return <tr role="row">
    <td role="cell" className="idea-cell-name">
      <Link className="idea-rowname" to={href} state={ideaDetailLinkState}>
        {row.name}
      </Link>
    </td>
    <td role="cell" className="idea-cell-owner">
      <span className="idea-mobile-label" aria-hidden="true">{c.fields.owner}</span>
      <span className={row.owner ? undefined : "idea-owner-unassigned"}>{row.owner || c.noOwner}</span>
    </td>
    <td role="cell" className="idea-cell-stage">
      <span className="idea-mobile-label" aria-hidden="true">{c.fields.status}</span>
      <select className="idea-stage-select" value={row.status} disabled={saving}
        aria-label={row.name + " " + c.fields.status}
        onChange={event => void update(event.target.value as IdeaStatus)}><StatusOptions/></select>
    </td>
    <td role="cell" className="idea-cell-work">
      <span className="idea-mobile-label" aria-hidden="true">{c.fields.last_work}</span>
      <span className="idea-work-text">{row.last_work ? formatWorkText(row.last_work) : c.blank}</span>
    </td>
    <td role="cell" className="idea-cell-date">
      <span className="idea-mobile-label" aria-hidden="true">{c.fields.work_date}</span>
      {row.work_date ? <time dateTime={row.work_date}>{formatDate(row.work_date)}</time> : c.blank}
    </td>
    <td role="cell" className="idea-cell-files">
      <span className="idea-mobile-label" aria-hidden="true">{c.file}</span>
      {row.attachment_count > 0 ? <Link className="idea-files" to={href} state={ideaDetailLinkState}
        aria-label={row.name + " " + c.file + " " + c.results(row.attachment_count)}>
        <PaperClipIcon width={14} aria-hidden="true"/>{row.attachment_count}
      </Link> : c.blank}
    </td>
  </tr>
}

export function IdeasBoard({ items, openedStatus, detailHref, save, add }: {
  items: IdeaRow[] | undefined
  openedStatus: IdeaStatus | undefined
  detailHref: IdeaDetailHref
  save: (id: string, patch: IdeaPatch) => Promise<void>
  add: () => void
}) {
  const [search, setSearch] = useState("")
  const [status, setStatus] = useState("")
  const [owner, setOwner] = useState("all")
  const [order, setOrder] = useState<OwnerOrder | "newest" | "oldest">("newest")
  const [groupState, setGroupState] = useState<Partial<Record<IdeaStatus, boolean>>>({})
  const [message, setMessage] = useState("")
  const term = search.trim().toLocaleLowerCase("ko-KR")
  const owners = Array.from(new Set(items?.flatMap(row => row.owner ? [row.owner] : []))).sort(ownerNames.compare)
  const ownerOrder = order === "ownerAsc" || order === "ownerDesc" ? order : undefined
  const nextDateOrder = order === "newest" ? "oldest" : "newest"
  const DateIcon = ownerOrder ? ArrowsUpDownIcon : order === "newest" ? ArrowDownIcon : ArrowUpIcon
  const filtered = items?.filter(row =>
    (!status || row.status === status) &&
    (owner === "all" || (row.owner ? "owner:" + row.owner : "unassigned") === owner) &&
    [row.name, row.brand, row.owner, row.category, row.concept, row.last_work, row.reason]
      .some(value => value?.toLocaleLowerCase("ko-KR").includes(term)))
    .sort((a, b) => ownerOrder ? compareOwner(a, b, ownerOrder) : compareWorkDate(a, b, order === "newest"))

  async function changeStage(id: string, nextStatus: IdeaStatus) {
    setMessage("")
    try {
      await save(id, { status: nextStatus })
      setGroupState(groups => ({ ...groups, [nextStatus]: true }))
    } catch {
      setMessage(c.saveError)
    }
  }

  function renderRow(row: IdeaRow) {
    return <BoardRow key={row.id} row={row} detailHref={detailHref} changeStage={changeStage}/>
  }

  return <section className="idea-section" aria-label={c.boardTab}>
    <div className="idea-board-filters">
      <IdeaField label={c.search}>
        <input type="search" placeholder={c.searchHint} value={search} onChange={event => {
          setSearch(event.target.value)
          setGroupState({})
        }} />
      </IdeaField>
      <IdeaField label={c.fields.status}>
        <select value={status} onChange={event => {
          setStatus(event.target.value)
          setGroupState({})
        }}><option value="">{c.statusAny}</option><StatusOptions/></select>
      </IdeaField>
    </div>
    {message && <p role="alert">{message}</p>}
    {items && <div className="idea-collection">
      <table className="idea-sheet" aria-label={c.boardTab} role="table">
        <thead role="rowgroup"><tr role="row">
          <th scope="col" role="columnheader" className="idea-cell-name">{c.fields.name}</th>
          <th scope="col" role="columnheader" className="idea-cell-owner"
            aria-sort={ownerOrder && (ownerOrder === "ownerAsc" ? "ascending" : "descending")}>
            <IdeaOwnerMenu owners={owners} filter={owner} order={ownerOrder} onOrder={setOrder}
              onFilter={value => { setOwner(value); setGroupState({}) }}/>
          </th>
          <th scope="col" role="columnheader" className="idea-cell-stage">{c.fields.status}</th>
          <th scope="col" role="columnheader" className="idea-cell-work">{c.fields.last_work}</th>
          <th scope="col" role="columnheader" className="idea-cell-date"
            aria-sort={ownerOrder ? undefined : order === "newest" ? "descending" : "ascending"}>
            <button type="button" className="idea-date-sort" onClick={() => setOrder(nextDateOrder)}
              aria-label={c.sortWorkDate(nextDateOrder === "newest" ? c.newestFirst : c.oldestFirst)}>
              {c.fields.work_date}<DateIcon width={14} aria-hidden="true"/>
            </button>
          </th>
          <th scope="col" role="columnheader" className="idea-cell-files">{c.file}</th>
        </tr></thead>
        {!filtered?.length ? <tbody><tr><td className="idea-empty-cell" colSpan={6}>
          <p role="status">{items.length ? c.noMatches : c.emptyBoard}</p>
          {!items.length && <Button label={c.add} variant="secondary" onClick={add}/>}
        </td></tr></tbody> : ownerOrder ? <tbody role="rowgroup">{filtered.map(renderRow)}</tbody> :
          ideaStatuses.map((group, index) => {
            const rows = filtered.filter(row => row.status === group)
            if (!rows.length) return null
            const label = c.statuses[group]
            const groupId = `idea-group-${index}`
            const open = groupState[group] ?? (Boolean(term || status || owner !== "all") || group === openedStatus || !archivedStatuses.includes(group))
            return <Fragment key={group}>
              <tbody className="idea-group-heading"><tr><td colSpan={6}>
                <Heading level={2}>
                  <button type="button" className="idea-group-toggle" aria-expanded={open} aria-controls={groupId}
                    onClick={() => setGroupState(groups => ({ ...groups, [group]: !open }))}>
                    <ChevronDownIcon width={16} aria-hidden="true"/>{label}<Badge variant="neutral" label={c.results(rows.length)}/>
                  </button>
                </Heading>
              </td></tr></tbody>
              <tbody className="idea-group-rows" role="rowgroup" aria-label={label} id={groupId} hidden={!open}>{open && rows.map(renderRow)}</tbody>
            </Fragment>
          })}
      </table>
    </div>}
  </section>
}
