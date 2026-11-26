/**
 * 신제품 제안서의 종이(지시서 14의 4절). /proposal/:chatId 화면과 작업대의 결과 보고서 단계(지시서 21)가 함께 쓴다.
 * 종이 안의 글은 서버가 보낸 보고서체 그대로이고, 칸의 이름만 copy.ts에 있다. 매대 테스트를 한 컨셉의 종이는 결과 보고서(지시서 22). 종이의 치수와 글씨는 proposal.css 한 곳에 있다.
 */
import { useEffect, useRef, useState } from "react"
import { HStack } from "@astryxdesign/core/HStack"
import { Skeleton } from "@astryxdesign/core/Skeleton"
import { Text } from "@astryxdesign/core/Text"
import { VStack } from "@astryxdesign/core/VStack"
import { copy } from "../../copy"
import { isReportTest, type Proposal, type ProposalPage as Page, type ReportTest } from "../../chat/contract"
import { CONTAINER_ICONS } from "../ContainerIcon"
import { containerOf } from "../workbench/CardBodies"
import { isResultReport } from "../../chat/contract-shelf"
import { OPINION_EVENT, ReportSheets, type OpinionDetail } from "./ReportSheets"
import "../../pages/proposal.css"

const t = copy.proposal

export type LoadedProposal = { state: "loading" } | { state: "ready"; data: Proposal } | { state: "failed" }

/** GET /api/chats/{id}/proposal. attempt를 올리면 다시 받는다. enabled가 거짓이면 받지 않는다(작업대가 결과 보고서 단계일 때만 받게). */
export function useProposal(chatId: string, attempt: number, enabled = true): LoadedProposal {
  const [loaded, setLoaded] = useState<LoadedProposal>({ state: "loading" })
  useEffect(() => {
    if (!enabled) return
    let alive = true
    setLoaded({ state: "loading" })
    fetch(`/api/chats/${encodeURIComponent(chatId)}/proposal`)
      .then((r) => (r.ok ? (r.json() as Promise<Proposal>) : Promise.reject(r.status)))
      .then((data) => alive && setLoaded({ state: "ready", data }))
      .catch(() => alive && setLoaded({ state: "failed" }))
    return () => {
      alive = false
    }
  }, [chatId, attempt, enabled])
  // 결과 보고서의 기획자 의견을 고치면(ReportSheets) 받아 둔 종이 자료에도 넣는다(LLM용 복사가 같은 글을 내게, 지시서 32)
  useEffect(() => {
    const onOpinion = (e: Event) => {
      const d = (e as CustomEvent<OpinionDetail>).detail
      if (d.chatId !== chatId) return
      setLoaded((cur) => {
        if (cur.state !== "ready") return cur
        const pages = cur.data.pages.map((p) =>
          p.concept_id === d.conceptId && isResultReport(p.test) ? { ...p, test: { ...p.test, opinion: d.text } } : p,
        )
        return { state: "ready", data: { ...cur.data, pages } }
      })
    }
    window.addEventListener(OPINION_EVENT, onOpinion)
    return () => window.removeEventListener(OPINION_EVENT, onOpinion)
  }, [chatId])
  return loaded
}

/** 불러오는 동안 흐른 초(서버가 글을 쓰는 데 10~40초가 걸릴 수 있다). */
export function useSeconds(isRunning: boolean) {
  const started = useRef(Date.now())
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!isRunning) return
    started.current = Date.now()
    setNow(Date.now())
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [isRunning])
  return Math.max(0, Math.floor((now - started.current) / 1000))
}

function Ref({ refs }: { refs: number[] }) {
  if (refs.length === 0) return null
  return <sup data-paper-ref>{refs.map((n) => t.ref(n)).join(" ")}</sup>
}

function Section({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section data-paper-section>
      <h3 data-paper-h>{t.numbered(n, title)}</h3>
      {children}
    </section>
  )
}

function Bullets({ items }: { items: React.ReactNode[] }) {
  return (
    <ul data-paper-bullets>
      {items.map((x, i) => (
        <li key={i}>{x}</li>
      ))}
    </ul>
  )
}

