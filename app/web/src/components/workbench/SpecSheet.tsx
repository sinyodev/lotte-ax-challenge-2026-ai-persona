/**
 * 제품 사양 묶음(지시서 33, 참가자의 검수로 다시 그림): 규격이 열, 항목이 행인 표.
 * 열의 머리는 규격의 이름(용기 + 용량)이고 표에서 가장 굵다. 값은 오른쪽 맞춤에 고정 폭 숫자.
 * 모든 규격에서 비어 있는 행은 그리지 않는다. 규격과 상관없는 출시·채널은 표 아래에 같은 글씨로 따로 둔다.
 * 이름표와 값은 모두 본문 색이다(회색 작은 글씨는 읽히지 않는다). 아이콘은 두지 않는다.
 * 칠성이가 어림한 유통기한·열량은 행 이름 옆에 "추정값" 표시(spec.estimated).
 * 컨셉 보드에서는 매대에 올릴 규격을 이 표에서 고른다(shelf): 올린 규격의 열은 옅은 면, 머리에 "매대 테스트" 표시,
 * 다른 규격의 머리를 누르면 그 규격으로 바뀐다. 표시의 자리는 모든 열에 처음부터 있어 고르기 전후로 크기가 같다.
 * 좁은 카드(아이디어 카드)에서는 긴 행 이름을 짧은 이름으로 바꿔 규격 둘이 들어가게 한다(컨테이너 크기로).
 */
import type { ReactNode } from "react"
import { Text } from "@astryxdesign/core/Text"
import type { ProductSpec, VariantRow } from "../../chat/contract"
import { specCopy as s } from "../../copy/spec"
import { Tag } from "./OriginTag"

type V = Omit<VariantRow, "label"> & { pack: string }

const VOLUME_RE = /\s*(\d+)\s*m[lL]\b\s*/

/** "슬림캔 250ml" → 슬림캔, 250. */
function parsePack(text: string): { pack: string; volume?: number } {
  const m = VOLUME_RE.exec(text)
  const pack = text.replace(VOLUME_RE, " ").trim()
  return { pack, volume: m ? Number(m[1]) : undefined }
}

export function variantsOf(spec: ProductSpec, pack?: string): V[] {
  if (spec.variants?.length) {
    return spec.variants.map(({ label, ...v }) => {
      const p = parsePack(label)
      return { ...v, pack: p.pack, volume_ml: v.volume_ml ?? p.volume }
    })
  }
  if (!pack) return []
  const p = parsePack(pack)
  return [{ pack: p.pack, volume_ml: p.volume }]
}

/** 열의 머리: "슬림캔 250 mL". */
const headOf = (v: V) => [v.pack, v.volume_ml != null ? s.volume(v.volume_ml) : ""].filter(Boolean).join(" ")
const life = (v: V) =>
  v.shelf_life_months != null ? s.months(v.shelf_life_months) : v.shelf_life_days != null ? s.days(v.shelf_life_days) : null

type Row = { key: string; label: string; short?: string; mark?: string; values: (string | null)[] }

function rowsOf(vs: V[], spec: ProductSpec): Row[] {
  const mark = spec.estimated ? s.estimated : undefined
  const all: Row[] = [
    { key: "factory", label: s.factoryPrice, values: vs.map((v) => (v.factory_price != null ? s.won(v.factory_price) : null)) },
    { key: "retail", label: s.retail, short: s.retailShort, values: vs.map((v) => (v.price != null ? s.won(v.price) : null)) },
    { key: "life", label: s.shelfLife, mark, values: vs.map(life) },
    { key: "kcal", label: s.kcal, mark, values: vs.map((v) => (v.kcal != null ? s.kcalValue(v.kcal) : null)) },
  ]
  return all.filter((r) => r.values.some((x) => x != null))
}

/** 행 이름. 짧은 이름이 있으면 좁을 때만 그것을 보인다. */
function RowLabel({ row, isWide }: { row: Row; isWide: boolean }) {
  // 값의 열이 하나면 이름과 표시를 한 줄에 둔다(열이 둘이면 좁은 카드에서 표시가 아래로 내려간다)
  return (
    <span className={`inline-flex items-center gap-x-1.5 gap-y-0.5 ${isWide ? "flex-nowrap" : "flex-wrap"}`}>
      {row.short ? (
        <>
          <span className="@xs:hidden">
            <Text>{row.short}</Text>
          </span>
          <span className="hidden @xs:inline">
            <Text>{row.label}</Text>
          </span>
        </>
      ) : (
        <Text>{row.label}</Text>
      )}
      {row.mark && <Tag>{row.mark}</Tag>}
    </span>
  )
}

