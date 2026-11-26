/**
 * 결과 보고서의 종이들(지시서 32의 B). 첫 장(결재용) → 근거와 다음 실제 조사의 조건 → 부록. 종이마다 <article data-paper>.
 * 글은 서버가 보낸 보고서체 그대로, 칸의 이름만 copy/report.ts에 있다. 치수와 글씨는 pages/proposal.css.
 * 기획자 의견은 화면에서 고치면 PUT /api/chats/{id}/proposal/opinion으로 저장하고, 같은 창의 종이 자료(useProposal)에도 알린다.
 */
import { useEffect, useRef, useState, type ReactNode } from "react"
import { TextArea } from "@astryxdesign/core/TextArea"
import type { ResultReport } from "../../chat/contract-shelf"
import { copy } from "../../copy"
import { reportCopy as t } from "../../copy/report"
import { GroupPaper } from "./GroupPaper"

/** 같은 창의 종이 자료에 의견이 바뀐 것을 알리는 이벤트(Paper.tsx의 useProposal이 듣는다). */
export const OPINION_EVENT = "ax-report-opinion"
export type OpinionDetail = { chatId: string; conceptId: string; text: string }

const SAVE_MS = 700

function Section({ n, title, children }: { n?: number; title: string; children: ReactNode }) {
  return (
    <section data-paper-section>
      <h3 data-paper-h>{n ? t.numbered(n, title) : title}</h3>
      {children}
    </section>
  )
}

function Bullets({ items }: { items: ReactNode[] }) {
  return (
    <ul data-paper-bullets>
      {items.map((x, i) => (
        <li key={i}>{x}</li>
      ))}
    </ul>
  )
}

function Head({ title, dept, date }: { title: string; dept: string; date: string }) {
  return (
    <header data-paper-head>
      <h1 data-paper-kind>{title}</h1>
      <span data-paper-meta>{copy.proposal.meta(dept, copy.proposal.date(date))}</span>
    </header>
  )
}

function Opinion({ report, conceptId }: { report: ResultReport; conceptId: string }) {
  const [text, setText] = useState(report.opinion)
  const [state, setState] = useState<"idle" | "saved" | "failed">("idle")
  const timer = useRef<number | null>(null)
  const chatId = report.chat_id ?? ""
  useEffect(() => () => {
    if (timer.current) window.clearTimeout(timer.current)
  }, [])
  const save = (value: string) => {
    if (!chatId) return
    fetch(`/api/chats/${encodeURIComponent(chatId)}/proposal/opinion`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ concept_id: conceptId, text: value }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((body: { text: string }) => {
        setState("saved")
        window.dispatchEvent(
          new CustomEvent<OpinionDetail>(OPINION_EVENT, { detail: { chatId, conceptId, text: body.text } }),
        )
      })
      .catch(() => setState("failed"))
  }
  const onChange = (value: string) => {
    setText(value)
    setState("idle")
    if (timer.current) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => save(value), SAVE_MS)
  }
  return (
    <div data-paper-opinion>
      {chatId && (
        <div data-paper-opinion-edit>
          <TextArea
            label={t.opinion}
            isLabelHidden
            value={text}
            onChange={onChange}
            placeholder={t.opinionPlaceholder}
            rows={3}
            status={
              state === "saved"
                ? { type: "success", message: t.opinionSaved }
                : state === "failed"
                  ? { type: "error", message: t.opinionFailed }
                  : undefined
            }
          />
        </div>
      )}
      <div data-paper-opinion-print data-empty={text.trim() ? undefined : true}>
        {text.trim() ? text : null}
      </div>
    </div>
  )
}