/** 예시 시안: 컨셉 카드 위쪽의 것(용기 윤곽과 글)을 작게. 새 그림을 만들지 않는다. */
function Sketch({ sketch, image }: { sketch: Page["sketch"]; image?: string | null }) {
  const container = containerOf(sketch.pack)
  const Shape = container ? CONTAINER_ICONS[container] : null
  return (
    <figure data-paper-sketch>
      <figcaption data-paper-sketch-label>{t.sketch}</figcaption>
      {sketch.headline && <p data-paper-sketch-headline>{sketch.headline}</p>}
      <p data-paper-sketch-name>{sketch.name}</p>
      <div data-paper-sketch-image data-photo={image ? "" : undefined}>
        {image ? <img src={image} alt={sketch.name} /> : Shape && <Shape aria-hidden data-paper-sketch-shape />}
      </div>
      {sketch.benefit && <p data-paper-sketch-benefit>{sketch.benefit}</p>}
      {sketch.points.length > 0 && (
        <ul data-paper-sketch-points>
          {sketch.points.map((p, i) => (
            <li key={i}>{p}</li>
          ))}
        </ul>
      )}
      {sketch.price && (
        <p data-paper-sketch-price>{copy.workbench.conceptPriceLine(sketch.price, sketch.pack)}</p>
      )}
    </figure>
  )
}

