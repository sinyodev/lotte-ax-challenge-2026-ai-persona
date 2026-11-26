/**
 * "LLM용 복사"(지시서 22의 E): 지금 보이는 종이 전부를 마크다운 한 벌로. 종이(Paper.tsx)와 같은 자료, 같은 차례, 같은 글이다.
 * 종이 한 장은 `# {머리}: {제품명}`으로 시작하고, 칸은 `##`, 줄은 `-`, 표는 마크다운 표, 인용은 `>`. 막대 그림은 표로 옮긴다.
 * 종이 사이는 `---`. 유의 사항은 맨 끝에 한 줄(종이마다 같은 글이라 한 번만).
 */
import { copy } from "../../copy"
import { isReportTest, type ProposalPage, type ReportTest } from "../../chat/contract"
import { isResultReport, type ResultReport } from "../../chat/contract-shelf"
import { reportCopy as rc } from "../../copy/report"

const t = copy.proposal

const cell = (x: string) => x.replace(/\|/g, "\\|").replace(/\n/g, " ")

function table(head: string[], rows: string[][]): string {
  return [
    `| ${head.map(cell).join(" | ")} |`,
    `| ${head.map(() => "---").join(" | ")} |`,
    ...rows.map((r) => `| ${r.map(cell).join(" | ")} |`),
  ].join("\n")
}

const bullets = (items: string[]) => items.map((x) => `- ${x}`).join("\n")

function reportBlocks(test: ReportTest): [string, string][] {
  const out: [string, string][] = []
  out.push([t.report.overview, bullets(test.overview)])
  const findings = [bullets(test.findings)]
  if (test.inflow.length > 0) {
    findings.push(
      table(
        [t.inflowHead.label, t.inflowHead.n, t.inflowHead.share],
        test.inflow.map((r) => [r.label, t.people(r.n), r.share]),
      ),
    )
  }
  out.push([t.report.findings, findings.join("\n\n")])
  if (test.compare.length > 0) {
    const lines = test.compare.map((r) => r.line).filter(Boolean) as string[]
    const parts = [
      table(
        [t.variantHead.name, t.variantHead.change, t.variantHead.n, t.variantHead.rank],
        test.compare.map((r) => [r.name, r.change || "-", t.people(r.n), t.rank(r.rank)]),
      ),
    ]
    if (lines.length > 0) parts.push(bullets(lines))
    out.push([t.report.variants, parts.join("\n\n")])
  }
  const { picked, passed } = test.voices
  if (picked || passed) {
    const parts: string[] = []
    if (picked) parts.push(`**${picked.factor}**`, `> ${t.quote(picked.quote, picked.who)}`)
    if (passed) {
      parts.push(`**${passed.factor}**`)
      if (passed.quote) parts.push(`> ${t.quote(passed.quote, passed.who)}`)
      if (passed.others) parts.push(passed.others)
    }
    out.push([t.report.voices, parts.join("\n\n")])
  }
  out.push([t.report.plans, test.plans.map((p) => `- **${p.title}**: ${p.body}`).join("\n")])
  return out
}