/** 사양 묶음에 그릴 것이 있는가. */
export function hasSpecSheet(spec: ProductSpec, pack?: string): boolean {
  return variantsOf(spec, pack).length > 0 || Boolean(spec.launch || spec.season) || (spec.channels?.length ?? 0) > 0
}

/** 컨셉 보드에서 매대에 올릴 규격 고르기(지시서 33 후속). isLocked면 확정한 뒤라 고를 수 없다. */
export type VariantPick = {
  onPick: (conceptId: string, index: number, label: string) => void
  isDisabled: boolean
  isLocked: boolean
} | null

/** 표에서 매대에 올릴 규격을 고르는 일. 컨셉 보드에서만 넘긴다. */
export type ShelfChoice = { conceptId: string; pick: VariantPick }

/** 열의 머리. 고를 수 있으면 누르는 단추다. 모든 열에 "매대 테스트" 표시의 자리가 있다. */
function ColumnHead({
  v,
  index,
  isShelf,
  showMark,
  onPick,
  disabledMessage,
}: {
  v: V
  index: number
  isShelf: boolean
  showMark: boolean
  onPick?: () => void
  disabledMessage?: string
}) {
  const body = (
    <span className="flex flex-col items-end gap-1">
      {showMark && (
        <span className={isShelf ? undefined : "invisible"} aria-hidden={!isShelf || undefined}>
          <Tag>{s.shelfMark}</Tag>
        </span>
      )}
      <Text weight="bold" justify="end">
        {headOf(v)}
      </Text>
    </span>
  )
  return (
    <th scope="col" data-spec-col={index} data-shelf={isShelf || undefined} className="px-2 pt-2 pb-2 align-bottom">
      {showMark ? (
        <button
          type="button"
          data-spec-col-pick
          className="w-full"
          aria-pressed={isShelf}
          disabled={!onPick}
          title={!onPick ? disabledMessage : undefined}
          onClick={onPick}
        >
          {body}
        </button>
      ) : (
        body
      )}
    </th>
  )
}

/** 표 아래의 출시·채널 한 줄: 이름은 표의 행 이름과 같은 글씨와 같은 열, 값은 규격의 열을 모두 차지한다. */
function ExtraRow({ label, span, children }: { label: string; span: number; children: ReactNode }) {
  return (
    <tr data-spec-tr="extra">
      <th scope="row" className="py-1.5 pr-2 text-left align-top whitespace-nowrap">
        <Text>{label}</Text>
      </th>
      <td colSpan={span} className="px-2 py-1.5 align-top">
        <div className="flex min-w-0 flex-wrap items-center justify-end gap-1.5">{children}</div>
      </td>
    </tr>
  )
}

/** 표에 더 넣는 줄(규격과 상관없는 것: 제품 유형, 보관 등). */
export type ExtraLine = { key: string; label: string; value: string }

/** 규격의 이름: "슬림캔 250 mL"(용기와 용량). 규격이 없으면 빈 글. */
export function specHead(spec: ProductSpec, pack?: string): string {
  const vs = variantsOf(spec, pack)
  const k = vs.length > 1 ? (spec.shelf_variant ?? 0) : 0
  return vs[k] ? headOf(vs[k]) : ""
}

/**
 * 11-25: 규격이 하나면 열 머리 없이 이름과 값의 두 열(withPack이면 첫 줄이 용기와 용량). 규격이 둘 이상인 옛 대화는 지금의 표.
 * lead와 tail은 표의 앞과 끝에 더하는 줄이다(컨셉 보드의 제품 스펙 구역).
 */