/** 변경안 비교의 가로 막대: 같은 눈금(가장 높은 선택률이 꽉 찬 길이). 기존안보다 분명히 나은 안만 강조색. */
function Bars({ rows }: { rows: ReportTest["compare"] }) {
  const top = Math.max(...rows.map((r) => r.rate), 0)
  return (
    <div data-paper-bars>
      {rows.map((r) => (
        <div key={r.name} data-paper-bar-row role="img" aria-label={t.barLabel(r.name, r.value)}>
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

/** 결과 보고서의 칸(지시서 22): 테스트 개요, 주요 결과, 변경안 비교, 소비자 반응, 시사점 및 향후 계획. */
function reportSections(test: ReportTest) {
  const out: { key: string; title: string; body: React.ReactNode }[] = []
  out.push({ key: "r-overview", title: t.report.overview, body: <Bullets items={test.overview} /> })
  out.push({
    key: "r-findings",
    title: t.report.findings,
    body: (
      <>
        <Bullets items={test.findings} />
        {test.inflow.length > 0 && (
          <table data-paper-table data-paper-compare data-paper-inflow>
            <thead>
              <tr>
                <th scope="col">{t.inflowHead.label}</th>
                <th scope="col">{t.inflowHead.n}</th>
                <th scope="col">{t.inflowHead.share}</th>
              </tr>
            </thead>
            <tbody>
              {test.inflow.map((r) => (
                <tr key={r.label}>
                  <td>{r.label}</td>
                  <td data-num>{t.people(r.n)}</td>
                  <td data-num>{r.share}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </>
    ),
  })
  if (test.compare.length > 0) {
    const lines = test.compare.map((r) => r.line).filter(Boolean) as string[]
    out.push({
      key: "r-variants",
      title: t.report.variants,
      body: (
        <>
          <Bars rows={test.compare} />
          {lines.length > 0 && <Bullets items={lines} />}
        </>
      ),
    })
  }
  const { picked, passed } = test.voices
  if (picked || passed) {
    out.push({
      key: "r-voices",
      title: t.report.voices,
      body: (
        <div data-paper-voices>
          {picked && (
            <div data-paper-voice>
              <p data-paper-voice-factor>{picked.factor}</p>
              <blockquote data-paper-quote>{t.quote(picked.quote, picked.who)}</blockquote>
            </div>
          )}
          {passed && (
            <div data-paper-voice>
              <p data-paper-voice-factor>{passed.factor}</p>
              {passed.quote && <blockquote data-paper-quote>{t.quote(passed.quote, passed.who)}</blockquote>}
              {passed.others && <p>{passed.others}</p>}
            </div>
          )}
        </div>
      ),
    })
  }
  out.push({
    key: "r-plans",
    title: t.report.plans,
    body: (
      <ol data-paper-plans>
        {test.plans.map((p) => (
          <li key={p.title}>
            <p data-paper-plan-title>{p.title}</p>
            <p>{p.body}</p>
          </li>
        ))}
      </ol>
    ),
  })
  return out
}

/**
 * 종이 한 장. 제안 배경이 없으면 그 절을 빼고 번호를 당긴다. 비교할 제품이 없으면 그 절을 뺀다.
 * 매대 테스트를 한 컨셉(page.test, 약속 v1.13)은 결과 보고서: 맨 위에 검토 의견, 결과의 칸들 다음에 제안서의 칸을 번호를 이어 두고,
 * 향후 계획은 시사점 및 향후 계획이 갈음하며, 맨 아래에 유의 사항.
 */
export function Paper({ page, dept, date }: { page: Page; dept: string; date: string }) {
  const test = isReportTest(page.test) ? page.test : null
  const hasCompare = page.compare.rows.length > 1
  const sections: { key: string; title: string; body: React.ReactNode }[] = test ? reportSections(test) : []
  if (page.background.length > 0) {
    sections.push({
      key: "background",
      title: t.sections.background,
      body: (
        <Bullets
          items={page.background.map((b) => (
            <>
              {b.text}
              <Ref refs={b.refs} />
            </>
          ))}
        />
      ),
    })
  }
  sections.push({
    key: "overview",
    title: t.sections.overview,
    body: (
      <div data-paper-overview>
        <table data-paper-table data-paper-kv>
          <tbody>
            {page.overview.map((o) => (
              <tr key={o.label}>
                <th scope="row">{o.label}</th>
                <td>{o.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <Sketch sketch={page.sketch} image={page.image} />
      </div>
    ),
  })
  if (hasCompare) {
    const notes = [page.compare.pod && t.pod(page.compare.pod), page.compare.range].filter(Boolean) as string[]
    sections.push({
      key: "compare",
      title: t.sections.compare,
      body: (
        <>
          <table data-paper-table data-paper-compare>
            <thead>
              <tr>
                <th scope="col">{t.compareHead.role}</th>
                <th scope="col">{t.compareHead.name}</th>
                <th scope="col">{t.compareHead.pack}</th>
                <th scope="col">{t.compareHead.price}</th>
                <th scope="col">{t.compareHead.promo}</th>
              </tr>
            </thead>
            <tbody>
              {page.compare.rows.map((r, i) => (
                <tr key={i} data-proposal-row={r.role === "proposal" || undefined}>
                  <td>{t.roles[r.role]}</td>
                  <td>{r.name}</td>
                  <td>{r.pack}</td>
                  <td data-num>{r.price}</td>
                  <td>{r.promo}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {notes.length > 0 && <Bullets items={notes} />}
        </>
      ),
    })
  }
  if (!test && page.plan.length > 0) {
    sections.push({ key: "plan", title: t.sections.plan, body: <Bullets items={page.plan} /> })
  }

  const foot = (
    <footer data-paper-foot>
      {page.sources.length > 0 && (
        <p data-paper-sources>
          {page.sources.map((s) => (
            <span key={s.n}>
              {t.ref(s.n)} {s.text}
            </span>
          ))}
        </p>
      )}
      {(page.notices ?? [page.notice]).map((x) => (
        <p key={x}>{x}</p>
      ))}
      {test && (
        <p data-paper-caution>
          <span data-paper-gist-label>{t.caution}</span> {test.caution}
        </p>
      )}
    </footer>
  )

  // 지시서 32: 결과 보고서는 종이 세 장(첫 장, 근거, 부록). 제안서의 칸(배경, 제품 개요, 경쟁 제품)은 부록의 제품 개요로 간다
  if (isResultReport(page.test)) {
    const product = (
      <>
        {sections.map((s) => (
          <div key={s.key} data-paper-subsection>
            <p data-paper-voice-factor>{s.title}</p>
            {s.body}
          </div>
        ))}
      </>
    )
    return <ReportSheets report={page.test} conceptId={page.concept_id} dept={dept} date={date} product={product} foot={foot} />
  }

  return (
    <article data-paper>
      <header data-paper-head>
        <h1 data-paper-kind>{test ? t.reportHeading : t.heading}</h1>
        <span data-paper-meta>{t.meta(dept, t.date(date))}</span>
      </header>
      <h2 data-paper-title>{page.title}</h2>
      {test ? (
        <div data-paper-gist data-paper-review={test.review.tone}>
          <span data-paper-gist-label>{t.review}</span>
          <p>{test.review.text}</p>
        </div>
      ) : (
        <div data-paper-gist>
          <span data-paper-gist-label>{t.gist}</span>
          <p>{page.gist}</p>
        </div>
      )}
      {sections.map((s, i) => (
        <Section key={s.key} n={i + 1} title={s.title}>
          {s.body}
        </Section>
      ))}
      {foot}
    </article>
  )
}

/** 불러오는 동안: 종이 모양의 뼈대와 흐른 시간. */
export function PaperSkeleton({ seconds }: { seconds: number }) {
  return (
    <article data-paper aria-busy="true" aria-label={t.loading}>
      <VStack gap={4}>
        <HStack gap={2} justify="between" vAlign="center">
          <Skeleton height={18} width="30%" />
          {seconds >= 1 && (
            <Text type="supporting" hasTabularNumbers>
              {copy.test.elapsed(seconds)}
            </Text>
          )}
        </HStack>
        <Skeleton height={28} width="55%" index={1} />
        <Skeleton height={48} index={2} />
        {[3, 4, 5, 6, 7, 8].map((i) => (
          <Skeleton key={i} height={16} width={i % 3 === 0 ? "70%" : "100%"} index={i} />
        ))}
        <Skeleton height={160} index={9} />
      </VStack>
    </article>
  )
}
