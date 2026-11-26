/**
 * 후속 개선의 새 화면: 보고서 한 장(컨셉 보드 분석, 테스트 결과와 같은 문법). 지금은 "조사 확인" 단계만.
 * 결론 한 문장 → 숫자 줄 → ① 가상 소비자와 실제 조사의 차이 → ② 가격별 매출 → ③ 소비자 의견.
 * 다음 행동(가상 소비자 맞추기, 다시 테스트)은 여기 두지 않는다. 칠성이의 말과 대화의 버튼이 맡는다.
 * 숫자는 모두 GET /api/followup/{id}의 payload에서 온다(서버가 조사 파일에서 집계).
 */
import type { ReactNode } from "react"
import { CheckCircleIcon, ExclamationCircleIcon } from "@heroicons/react/20/solid"
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { Text } from "@astryxdesign/core/Text"
import type { FollowupDiff, FollowupOpinion, FollowupPayload, FollowupPeople, FollowupPerson } from "../../chat/contract-followup"
import { followupReportCopy as t } from "../../copy/followup-report"
import { BarTable, type BarRow } from "./ResultCharts"
import "./analysis-report.css"
import "./result-report.css"
import "./followup-report.css"

/** 100명 중 이만큼은 달라야 "달랐다"고 본다. 서버 agent/followup.MIN_GAP과 같다. */
const MIN_GAP = 5

const ink = "var(--color-text-primary)"
const line = "var(--color-border)"
const faint = "var(--color-border-emphasized)"
const accent = "var(--color-accent)"

type Gap = FollowupDiff & { virtual: number; gap: number }
const gapsOf = (p: FollowupPayload): Gap[] =>
  p.diffs.filter((d): d is FollowupDiff & { virtual: number } => d.virtual !== null).map((d) => ({ ...d, gap: d.actual - d.virtual }))
export const bigGaps = (p: FollowupPayload) => gapsOf(p).filter((d) => Math.abs(d.gap) >= MIN_GAP).sort((a, b) => Math.abs(b.gap) - Math.abs(a.gap))

function headline(p: FollowupPayload) {
  const top = bigGaps(p)[0]
  if (!top) return t.headline.same(p.target)
  return top.id === "price" ? t.headline.price(p.concept.price, p.target, top.actual, top.virtual) : t.headline.worry(p.target, top.actual, top.virtual)
}

function Figure({ name, value, caption, status }: { name: string; value: string; caption: string; status?: "flag" | "ok" }) {
  return (
    <div className="cba-figure">
      <div className="cba-figure__name">
        {status === "flag" && <ExclamationCircleIcon className="cba-mark" data-flag aria-hidden="true" />}
        {status === "ok" && <CheckCircleIcon className="cba-mark" aria-hidden="true" />}
        <Text weight="medium">{name}</Text>
      </div>
      <div className="cba-figure__value">{value}</div>
      <Text as="p" display="block">{caption}</Text>
    </div>
  )
}

function Block({ name, title, keys, children }: { name: string; title: string; keys?: ReactNode; children: ReactNode }) {
  return (
    <section className="cba-finding">
      <div className="fr-head">
        <div className="rr-cell__head">
          <span className="rr-eyebrow">{name}</span>
          {keys && <div className="cba-keys">{keys}</div>}
        </div>
        <h3 className="cba-finding__title">{title}</h3>
      </div>
      {children}
    </section>
  )
}

// ---------- ① 가상 소비자와 실제 조사: 문항마다 막대 둘(가상, 실제)과 차이 ----------