/** 첫 장: 머리, 권고, 결정 요청, 핵심 수치, 한계, 기획자 의견, 아래 한 줄. 한 장에 들어가야 한다. */
function FirstSheet({ report, conceptId, dept, date }: { report: ResultReport; conceptId: string; dept: string; date: string }) {
  const r = report
  return (
    <article data-paper data-report-first>
      <Head title={r.head.title} dept={dept} date={date} />
      <div>
        <h2 data-paper-title>{r.head.product}</h2>
        {r.head.spec && <p data-paper-spec>{r.head.spec}</p>}
      </div>
      <div data-paper-gist data-paper-recommend={r.recommend.verdict}>
        <span data-paper-gist-label>{t.recommend}</span>
        <div data-paper-recommend-body>
          <p data-paper-recommend-text>{r.recommend.text}</p>
          <Bullets items={r.recommend.reasons} />
        </div>
      </div>
      <Section n={1} title={t.decisions}>
        <ol data-paper-decisions>
          {r.decisions.map((d, i) => (
            <li key={d}>
              <span data-paper-decision-n>{t.circled(i + 1)}</span> {d}
            </li>
          ))}
        </ol>
      </Section>
      <Section n={2} title={t.key}>
        <table data-paper-table data-paper-key>
          <thead>
            <tr>
              {r.key.map((k) => (
                <th key={k.key} scope="col">
                  {k.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              {r.key.map((k) => (
                <td key={k.key}>
                  <span data-paper-key-value>{k.value}</span>
                  {k.note && <span data-paper-key-note>{k.note}</span>}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </Section>
      <Section n={3} title={t.limits}>
        <Bullets items={r.limits} />
      </Section>
      <Section n={4} title={t.opinion}>
        <Opinion report={r} conceptId={conceptId} />
      </Section>
      <footer data-paper-foot>
        <p data-paper-disclaimer>{r.disclaimer}</p>
      </footer>
    </article>
  )
}

function Bars({ rows }: { rows: ResultReport["evidence"]["variants"] }) {
  const top = Math.max(...rows.map((r) => r.rate), 0)
  return (
    <div data-paper-bars>
      {rows.map((r) => (
        <div key={r.name} data-paper-bar-row role="img" aria-label={copy.proposal.barLabel(r.name, r.value)}>
          <span data-paper-bar-name>
            <span data-paper-bar-title>{r.name}</span>
            {r.change && <span>{r.change}</span>}
          </span>
          <span data-paper-bar-track>
            <span
              data-paper-bar-fill
              data-better={r.verdict === "better" || undefined}
              style={{ width: top > 0 ? `${(100 * r.rate) / top}%` : "0%" }}
            />
          </span>
          <span data-paper-bar-value>{r.value}</span>
        </div>
      ))}
    </div>
  )
}

/** 근거의 칸들(보이는 것만, 번호를 당긴다). */
function evidenceSections(r: ResultReport): { key: string; title: string; body: ReactNode }[] {
  const ev = r.evidence
  const out: { key: string; title: string; body: ReactNode }[] = []
  out.push({
    key: "who",
    title: t.sections.who,
    body: (
      <>
        <Bullets items={ev.who.lines} />
        {ev.who.cells.length > 0 && (
          <table data-paper-table data-paper-compare>
            <thead>
              <tr>
                <th scope="col">{t.whoHead.label}</th>
                <th scope="col">{t.whoHead.n}</th>
                <th scope="col">{t.whoHead.picked}</th>
                <th scope="col">{t.whoHead.rate}</th>
              </tr>
            </thead>
            <tbody>
              {ev.who.cells.map((c) => (
                <tr key={c.label}>
                  <td>{c.label}</td>
                  <td data-num>{t.people(c.n)}</td>
                  <td data-num>{t.people(c.picked)}</td>
                  <td data-num>{t.rate(c.rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </>
    ),
  })
  if (ev.from.rows.length > 0) {
    out.push({
      key: "from",
      title: t.sections.from,
      body: (
        <>
          <table data-paper-table data-paper-compare>
            <thead>
              <tr>
                <th scope="col">{t.fromHead.label}</th>
                <th scope="col">{t.fromHead.n}</th>
                <th scope="col">{t.fromHead.top}</th>
              </tr>
            </thead>
            <tbody>
              {ev.from.rows.map((x) => (
                <tr key={x.key}>
                  <td>{x.label}</td>
                  <td data-num>{t.people(x.n)}</td>
                  <td>{x.top.map((p) => t.topItem(p.name, p.count)).join(", ") || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {ev.from.note && <p>{ev.from.note}</p>}
        </>
      ),
    })
  }
  if (ev.barriers.length > 0) {
    out.push({
      key: "barriers",
      title: t.sections.barriers,
      body: (
        <table data-paper-table data-paper-compare data-paper-inflow>
          <thead>
            <tr>
              <th scope="col">{t.barrierHead.label}</th>
              <th scope="col">{t.barrierHead.n}</th>
            </tr>
          </thead>
          <tbody>
            {ev.barriers.map((b) => (
              <tr key={b.label}>
                <td>{b.label}</td>
                <td data-num>{t.people(b.n)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ),
    })
  }
  if (ev.variants.length > 0) {
    out.push({
      key: "variants",
      title: t.sections.variants,
      body: (
        <>
          <Bars rows={ev.variants} />
          <GroupPaper rows={ev.variants} />
        </>
      ),
    })
  }
  if (ev.voices.length > 0) {
    out.push({
      key: "voices",
      title: t.sections.voices,
      body: (
        <div data-paper-voices>
          {ev.voices.map((v, i) => (
            <div key={i} data-paper-voice>
              <p data-paper-voice-factor>{v.factor}</p>
              <blockquote data-paper-quote>{t.quote(v.quote, v.who)}</blockquote>
            </div>
          ))}
        </div>
      ),
    })
  }
  for (const [i, c] of ev.compare.entries()) {
    out.push({ key: `compare-${i}`, title: c.title, body: <Bullets items={c.lines} /> })
  }
  return out
}

function EvidenceSheet({ report, dept, date }: { report: ResultReport; dept: string; date: string }) {
  const sections = evidenceSections(report)
  const nx = report.next
  const parts: [string, string[]][] = [
    [t.nextParts.target, [nx.target]],
    [t.nextParts.questions, nx.questions],
    [t.nextParts.conditions, nx.conditions],
    [t.nextParts.unknowns, nx.unknowns],
  ]
  return (
    <article data-paper>
      <Head title={report.head.title} dept={dept} date={date} />
      <h2 data-paper-title>{t.evidence}</h2>
      {sections.map((s, i) => (
        <Section key={s.key} n={i + 1} title={s.title}>
          {s.body}
        </Section>
      ))}
      <Section n={sections.length + 1} title={t.next}>
        {parts
          .filter(([, items]) => items.length > 0)
          .map(([label, items]) => (
            <div key={label} data-paper-next-part>
              <p data-paper-voice-factor>{label}</p>
              <Bullets items={items} />
            </div>
          ))}
      </Section>
    </article>
  )
}

function AppendixSheet({ report, product, foot, dept, date }: {
  report: ResultReport
  product: ReactNode
  foot: ReactNode
  dept: string
  date: string
}) {
  const a = report.appendix
  const parts: { key: string; title: string; body: ReactNode }[] = [
    { key: "method", title: t.appendixParts.method, body: <Bullets items={a.method} /> },
  ]
  if (a.records.length > 0) parts.push({ key: "records", title: t.appendixParts.records, body: <Bullets items={a.records} /> })
  parts.push({ key: "overview", title: t.appendixParts.overview, body: product })
  parts.push({ key: "rules", title: t.appendixParts.rules, body: <Bullets items={a.rules} /> })
  return (
    <article data-paper>
      <Head title={report.head.title} dept={dept} date={date} />
      <h2 data-paper-title>{t.appendix}</h2>
      {parts.map((p, i) => (
        <Section key={p.key} n={i + 1} title={p.title}>
          {p.body}
        </Section>
      ))}
      {foot}
    </article>
  )
}

/** 결과 보고서 한 벌(종이 세 장). product는 부록의 제품 개요(Paper.tsx가 그린다), foot은 각주와 알림. */
export function ReportSheets({ report, conceptId, dept, date, product, foot }: {
  report: ResultReport
  conceptId: string
  dept: string
  date: string
  product: ReactNode
  foot: ReactNode
}) {
  return (
    <>
      <FirstSheet report={report} conceptId={conceptId} dept={dept} date={date} />
      <EvidenceSheet report={report} dept={dept} date={date} />
      <AppendixSheet report={report} product={product} foot={foot} dept={dept} date={date} />
    </>
  )
}
