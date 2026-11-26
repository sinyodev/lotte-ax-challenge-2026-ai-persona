/**
 * 테스트 결과의 그림 둘. 형식은 21st.dev의 레퍼런스를 따른다.
 * - 막대 표: "Rank Bars"(이름은 왼쪽 줄, 막대는 같은 칸에서 시작, 값은 오른쪽 줄, 한 줄만 강조)와
 *   "Leaderboard Bars"(칸 머리, 굵은 줄 아래에 따로 둔 줄, 오른쪽으로 맞춘 숫자 칸)
 * - 어디서 왔나: "Partition Bar"(한 줄을 몫대로 나누고 아래에 이름과 값)
 * 색과 글씨 크기는 테마의 값과 css의 클래스로만 정한다. 막대의 길이만 값에서 온다.
 */
import type { CSSProperties } from "react"
import { Text } from "@astryxdesign/core/Text"

export type Tone = "accent" | "ink" | "faint"

/** share는 0~1(막대의 길이), cells는 오른쪽 숫자 칸의 글. */
export type BarRow = { name: string; share: number; tone: Tone; cells: string[]; strong?: boolean }

const width = (share: number) => `${share > 0 ? Math.max(1.5, Math.min(100, share * 100)) : 0}%`

function Row({ r, dots }: { r: BarRow; dots?: boolean }) {
  return (
    <tr data-strong={r.strong || undefined}>
      <th scope="row">
        {dots ? <span className="cba-key" data-kind={r.tone === "faint" ? "bar-soft" : "bar"}><i aria-hidden="true" />{r.name}</span> : r.name}
      </th>
      {!dots && <td className="rr-bars__bar" aria-hidden="true"><span><i data-tone={r.tone} style={{ inlineSize: width(r.share) }} /></span></td>}
      {r.cells.map((c, i) => <td key={i} data-num>{c}</td>)}
    </tr>
  )
}

/**
 * 막대 표. head는 [이름 칸, 숫자 칸…]의 머리.
 * track은 막대의 바탕(전체가 뜻이 있을 때만), mark는 기준선의 자리(0~100), foot은 굵은 줄 아래에 따로 두는 줄(전체).
 * dots는 막대 없이 이름 앞에 색 점만 두는 목록(값이 작아 막대로 견주면 과장되는 곳).
 */
export function BarTable({ label, head, rows, foot, track, mark, dots }: {
  label: string
  head: string[]
  rows: BarRow[]
  foot?: BarRow
  track?: boolean
  mark?: number
  dots?: boolean
}) {
  return (
    <table className="rr-bars" aria-label={label} data-track={track || undefined} data-dots={dots || undefined} data-mark={mark != null || undefined}
      style={mark != null ? ({ "--rr-mark": `${mark}%` } as CSSProperties) : undefined}>
      <thead>
        <tr>
          <th scope="col">{head[0]}</th>
          {!dots && <td aria-hidden="true" />}
          {head.slice(1).map((h) => <th key={h} scope="col" data-num>{h}</th>)}
        </tr>
      </thead>
      <tbody>{rows.map((r) => <Row key={r.name} r={r} dots={dots} />)}</tbody>
      {foot && <tfoot><Row r={foot} /></tfoot>}
    </table>
  )
}

/** 한 줄을 몫대로 나눈 막대. 아래에 몫마다 이름과 값. */
export function PartitionBar({ parts, label }: { parts: { name: string; value: number; label: string; tone: Tone }[]; label: string }) {
  const shown = parts.filter((p) => p.value > 0)
  return (
    <div className="rr-parts" role="img" aria-label={`${label}: ${shown.map((p) => `${p.name} ${p.label}`).join(", ")}`}>
      <div className="rr-parts__bar">
        {shown.map((p) => <i key={p.name} data-tone={p.tone} style={{ flexGrow: p.value }} />)}
      </div>
      <div className="rr-parts__legend">
        {shown.map((p) => (
          <div key={p.name} style={{ flexGrow: p.value }}>
            <span className="cba-key" data-kind={p.tone === "ink" ? "bar" : "bar-soft"}><i aria-hidden="true" /><Text weight="medium">{p.name}</Text></span>
            <Text hasTabularNumbers>{p.label}</Text>
          </div>
        ))}
      </div>
    </div>
  )
}