function DiffTable({ p }: { p: FollowupPayload }) {
  return (
    <table className="rr-bars fr-diff" data-track aria-label={t.diffName}>
      <thead>
        <tr>
          <th scope="col">{t.colItem}</th>
          <td aria-hidden="true" />
          <th scope="col" data-num>{t.colVirtual}</th>
          <th scope="col" data-num>{t.colActual}</th>
          <th scope="col" data-num>{t.colGap}</th>
        </tr>
      </thead>
      <tbody>
        {p.diffs.map((d) => {
          const gap = d.virtual === null ? null : d.actual - d.virtual
          const big = gap !== null && Math.abs(gap) >= MIN_GAP
          return (
            <tr key={d.id} data-strong={big || undefined}>
              <th scope="row">{d.text}</th>
              <td className="rr-bars__bar fr-diff__bars" aria-hidden="true">
                <span>{d.virtual !== null && <i data-tone="faint" style={{ inlineSize: `${d.virtual}%` }} />}</span>
                <span><i data-tone="ink" style={{ inlineSize: `${d.actual}%` }} /></span>
              </td>
              <td data-num>{d.virtual === null ? t.notAsked : t.pct(d.virtual)}</td>
              <td data-num>{t.pct(d.actual)}</td>
              <td data-num data-flag={big || undefined}>{gap === null ? "" : t.gap(gap)}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

// ---------- ② 가격별 매출: 막대(가격마다) + 지금 가격의 세로줄, 옆에 표 ----------

function Tip({ active, label, payload }: { active?: boolean; label?: number; payload?: { value?: number }[] }) {
  if (!active || !payload?.length || label == null) return null
  return (
    <div className="cba-tip">
      <Text weight="semibold">{t.won(label)}</Text>
      <div className="cba-tip__row"><Text>{t.tipMoney}</Text><Text hasTabularNumbers weight="medium">{t.money(payload[0].value ?? 0)}</Text></div>
    </div>
  )
}

function MoneyChart({ p }: { p: FollowupPayload }) {
  return (
    <div className="cba-chart">
      <div className="cba-keys">
        <span className="cba-key" data-kind="bar"><i aria-hidden="true" /><Text>{t.keyBest}</Text></span>
        <span className="cba-key" data-kind="bar-soft"><i aria-hidden="true" /><Text>{t.keyRest}</Text></span>
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={p.curve} margin={{ top: 30, right: 24, bottom: 0, left: 0 }} barCategoryGap="18%" accessibilityLayer>
          <CartesianGrid vertical={false} stroke={line} />
          <XAxis dataKey="price" tickLine={false} axisLine={{ stroke: faint }} tickMargin={10} interval={0} tickFormatter={(v: number) => t.won(v)} />
          <YAxis width={44} tickLine={false} axisLine={false} tickCount={4} tickFormatter={(v: number) => t.moneyAxis(v)} />
          <Tooltip cursor={{ fill: line, fillOpacity: 0.5 }} content={<Tip />} />
          <Bar dataKey="money" radius={[3, 3, 0, 0]} isAnimationActive={false}>
            {p.curve.map((c) => <Cell key={c.price} fill={c.price === p.best_price ? ink : faint} />)}
          </Bar>
          {p.curve.some((c) => c.price === p.concept.price) && (
            <ReferenceLine x={p.concept.price} stroke={accent} strokeWidth={2} ifOverflow="visible"
              label={{ value: t.nowAt(p.concept.price), position: "top", offset: 12, fill: accent, className: "cba-chart__value cba-chart__value--accent" }} />
          )}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function PriceTable({ p }: { p: FollowupPayload }) {
  return (
    <table className="cba-table fr-prices">
      <thead>
        <tr><th scope="col">{t.colPrice}</th><th scope="col" data-num>{t.colCanPay}</th><th scope="col" data-num>{t.colMoney}</th></tr>
      </thead>
      <tbody>
        {p.curve.map((c) => (
          <tr key={c.price} data-now={c.price === p.concept.price || undefined} data-best={c.price === p.best_price || undefined}>
            <th scope="row">{t.won(c.price)}</th>
            <td data-num>{t.pct(c.share)}</td>
            <td data-num>{t.money(c.money)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// ---------- ③ 소비자 의견 ----------

function opinionRows(items: FollowupOpinion[]): BarRow[] {
  const top = Math.max(...items.map((x) => x.n), 1)
  return items.map((x, i) => ({ name: x.text, share: x.n / top, cells: [t.people(x.n), t.pct(x.intent)], tone: i === 0 ? "ink" : "faint", strong: i === 0 }))
}

function OpinionCell({ name, title, items }: { name: string; title: (text: string) => string; items: FollowupOpinion[] }) {
  if (!items.length) return null
  return (
    <section className="rr-cell">
      <div className="rr-cell__head"><span className="rr-eyebrow">{name}</span></div>
      <h3 className="cba-finding__title">{title(items[0].text)}</h3>
      <div className="rr-cell__body">
        <BarTable label={name} head={[t.colOpinion, t.colSaid, t.colIntent]} rows={opinionRows(items)} />
      </div>
    </section>
  )
}

// ---------- 가상 소비자 최적화: 최적화 전과 후, 실제 ----------

export function FollowupFit({ payload: p }: { payload: FollowupPayload }) {
  const fit = p.fit
  if (!fit) return <FollowupReport payload={p} />
  const f = t.fit
  const rows = p.diffs.filter((d) => fit.diffs[d.id] !== undefined)
  const moved = rows
    .filter((d): d is FollowupDiff & { virtual: number } => d.virtual !== null && Math.abs(fit.diffs[d.id] - d.virtual) >= MIN_GAP)
    .sort((a, b) => Math.abs(fit.diffs[b.id] - b.virtual) - Math.abs(fit.diffs[a.id] - a.virtual))
  const fresh = rows.filter((d) => d.virtual === null)
  return (
    <article className="cba rr fr">
      <div className="fr-head">
        <h2 className="cba-headline">{f.headline(fit.n, p.target)}</h2>
        <Text as="p" display="block">{f.lead(p.target, p.n.target, fit.n)}</Text>
      </div>
      <div className="cba-figures">
        <Figure name={f.figSurvey(p.target)} value={t.people(p.n.target)} caption={f.figSurveyOf} />
        <Figure name={f.figPeople} value={t.people(fit.n)} caption={f.figPeopleOf} status="ok" />
        {rows.slice(0, 2).map((d) => (
          <Figure key={d.id} name={t.figGap[d.id]?.(p.concept.price) ?? d.text} value={t.pct(fit.diffs[d.id])}
            caption={d.virtual === null ? f.figNew : f.figBefore(d.virtual)} status="ok" />
        ))}
      </div>

      <Block name={f.name} title={moved[0] ? f.title[moved[0].id] ?? f.titleSame : f.titleSame}
        keys={<>
          <span className="cba-key" data-kind="bar-soft"><i aria-hidden="true" /><Text>{f.keyBefore}</Text></span>
          <span className="cba-key" data-kind="bar"><i aria-hidden="true" /><Text>{f.keyAfter}</Text></span>
        </>}>
        <table className="rr-bars fr-diff" data-track aria-label={f.name}>
          <thead>
            <tr>
              <th scope="col">{t.colItem}</th>
              <td aria-hidden="true" />
              <th scope="col" data-num>{f.colBefore}</th>
              <th scope="col" data-num>{f.colAfter}</th>
              <th scope="col" data-num>{f.colActual}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((d) => (
              <tr key={d.id} data-strong={moved.some((m) => m.id === d.id) || undefined}>
                <th scope="row">{d.text}</th>
                <td className="rr-bars__bar fr-diff__bars" aria-hidden="true">
                  <span>{d.virtual !== null && <i data-tone="faint" style={{ inlineSize: `${d.virtual}%` }} />}</span>
                  <span><i data-tone="ink" style={{ inlineSize: `${fit.diffs[d.id]}%` }} /></span>
                </td>
                <td data-num>{d.virtual === null ? f.none : t.pct(d.virtual)}</td>
                <td data-num>{t.pct(fit.diffs[d.id])}</td>
                <td data-num>{t.pct(d.actual)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Block>

      <Block name={f.valueName} title={f.valueTitle(p.target)}>
        <ul className="fr-values">
          {moved.map((d) => f.value[d.id] && <li key={d.id}><Text>{f.value[d.id](p.concept.price, d.virtual, fit.diffs[d.id])}</Text></li>)}
          {fresh.filter((d) => d.id === "hope").map((d) => <li key={d.id}><Text>{f.valueHope(fit.diffs[d.id])}</Text></li>)}
        </ul>
        <Text as="p" display="block">{f.how}</Text>
      </Block>
    </article>
  )
}

// ---------- 최적화로 나온 개선안과 보정의 순환 ----------

export function FollowupIdeas({ payload: p }: { payload: FollowupPayload }) {
  const c = t.ideas
  const ideas = p.ideas ?? []
  const fit = p.fit
  const kind = (k: string) => c.kinds[k] ?? k
  return (
    <article className="cba rr fr">
      <div className="fr-head">
        <h2 className="cba-headline">{ideas.length ? c.headline(ideas.length) : c.none}</h2>
        {ideas.length > 0 && <Text as="p" display="block">{c.lead}</Text>}
      </div>

      {ideas.length > 0 && (
        <Block name={c.name} title={c.title(kind(ideas[0].kind))}>
          <table className="cba-table fr-ideas">
            <thead>
              <tr>
                <th scope="col">{c.colWhat}</th>
                <th scope="col">{c.colNow}</th>
                <th scope="col">{c.colNext}</th>
                <th scope="col" data-num>{c.colReach}</th>
              </tr>
            </thead>
            <tbody>
              {ideas.map((x, i) => (
                <tr key={i} data-best={i === 0 || undefined}>
                  <th scope="row">{kind(x.kind)}</th>
                  <td>{x.before}</td>
                  <td>
                    <div className="fr-ideas__next">{x.after}</div>
                    <Text as="p" display="block">{x.reason}</Text>
                  </td>
                  <td data-num>
                    {x.effect === null ? "" : x.effect.kind === "price" ? c.reach.price(x.effect.before, x.effect.after) : c.reach.people(x.effect.n, x.effect.total)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Block>
      )}

      <Block name={c.cycleName} title={c.cycleTitle(Boolean(p.saved))}>
        <ol className="fr-cycle">
          {c.cycle.map((step, i) => (
            <li key={step} data-now={i === c.cycleNow || undefined} data-done={i < c.cycleNow || undefined}>
              <span className="fr-cycle__n">{i + 1}</span>
              <Text weight={i === c.cycleNow ? "semibold" : undefined}>{step}</Text>
            </li>
          ))}
          <li data-back><Text>{c.cycleBack}</Text></li>
        </ol>
        {p.saved && fit && (
          <table className="cba-table fr-prices">
            <thead>
              <tr>
                <th scope="col">{c.colTarget}</th>
                <th scope="col" data-num>{c.colSurvey}</th>
                <th scope="col" data-num>{c.colPeople}</th>
                {fit.diffs.price !== undefined && <th scope="col" data-num>{c.savedPrice(p.concept.price)}</th>}
                {fit.diffs.worry !== undefined && <th scope="col" data-num>{c.savedWorry}</th>}
              </tr>
            </thead>
            <tbody>
              <tr>
                <th scope="row">{p.target}</th>
                <td data-num>{t.people(p.n.target)}</td>
                <td data-num>{t.people(fit.n)}</td>
                {fit.diffs.price !== undefined && <td data-num>{t.pct(fit.diffs.price)}</td>}
                {fit.diffs.worry !== undefined && <td data-num>{t.pct(fit.diffs.worry)}</td>}
              </tr>
            </tbody>
          </table>
        )}
      </Block>
    </article>
  )
}

export function FollowupReport({ payload: p }: { payload: FollowupPayload }) {
  const removed = p.removed.reduce((a, r) => a + r.count, 0)
  const gaps = gapsOf(p)
  const top = bigGaps(p)[0]
  return (
    <article className="cba rr fr">
      <h2 className="cba-headline">{headline(p)}</h2>
      <div className="cba-figures">
        <Figure name={t.figAnswers(p.target)} value={t.people(p.n.target)} caption={t.figAnswersOf(p.n.raw)} />
        <Figure name={t.figRemoved} value={t.people(removed)} caption={removed ? t.figRemovedOf(p.removed.filter((r) => r.count > 0)) : t.figNone} status="ok" />
        {gaps.slice(0, 2).map((d) => (
          <Figure key={d.id} name={t.figGap[d.id]?.(p.concept.price) ?? d.text} value={t.pct(d.actual)} caption={t.figGapOf(d.virtual)} status={Math.abs(d.gap) >= MIN_GAP ? "flag" : "ok"} />
        ))}
      </div>

      <Block name={t.diffName} title={top ? t.diffTitle[top.id] ?? t.diffSame : t.diffSame}
        keys={<>
          <span className="cba-key" data-kind="bar-soft"><i aria-hidden="true" /><Text>{t.keyVirtual(p.track.total)}</Text></span>
          <span className="cba-key" data-kind="bar"><i aria-hidden="true" /><Text>{t.keyActual(p.target, p.n.target)}</Text></span>
        </>}>
        <DiffTable p={p} />
        <Text as="p" display="block">{t.how(p.target, p.n.target, p.diffs.find((d) => d.id === "price")?.actual_n ?? null, p.track.total)}</Text>
      </Block>

      {p.curve.length > 0 && p.best_price != null && (
        <Block name={t.priceName} title={t.priceTitle(p.best_price, p.concept.price)}>
          <div className="cba-split">
            <MoneyChart p={p} />
            <PriceTable p={p} />
          </div>
        </Block>
      )}

      {(p.opinions.bad.length > 0 || p.opinions.good.length > 0) && (
        <div className="rr-grid fr-opinions">
          <OpinionCell name={t.badName} title={t.badTitle} items={p.opinions.bad} />
          <OpinionCell name={t.goodName} title={t.goodTitle} items={p.opinions.good} />
        </div>
      )}
    </article>
  )
}

// ---------- 다시 테스트 결과: 처음과 다시 물은 결과, 빠진 사람과 새로 고른 사람 ----------

const SHOWN = 5

function PeopleTable({ people }: { people: FollowupPerson[] }) {
  const r = t.retest
  return (
    <table className="cba-table fr-people">
      <thead><tr><th scope="col">{r.colWho}</th><th scope="col">{r.colLines}</th><th scope="col">{r.colSaid}</th></tr></thead>
      <tbody>
        {people.slice(0, SHOWN).map((x) => (
          <tr key={x.id}>
            <th scope="row">{x.who}</th>
            <td>{x.lines.length ? x.lines.join(", ") : r.noLines}</td>
            <td>{x.said ? `“${x.said}”` : ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function retestMoves(people: FollowupPeople) {
  const answered = people.people.filter((x) => x.after !== null)
  return {
    stay: answered.filter((x) => x.before && x.after),
    lost: answered.filter((x) => x.before && !x.after),
    gain: answered.filter((x) => !x.before && x.after),
    before: answered.filter((x) => x.before).length,
    after: answered.filter((x) => x.after).length,
    n: answered.length,
  }
}

export function FollowupRetest({ payload: p, people }: { payload: FollowupPayload; people: FollowupPeople }) {
  const r = t.retest
  if (people.status !== "done") return <Text as="p" display="block">{r.running(people.asked, people.total)}</Text>
  const m = retestMoves(people)
  const top = Math.max(m.stay.length, m.lost.length, m.gain.length, 1)
  const rows: BarRow[] = [
    { name: r.stay, share: m.stay.length / top, cells: [t.people(m.stay.length)], tone: "ink" },
    { name: r.lost, share: m.lost.length / top, cells: [t.people(m.lost.length)], tone: "faint", strong: m.lost.length > 0 },
    { name: r.gain, share: m.gain.length / top, cells: [t.people(m.gain.length)], tone: "accent" },
  ]
  return (
    <article className="cba rr fr">
      <h2 className="cba-headline">{r.headline(p.concept.name, m.before, m.after)}</h2>
      <div className="cba-figures">
        <Figure name={r.figBefore} value={t.people(m.before)} caption={r.figOf(m.n)} />
        <Figure name={r.figAfter} value={t.people(m.after)} caption={r.figOf(m.n)} status={m.after < m.before ? "flag" : "ok"} />
        <Figure name={r.figLost} value={t.people(m.lost.length)} caption={r.figLostOf} status={m.lost.length ? "flag" : "ok"} />
        <Figure name={r.figGain} value={t.people(m.gain.length)} caption={r.figGainOf} />
      </div>
      <Block name={r.moveName} title={r.moveTitle(m.lost.length, m.gain.length)}>
        <BarTable label={r.moveName} head={[r.colGroup, r.colCount]} rows={rows} />
      </Block>
      {m.lost.length > 0 && <Block name={r.lostName} title={r.lostTitle}><PeopleTable people={m.lost} /></Block>}
      {m.gain.length > 0 && <Block name={r.gainName} title={r.gainTitle}><PeopleTable people={m.gain} /></Block>}
    </article>
  )
}