/** 결과 보고서(지시서 32): 종이(ReportSheets.tsx)와 같은 차례와 글. 첫 장 → 근거 → 다음 실제 조사의 조건 → 부록. */
function resultReportMarkdown(r: ResultReport, dept: string, date: string, product: string, foot: string): string {
  const out: string[] = []
  out.push(`# ${r.head.title}: ${r.head.product}`, t.meta(dept, t.date(date)))
  if (r.head.spec) out.push(r.head.spec)
  out.push(`## ${rc.recommend}\n\n**${r.recommend.text}**\n\n${bullets(r.recommend.reasons)}`)
  out.push(`## ${rc.numbered(1, rc.decisions)}\n\n${r.decisions.map((d, i) => `${rc.circled(i + 1)} ${d}`).join("\n")}`)
  out.push(`## ${rc.numbered(2, rc.key)}\n\n${table(r.key.map((k) => k.label), [r.key.map((k) => (k.note ? `${k.value} (${k.note})` : k.value))])}`)
  out.push(`## ${rc.numbered(3, rc.limits)}\n\n${bullets(r.limits)}`)
  out.push(`## ${rc.numbered(4, rc.opinion)}\n\n${r.opinion.trim() || rc.opinionEmpty}`)
  out.push(`**${r.disclaimer}**`, "---", `# ${rc.evidence}`)
  const ev = r.evidence
  const sec: [string, string][] = []
  const who = [bullets(ev.who.lines)]
  if (ev.who.cells.length > 0) {
    const h = rc.whoHead
    who.push(table([h.label, h.n, h.picked, h.rate], ev.who.cells.map((c) => [c.label, rc.people(c.n), rc.people(c.picked), rc.rate(c.rate)])))
  }
  sec.push([rc.sections.who, who.join("\n\n")])
  if (ev.from.rows.length > 0) {
    const h = rc.fromHead
    const parts = [table([h.label, h.n, h.top], ev.from.rows.map((x) => [x.label, rc.people(x.n), x.top.map((p) => rc.topItem(p.name, p.count)).join(", ") || "-"]))]
    if (ev.from.note) parts.push(ev.from.note)
    sec.push([rc.sections.from, parts.join("\n\n")])
  }
  if (ev.barriers.length > 0) {
    sec.push([rc.sections.barriers, table([rc.barrierHead.label, rc.barrierHead.n], ev.barriers.map((b) => [b.label, rc.people(b.n)]))])
  }
  if (ev.variants.length > 0) {
    const lines = ev.variants.map((x) => x.line).filter(Boolean) as string[]
    const parts = [table([t.variantHead.name, t.variantHead.change, t.variantHead.n, t.variantHead.rank],
      ev.variants.map((x) => [x.name, x.change || "-", t.people(x.n), t.rank(x.rank)]))]
    if (lines.length > 0) parts.push(bullets(lines))
    sec.push([rc.sections.variants, parts.join("\n\n")])
  }
  if (ev.voices.length > 0) {
    sec.push([rc.sections.voices, ev.voices.map((v) => `**${v.factor}**\n\n> ${rc.quote(v.quote, v.who)}`).join("\n\n")])
  }
  for (const c of ev.compare) sec.push([c.title, bullets(c.lines)])
  const nx = r.next
  const nextParts: [string, string[]][] = [[rc.nextParts.target, [nx.target]], [rc.nextParts.questions, nx.questions],
    [rc.nextParts.conditions, nx.conditions], [rc.nextParts.unknowns, nx.unknowns]]
  sec.push([rc.next, nextParts.filter(([, x]) => x.length > 0).map(([label, x]) => `**${label}**\n\n${bullets(x)}`).join("\n\n")])
  out.push(...sec.map(([title, text], i) => `## ${rc.numbered(i + 1, title)}\n\n${text}`))
  out.push("---", `# ${rc.appendix}`)
  const a = r.appendix
  const app: [string, string][] = [[rc.appendixParts.method, bullets(a.method)]]
  if (a.records.length > 0) app.push([rc.appendixParts.records, bullets(a.records)])
  app.push([rc.appendixParts.overview, product])
  app.push([rc.appendixParts.rules, bullets(a.rules)])
  out.push(...app.map(([title, text], i) => `## ${rc.numbered(i + 1, title)}\n\n${text}`))
  if (foot) out.push(foot)
  return out.join("\n\n")
}

function pageMarkdown(page: ProposalPage, dept: string, date: string): { text: string; caution: string | null } {
  const test = isReportTest(page.test) ? page.test : null
  const head = [`# ${t.mdTitle(test ? t.reportHeading : t.heading, page.title)}`, t.meta(dept, t.date(date))]
  head.push(test ? `## ${t.review}\n\n${test.review.text}` : `## ${t.gist}\n\n${page.gist}`)

  const blocks: [string, string][] = test ? reportBlocks(test) : []
  if (page.background.length > 0) {
    blocks.push([
      t.sections.background,
      bullets(page.background.map((b) => b.text + b.refs.map((n) => ` ${t.ref(n)}`).join(""))),
    ])
  }
  const s = page.sketch
  const sketch = [
    s.headline,
    s.name,
    s.benefit,
    ...s.points,
    s.price ? copy.workbench.conceptPriceLine(s.price, s.pack) : "",
  ].filter(Boolean)
  blocks.push([
    t.sections.overview,
    [
      table([t.overviewHead.label, t.overviewHead.value], page.overview.map((o) => [o.label, o.value])),
      `**${t.sketch}**\n\n${bullets(sketch)}`,
    ].join("\n\n"),
  ])
  if (page.compare.rows.length > 1) {
    const notes = [page.compare.pod && t.pod(page.compare.pod), page.compare.range].filter(Boolean) as string[]
    const h = t.compareHead
    const parts = [
      table(
        [h.role, h.name, h.pack, h.price, h.promo],
        page.compare.rows.map((r) => [t.roles[r.role], r.name, r.pack, r.price, r.promo]),
      ),
    ]
    if (notes.length > 0) parts.push(bullets(notes))
    blocks.push([t.sections.compare, parts.join("\n\n")])
  }
  if (!test && page.plan.length > 0) blocks.push([t.sections.plan, bullets(page.plan)])

  const body = blocks.map(([title, text], i) => `## ${t.numbered(i + 1, title)}\n\n${text}`)
  const foot = [
    ...page.sources.map((x) => `${t.ref(x.n)} ${x.text}`),
    ...(page.notices ?? [page.notice]),
  ]
  if (isResultReport(page.test)) {
    const product = blocks.map(([title, text]) => `**${title}**\n\n${text}`).join("\n\n")
    return { text: resultReportMarkdown(page.test, dept, date, product, foot.join("\n\n")), caution: null }
  }
  return {
    text: [...head, ...body, foot.join("\n\n")].filter(Boolean).join("\n\n"),
    caution: test ? test.caution : null,
  }
}

/** 종이들(보이는 차례대로)을 마크다운 한 벌로. */
export function proposalMarkdown(pages: ProposalPage[], dept: string, date: string): string {
  const made = pages.map((p) => pageMarkdown(p, dept, date))
  const caution = made.find((m) => m.caution)?.caution
  const text = made.map((m) => m.text).join("\n\n---\n\n")
  return caution ? `${text}\n\n---\n\n${t.caution}: ${caution}\n` : `${text}\n`
}
