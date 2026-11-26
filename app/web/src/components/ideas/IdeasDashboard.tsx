import { useState } from "react"
import { Heading } from "@astryxdesign/core/Heading"
import { InfoTip } from "@astryxdesign/core/InfoTip"
import { ChevronRightIcon } from "@heroicons/react/20/solid"
import { Link } from "react-router"
import type { IdeaLaunch, IdeasDashboard as Dashboard } from "../../chat/contract-ideas"
import { ideasCopy as c } from "../../copy/ideas"
import { formatDate, ideaDetailLinkState, IdeaField, type IdeaDetailHref } from "./IdeaFields"

const months = Array.from({ length: 12 }, (_, i) => i + 1)
const seoulCalendar = new Intl.DateTimeFormat("en", { timeZone: "Asia/Seoul", year: "numeric", month: "numeric" })
const launchDate = /^\d{4}-(0[1-9]|1[0-2])-\d{2}$/

export function IdeasDashboard({ data, detailHref }: { data: Dashboard; detailHref: IdeaDetailHref }) {
  const today = seoulCalendar.formatToParts(new Date())
  const currentYear = Number(today.find(part => part.type === "year")?.value)
  const currentMonth = Number(today.find(part => part.type === "month")?.value)
  const [selectedYear, setSelectedYear] = useState(currentYear)
  const [selectedMonth, setSelectedMonth] = useState<number>()
  const launches = (data.launches ?? []).filter(row => launchDate.test(row.launched_on))
  const years = [...new Set([currentYear, ...launches.map(launch => Number(launch.launched_on.slice(0, 4)))])]
    .sort((a, b) => b - a)
  const year = years.includes(selectedYear) ? selectedYear : currentYear
  const byMonth: IdeaLaunch[][] = months.map(() => [])
  for (const row of launches) {
    if (Number(row.launched_on.slice(0, 4)) !== year) continue
    byMonth[Number(row.launched_on.slice(5, 7)) - 1].push(row)
  }
  const total = byMonth.reduce((count, rows) => count + rows.length, 0)
  const max = Math.max(1, ...byMonth.map(rows => rows.length))
  const latestMonth = byMonth.reduce((latest, rows, index) => rows.length > 0 ? index + 1 : latest, 0)
  const month = (year === selectedYear ? selectedMonth : undefined) ?? (latestMonth || (year === currentYear ? currentMonth : 1))
  const products = byMonth[month - 1].slice().sort((a, b) => b.launched_on.localeCompare(a.launched_on) || a.name.localeCompare(b.name, "ko-KR"))

  return <section className="idea-launch-panel" aria-labelledby="idea-launch-title">
    <div className="idea-launch-header">
      <div className="idea-launch-kpi">
        <Heading level={2} id="idea-launch-title">{c.launchCount}</Heading>
        <div className="idea-launch-count">
          <p><strong>{total.toLocaleString("ko-KR")}</strong>{c.launchUnit}</p>
          <InfoTip label={c.launchCountHelp} content={c.launchCountBasis}/>
        </div>
      </div>
      <IdeaField label={c.yearFilter}>
        <select value={year} onChange={event => {
          setSelectedYear(Number(event.target.value))
          setSelectedMonth(undefined)
        }}>{years.map(item => <option value={item} key={item}>{c.year(item)}</option>)}</select>
      </IdeaField>
    </div>
    <div className="idea-launch-body">
      <section className="idea-chart-section" aria-labelledby="idea-chart-title">
        <Heading level={3} id="idea-chart-title">{c.launchChart}</Heading>
        <div className="idea-chart" role="group" aria-labelledby="idea-chart-title">
          {months.map(item => {
            const count = byMonth[item - 1].length
            return <button key={item} className="idea-month" type="button" aria-label={c.monthBar(item, count)}
              aria-pressed={item === month} aria-controls="idea-month-products" onClick={() => setSelectedMonth(item)}>
              <span className="idea-month-plot" aria-hidden="true">
                <span className="idea-month-bar" style={{ height: `${count / max * 100}%` }}>
                  <span className="idea-month-count">{count.toLocaleString("ko-KR")}</span>
                </span>
              </span>
              <span className="idea-month-label" aria-hidden="true">{c.month(item)}</span>
            </button>
          })}
        </div>
        {data.undated_launches > 0 && <p className="idea-muted">{c.undatedLaunches(data.undated_launches)}</p>}
      </section>
      <section className="idea-month-products" id="idea-month-products" aria-labelledby="idea-month-title">
        <div className="idea-section-heading" aria-live="polite">
          <Heading level={3} id="idea-month-title">{c.monthProducts(month)}</Heading>
          <span>{c.launchProducts(products.length)}</span>
        </div>
        {products.length > 0 ? <ul className="idea-launch-list">
          {products.map(row => <li key={row.row_id}>
            <Link to={detailHref(row.row_id)} state={ideaDetailLinkState} className="idea-list-link">
              <span>{row.name}</span>
              <time dateTime={row.launched_on}>{formatDate(row.launched_on)}</time>
              <ChevronRightIcon width={16} aria-hidden="true"/>
            </Link>
          </li>)}
        </ul> : <p className="idea-muted">{c.closedMonth}</p>}
      </section>
    </div>
  </section>
}