export function SpecSheet({
  spec,
  pack,
  shelf,
  withPack = false,
  lead = [],
  tail = [],
}: {
  spec: ProductSpec
  pack?: string
  shelf?: ShelfChoice
  withPack?: boolean
  lead?: ExtraLine[]
  tail?: ExtraLine[]
}) {
  const vs = variantsOf(spec, pack)
  const rows = rowsOf(vs, spec)
  const channels = spec.channels ?? []
  const hasLaunch = Boolean(spec.launch || spec.season)
  const isSingle = vs.length <= 1
  if (isSingle) {
    const packLine = withPack && vs[0] ? headOf(vs[0]) : ""
    if (!packLine && !rows.length && !hasLaunch && !channels.length && !lead.length && !tail.length) return null
    const line = (l: ExtraLine) => (
      <ExtraRow key={l.key} label={l.label} span={1}>
        <Text hasTabularNumbers>{l.value}</Text>
      </ExtraRow>
    )
    return (
      <div data-spec-sheet className="@container">
        <table data-spec-table data-single className="w-full border-collapse">
          <tbody>
            {lead.map(line)}
            {packLine && line({ key: "pack", label: s.pack, value: packLine })}
            {rows.map((r) => (
              <tr key={r.key} data-spec-tr={r.key}>
                <th scope="row" className="py-1.5 pr-2 text-left align-top whitespace-nowrap">
                  <RowLabel row={r} isWide />
                </th>
                <td className="px-2 py-1.5 text-right align-top whitespace-nowrap">
                  <Text hasTabularNumbers>{r.values[0] ?? ""}</Text>
                </td>
              </tr>
            ))}
            {hasLaunch && (
              <ExtraRow label={s.launch} span={1}>
                {spec.launch && <Text hasTabularNumbers>{s.launchValue(spec.launch)}</Text>}
                {spec.season && (spec.launch ? <Tag>{spec.season}</Tag> : <Text>{spec.season}</Text>)}
              </ExtraRow>
            )}
            {channels.length > 0 && (
              <ExtraRow label={s.channels} span={1}>
                {channels.map((c) => (
                  <Tag key={c}>{c}</Tag>
                ))}
              </ExtraRow>
            )}
            {tail.map(line)}
          </tbody>
        </table>
      </div>
    )
  }
  // 매대에 올릴 규격: 컨셉 보드에서, 규격이 둘 이상일 때만
  const canChoose = Boolean(shelf) && (spec.variants?.length ?? 0) > 1
  const shelfIndex = canChoose ? (spec.shelf_variant ?? 0) : -1
  const pick = shelf?.pick ?? null
  const isOpen = Boolean(pick) && !pick!.isDisabled
  const span = Math.max(vs.length, 1)
  return (
    <div data-spec-sheet className="@container">
      <table data-spec-table className="w-full border-collapse">
        {vs.length > 0 && (
          <thead>
            <tr>
              <td />
              {vs.map((v, i) => (
                <ColumnHead
                  key={i}
                  v={v}
                  index={i}
                  isShelf={i === shelfIndex}
                  showMark={canChoose}
                  disabledMessage={pick?.isLocked ? s.lockedShelf : undefined}
                  onPick={
                    canChoose && isOpen
                      ? () => {
                          if (i !== shelfIndex) pick!.onPick(shelf!.conceptId, i, spec.variants![i].label)
                        }
                      : undefined
                  }
                />
              ))}
            </tr>
          </thead>
        )}
        {(rows.length > 0 || hasLaunch || channels.length > 0 || lead.length > 0 || tail.length > 0) && (
          <tbody>
            {lead.map((l) => (
              <ExtraRow key={l.key} label={l.label} span={span}>
                <Text>{l.value}</Text>
              </ExtraRow>
            ))}
            {rows.map((r) => (
              <tr key={r.key} data-spec-tr={r.key}>
                <th scope="row" className="py-1.5 pr-2 text-left align-top whitespace-nowrap">
                  <RowLabel row={r} isWide={vs.length <= 1} />
                </th>
                {r.values.map((x, i) => (
                  <td key={i} data-shelf={i === shelfIndex || undefined} className="px-2 py-1.5 text-right align-top whitespace-nowrap">
                    <Text hasTabularNumbers>{x ?? ""}</Text>
                  </td>
                ))}
              </tr>
            ))}
            {hasLaunch && (
              <ExtraRow label={s.launch} span={span}>
                {spec.launch && <Text hasTabularNumbers>{s.launchValue(spec.launch)}</Text>}
                {spec.season && (spec.launch ? <Tag>{spec.season}</Tag> : <Text>{spec.season}</Text>)}
              </ExtraRow>
            )}
            {channels.length > 0 && (
              <ExtraRow label={s.channels} span={span}>
                {channels.map((c) => (
                  <Tag key={c}>{c}</Tag>
                ))}
              </ExtraRow>
            )}
            {tail.map((l) => (
              <ExtraRow key={l.key} label={l.label} span={span}>
                <Text>{l.value}</Text>
              </ExtraRow>
            ))}
          </tbody>
        )}
      </table>
    </div>
  )
}
