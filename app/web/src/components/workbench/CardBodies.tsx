/**
 * 작업대 카드의 몸통. 카드 종류(약속 2절 CardKind)마다 하나.
 * 제대로 그리는 것은 1부의 brief, evidence, ideas, concepts다(약속 v1.3). 2부의 shelf-run, result는 ShelfCards.tsx(지시서 15).
 * report는 받은 값을 단순한 목록으로 보여 주는 임시 모습이다. improve는 ImproveCard.tsx(지시서 17).
 */
import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type MouseEvent,
  type ReactNode,
  type RefObject,
} from "react"
import { Button } from "@astryxdesign/core/Button"
import { Card } from "@astryxdesign/core/Card"
import { Divider } from "@astryxdesign/core/Divider"
import { Heading } from "@astryxdesign/core/Heading"
import { Icon } from "@astryxdesign/core/Icon"
import { HStack } from "@astryxdesign/core/HStack"
import { Link } from "@astryxdesign/core/Link"
import { Text } from "@astryxdesign/core/Text"
import { VStack } from "@astryxdesign/core/VStack"
import { copy } from "../../copy"
import type { Container } from "../../fixtures/confirmedConcepts"
import { CheckBox } from "../chat/ChatParts"
import { ConceptVisual } from "./ConceptVisual"
import { SourceTag, Tag } from "./OriginTag"
import { SpecSheet, specHead, type ExtraLine, type VariantPick } from "./SpecSheet"
import type { CardReply, CardSay } from "./ShelfCards"
import { specCopy } from "../../copy/spec"
import { boardCopy } from "../../copy/board"
import "./board.css"
import type {
  BriefPayload,
  ConceptItem,
  ConceptsPayload,
  EvidenceItem,
  EvidencePayload,
  IdeaItem,
  IdeasPayload,
  ReportPayload,
} from "../../chat/contract"

export { ExploreBody } from "./ExploreCard"

const w = copy.workbench

/** 목록의 차례를 A, B, C로 적는다(대본의 표와 칩이 쓰는 이름). */
const letter = (i: number) => String.fromCharCode(65 + i)

const FRESH_MS = 1600

/** 처음 그린 뒤로 새로 생긴 항목의 id들. 잠깐 들고 있다가 놓는다. */
function useFreshIds(ids: string[]) {
  const seen = useRef<Set<string> | null>(null)
  const [fresh, setFresh] = useState<string[]>([])
  const key = ids.join("\u0000")
  useEffect(() => {
    if (seen.current === null) {
      seen.current = new Set(ids)
      return
    }
    const added = ids.filter((i) => !seen.current!.has(i))
    added.forEach((i) => seen.current!.add(i))
    if (added.length === 0) return
    setFresh(added)
    const t = window.setTimeout(() => setFresh([]), FRESH_MS)
    return () => window.clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  return fresh
}

/** 처음 그린 뒤로 값이 바뀌거나 새로 생긴 칸의 이름들. 잠깐 들고 있다가 놓는다. */
function useChangedKeys(values: Record<string, string>) {
  const prev = useRef<Record<string, string> | null>(null)
  const [changed, setChanged] = useState<string[]>([])
  const key = JSON.stringify(values)
  useEffect(() => {
    const before = prev.current
    prev.current = values
    if (before === null) return
    const keys = Object.keys(values).filter((k) => before[k] !== values[k])
    if (keys.length === 0) return
    setChanged(keys)
    const t = window.setTimeout(() => setChanged([]), FRESH_MS)
    return () => window.clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  return changed
}

/**
 * 순서가 바뀌거나 앞의 것이 빠져 자리가 옮겨진 항목을 옛 자리에서 새 자리로 미끄러지게 한다(FLIP).
 * 자리는 묶음 안에서 잰다(스크롤과 상관없다). 움직임의 길이는 테마(overrides.css의 data-flip-id)에 있다.
 */
function useFlip(container: RefObject<HTMLElement | null>, key: string) {
  const prev = useRef(new Map<string, { x: number; y: number }>())
  useLayoutEffect(() => {
    const box = container.current
    if (!box) return
    const origin = box.getBoundingClientRect()
    const next = new Map<string, { x: number; y: number }>()
    const moved: HTMLElement[] = []
    box.querySelectorAll<HTMLElement>("[data-flip-id]").forEach((el) => {
      const id = el.dataset.flipId!
      const r = el.getBoundingClientRect()
      const pos = { x: r.left - origin.left, y: r.top - origin.top }
      next.set(id, pos)
      const before = prev.current.get(id)
      if (!before || (before.x === pos.x && before.y === pos.y)) return
      el.style.transition = "none"
      el.style.transform = `translate(${before.x - pos.x}px, ${before.y - pos.y}px)`
      moved.push(el)
    })
    prev.current = next
    if (moved.length === 0) return
    const raf = requestAnimationFrame(() =>
      moved.forEach((el) => {
        el.style.transition = ""
        el.style.transform = ""
      }),
    )
    return () => cancelAnimationFrame(raf)
  }, [container, key])
}

/** 방금 고쳐진 칸 옆에 남는 작은 점. 모양은 overrides.css의 data-changed-dot. */
function ChangedDot() {
  return <span data-changed-dot role="img" aria-label={w.changedMark} />
}

/**
 * 방금 고쳐진 칸(changed). 값이 바뀌어 다시 그려질 때 잠깐 옅은 면이 깔렸다가 사라진다(값을 key로 써서 다시 붙인다).
 * 고쳐지지 않은 칸은 아무것도 더하지 않는다.
 */
function ChangedArea({ isChanged, value, children }: { isChanged: boolean; value: string; children: ReactNode }) {
  return (
    <div key={isChanged ? value : undefined} data-changed={isChanged || undefined}>
      {children}
    </div>
  )
}

/**
 * 찾아본 것의 한 항목: 왼쪽에 출처의 이름(웹에서 찾은 것은 점선에 링크), 오른쪽에 본문 한 문장,
 * 그 아래 날짜, 주의(note)는 작은 회색 글씨 한 줄.
 */
function EvidenceRow({ item, isFresh }: { item: EvidenceItem; isFresh: boolean }) {
  const isWeb = item.origin === "web"
  return (
    <li data-evidence-item data-origin-kind={item.origin} data-fresh={isFresh || undefined}>
      <div className="flex flex-col gap-2 @lg:flex-row @lg:gap-4">
        <div className="min-w-0 shrink-0 @lg:w-40">
          {item.origin === "internal" && item.url?.startsWith("/ideas?idea=") ? (
            <Link href={item.url} hasUnderline type="supporting" color="primary">{item.source}</Link>
          ) : <SourceTag source={item.source} isWeb={isWeb} url={item.url} />}
        </div>
        <div className="min-w-0 flex-1">
          <VStack gap={1}>
            <ClampText text={item.text} />
            {item.date && (
              <Text type="supporting" hasTabularNumbers>
                {item.date}
              </Text>
            )}
            {item.note && (
              <Text type="supporting" maxLines={1}>
                {item.note}
              </Text>
            )}
          </VStack>
        </div>
      </div>
    </li>
  )
}

/** 본문의 줄 수. 넘으면 자르고, 누르면 펼친다. */
const CLAMP_LINES = 3

/** 길면 세 줄에서 자르고 누르면 펼치는 글. 잘리지 않을 만큼 짧으면 누를 수 없다. */
function ClampText({ text }: { text: string }) {
  const box = useRef<HTMLDivElement>(null)
  const [isOpen, setIsOpen] = useState(false)
  const [isLong, setIsLong] = useState(false)
  useLayoutEffect(() => {
    const el = box.current?.firstElementChild as HTMLElement | null
    if (!el || isOpen) return
    const check = () => setIsLong(el.scrollHeight > el.clientHeight + 1)
    check()
    const ro = new ResizeObserver(check)
    ro.observe(el)
    return () => ro.disconnect()
  }, [text, isOpen])
  const canToggle = isLong || isOpen
  const toggle = () => setIsOpen((o) => !o)
  return (
    <div
      ref={box}
      data-clamp={canToggle ? (isOpen ? "open" : "closed") : undefined}
      role={canToggle ? "button" : undefined}
      tabIndex={canToggle ? 0 : undefined}
      aria-expanded={canToggle ? isOpen : undefined}
      aria-label={canToggle ? `${text} (${isOpen ? w.collapse : w.expand})` : undefined}
      onClick={canToggle ? toggle : undefined}
      onKeyDown={
        canToggle
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault()
                toggle()
              }
            }
          : undefined
      }
    >
      <Text as="p" display="block" maxLines={isOpen ? 0 : CLAMP_LINES} hasTruncateTooltip={false}>
        {text}
      </Text>
    </div>
  )
}

/**
 * 찾아본 것(약속 v1.3 evidence). 항목마다 출처의 이름, 본문 한 문장, 날짜, 주의.
 * 항목이 늘어나면 새 항목만 잠깐 강조한다.
 */
export function EvidenceBody({ payload }: { payload: EvidencePayload }) {
  const fresh = useFreshIds(payload.items.map((i) => i.id))
  return (
    <div className="@container">
      <ul aria-label={w.evidenceLabel} className="flex flex-col">
        {payload.items.map((it) => (
          <EvidenceRow key={it.id} item={it} isFresh={fresh.includes(it.id)} />
        ))}
      </ul>
    </div>
  )
}

/** 브리프에 보일 것이 있는지. 정해진 칸도 기획자의 생각도 없으면 카드 자체를 그리지 않는다. */
export function hasBriefContent(p: BriefPayload | null | undefined) {
  if (!p) return false
  return p.fields.some((f) => f.state === "set" && f.value) || (p.thoughts?.length ?? 0) > 0
}

/**
 * 기획 브리프(약속 v1.3): 양식이 아니라 대화에서 나온 것의 요약. 정해진 칸만 이름(작은 회색)과 값, 덧말은 값 옆에 작은 글씨.
 * 아래에 기획자의 생각을 작은 이름표로. 방금 바뀐 칸은 잠깐 옅은 면이 깔린다.
 */
export function BriefBody({ payload }: { payload: BriefPayload }) {
  const set = payload.fields.filter((f) => f.state === "set" && f.value)
  const thoughts = payload.thoughts ?? []
  const values: Record<string, string> = Object.fromEntries(set.map((f) => [f.key, `${f.value}\u0000${f.note ?? ""}`]))
  values.__thoughts = thoughts.join("\u0000")
  const changed = useChangedKeys(values)
  return (
    <VStack gap={3}>
      {set.map((f) => (
        <div key={f.key} data-brief-row data-fresh={changed.includes(f.key) || undefined}>
          <HStack gap={4} vAlign="start">
            <div className="w-24 shrink-0">
              <Text type="supporting">{f.label}</Text>
            </div>
            <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-2 gap-y-0.5">
              <Text weight="medium">{f.value}</Text>
              {f.note && <Text type="supporting">{f.note}</Text>}
            </div>
          </HStack>
        </div>
      ))}
      {thoughts.length > 0 && (
        <div data-brief-row data-fresh={changed.includes("__thoughts") || undefined}>
          <HStack gap={4} vAlign="start">
            <div className="w-24 shrink-0">
              <Text type="supporting">{w.briefThoughts}</Text>
            </div>
            <ul className="flex min-w-0 flex-1 flex-wrap gap-1.5">
              {thoughts.map((t) => (
                <li key={t} className="min-w-0 max-w-full">
                  <Tag>{t}</Tag>
                </li>
              ))}
            </ul>
          </HStack>
        </div>
      )}
    </VStack>
  )
}

/**
 * 카드 안에서 고르기(약속 v1.2 choices.on_card)의 상태. null이면 고르지 않는 카드다.
 * isLocked면 보낸 뒤라 누를 수 없고, 고른 것만 네모 칸이 채워진 채 남는다.
 */
export type PickMode = {
  selected: string[]
  isLocked: boolean
  onToggle?: (itemId: string) => void
} | null

/**
 * 고를 수 있는 항목. 왼쪽 위에 네모 칸, 고르면 테두리가 진해지고 칸이 채워진다.
 * 칸의 자리는 늘 있어서 고르기 전후로 크기가 같다. 모양은 테마(overrides.css의 data-pickable)에 있다.
 */
function Pickable({ id, pick, children }: { id: string; pick: PickMode; children: ReactNode }) {
  if (!pick) return <div data-pick-frame className="h-full">{children}</div>
  const isPicked = pick.selected.includes(id)
  const canToggle = !pick.isLocked && pick.onToggle
  return (
    <div
      data-pick-frame
      data-pickable
      data-picked={isPicked || undefined}
      data-locked={pick.isLocked || undefined}
      className="h-full"
      role="checkbox"
      aria-checked={isPicked}
      aria-disabled={pick.isLocked || undefined}
      tabIndex={canToggle ? 0 : -1}
      onClick={canToggle ? () => pick.onToggle!(id) : undefined}
      onKeyDown={
        canToggle
          ? (e) => {
              if (e.key === " " || e.key === "Enter") {
                e.preventDefault()
                pick.onToggle!(id)
              }
            }
          : undefined
      }
    >
      <PickContext.Provider value={{ isPicked, isHidden: pick.isLocked && !isPicked }}>{children}</PickContext.Provider>
    </div>
  )
}

/** 고를 수 있는 항목 안에서 네모 칸이 놓이는 자리(카드 제목 앞). 고르지 않는 카드에서는 아무것도 없다. */
const PickContext = createContext<{ isPicked: boolean; isHidden: boolean } | null>(null)
function PickBox() {
  const ctx = useContext(PickContext)
  if (!ctx) return null
  return (
    <div className={ctx.isHidden ? "invisible" : undefined}>
      <CheckBox isChecked={ctx.isPicked} />
    </div>
  )
}

/** 고르는 차례의 보드 머리 띠 오른쪽: "눌러서 고르기"나 "골랐어요". 고르는 차례가 아니면 fallback(확정 표시). */
function PickHint({ fallback }: { fallback: ReactNode }) {
  const ctx = useContext(PickContext)
  if (!ctx || ctx.isHidden) return <>{fallback}</>
  return (
    <span className="ml-auto">
      <Text weight="medium">{ctx.isPicked ? boardCopy.picked : boardCopy.pickHint}</Text>
    </span>
  )
}

/** 아이디어마다 맛, 용기와 용량, 특징이 다른 안과 다른지. 모든 안이 같으면 흐리게 둔다. */
function differingKeys(items: IdeaItem[]) {
  const vals = (k: "flavor" | "pack" | "features") =>
    items.map((it) => (k === "features" ? it.features.join(", ") : it[k]))
  const differs = (k: "flavor" | "pack" | "features") => {
    const v = vals(k)
    return v.map((x) => v.some((y) => y !== x))
  }
  return { flavor: differs("flavor"), pack: differs("pack"), features: differs("features") }
}

/**
 * 카드에서 보내는 일(약속 v1.3: 남기기, 빼기). 누르면 기획자의 말로 보낸다.
 * isDisabled면 칠성이가 말하는 중이라 누를 수 없다. null이면 버튼을 그리지 않는다.
 */
export type IdeaActions = { onSay: (text: string, reply?: CardReply) => void; isDisabled: boolean } | null

/** 카드의 "컨셉으로 만들기"가 보내는 metadata.reply: 대화의 같은 버튼과 같은 id(make-concepts)에 그 아이디어의 id를 붙인다. */
const MAKE_CONCEPT_ID = "make-concepts"

/**
 * 카드 아래의 버튼 둘: 이 아이디어를 컨셉으로 만들기, 보드에서 빼기. 무엇을 하는지 글로 적는다(남기기는 없앴다. 참가자의 검수).
 * 여러 개를 고르는 차례(isHidden: 칠성이가 어느 아이디어인지 물었을 때)에는 자리만 남기고 숨긴다. 그때는 체크 칸으로 고른다.
 */
function IdeaCardButtons({ item, actions, isHidden }: { item: IdeaItem; actions: NonNullable<IdeaActions>; isHidden: boolean }) {
  const say = (text: string, reply?: CardReply) => (e: MouseEvent) => {
    e.stopPropagation()
    actions.onSay(text, reply)
  }
  // 11-25: 규격별로 나눈 카드는 이름이 같아서 대화에 남는 말에 규격을 붙인다
  const head = (item.variants?.length ?? 0) === 1 ? specHead(item, item.pack) : ""
  const name = head ? `${item.name} ${head}` : item.name
  return (
    <div
      data-idea-actions
      className={`flex flex-wrap items-center gap-2 ${isHidden ? "invisible" : ""}`}
      aria-hidden={isHidden || undefined}
      onKeyDown={(e) => e.stopPropagation()}
    >
      <Button
        label={w.ideaMakeConcept}
        variant="secondary"
        size="sm"
        isDisabled={actions.isDisabled || isHidden}
        onClick={say(w.makeConceptSay(name), { to: "idea-card", ids: [MAKE_CONCEPT_ID, item.id] })}
      />
      <Button
        label={w.ideaRemove}
        variant="ghost"
        size="sm"
        isDisabled={actions.isDisabled || isHidden}
        onClick={say(w.removeSay(name))}
      />
    </div>
  )
}

/**
 * 11-25: 아이디어 카드의 머리 아래, 이 카드의 규격(굵게)과 권장 소비자가(가격표처럼 크게).
 * 규격이 둘 이상인 옛 아이디어는 표의 열이 규격을 보이므로 그리지 않는다.
 */
function IdeaSpecHead({ item }: { item: IdeaItem }) {
  if ((item.variants?.length ?? 0) > 1) return null
  const head = specHead(item, item.pack)
  const price = item.variants?.[0]?.price
  if (!head) return null
  return (
    <div data-idea-spec-head className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
      <Text size="lg" weight="bold">
        {head}
      </Text>
      {price != null && (
        <Text size="xl" weight="bold" hasTabularNumbers>
          {specCopy.won(price)}
        </Text>
      )}
    </div>
  )
}

function IdeaCard({
  item,
  index,
  diff,
  actions,
}: {
  item: IdeaItem
  index: number
  diff: { flavor: boolean; pack: boolean; features: boolean }
  actions: IdeaActions
}) {
  const changed = new Set(item.changed ?? [])
  const isMine = item.by === "planner"
  const isPicking = useContext(PickContext) !== null
  return (
    <div data-idea-card data-kept={item.kept || undefined} className="h-full">
      <Card padding={4} height="100%">
        <VStack gap={3}>
          <HStack gap={2} vAlign="start" justify="between">
            <HStack gap={2} vAlign="start">
              <PickBox />
              <Text weight="semibold" color="secondary">
                {letter(index)}
              </Text>
              <ChangedArea isChanged={changed.has("name")} value={item.name}>
                <span className="inline-flex items-center gap-1.5">
                  <Heading level={3}>{item.name}</Heading>
                  {changed.has("name") && <ChangedDot />}
                </span>
              </ChangedArea>
            </HStack>
          </HStack>
          <IdeaSpecHead item={item} />
          {(isMine || item.kept) && (
            <HStack gap={1.5} vAlign="center" wrap="wrap">
              {isMine && <Tag>{w.ideaMine}</Tag>}
              {item.kept && (
                <span data-kept-mark className="inline-flex">
                  <Tag>{w.ideaKept}</Tag>
                </span>
              )}
            </HStack>
          )}
          <ChangedArea isChanged={changed.has("flavor")} value={item.flavor}>
            <span className="inline-flex items-center gap-1.5">
              {changed.has("flavor") && <ChangedDot />}
              <Text weight={diff.flavor ? "semibold" : "medium"}>{item.flavor}</Text>
            </span>
          </ChangedArea>
          <ChangedArea isChanged={changed.has("line")} value={item.line}>
            <div className="flex items-baseline gap-1.5">
              {changed.has("line") && <ChangedDot />}
              <Text>{item.line}</Text>
            </div>
          </ChangedArea>
          {item.features.length > 0 && (
            <ChangedArea isChanged={changed.has("features")} value={item.features.join("\u0000")}>
              <ul className="flex flex-col gap-1">
                {item.features.map((f, k) => (
                  <li key={k} className="flex items-start gap-2">
                    <span className="pt-0.5">
                      <Icon icon="check" size="sm" color="inherit" />
                    </span>
                    <Text weight={diff.features ? "medium" : "normal"}>{f}</Text>
                    {k === 0 && changed.has("features") && <ChangedDot />}
                  </li>
                ))}
              </ul>
            </ChangedArea>
          )}
          <Divider />
          <ChangedArea isChanged={changed.has("pack")} value={item.pack}>
            {/* 옛 대화에는 표시가 없다. 칠성이가 낸 아이디어면 어림한 값으로 본다 */}
            <SpecSheet spec={{ ...item, estimated: item.estimated ?? item.by === "chilseong" }} pack={item.pack} />
          </ChangedArea>
          {actions && <IdeaCardButtons item={item} actions={actions} isHidden={isPicking} />}
        </VStack>
      </Card>
    </div>
  )
}

/**
 * 아이디어 보드(약속 v1.3). 같은 카드가 차례마다 다시 와서 항목이 늘거나 줄거나 고쳐진다.
 * 나란한 카드, 좁으면 세로로 쌓는다(컨테이너 크기로 바뀐다). 새로 들어온 카드는 잠깐 강조되고, 빠진 카드는 사라지고,
 * 순서가 바뀐 카드는 옛 자리에서 미끄러져 온다. pick이 있으면(고르는 차례) 카드를 눌러 고른다.
 */
export function IdeasBody({
  payload,
  pick = null,
  actions = null,
}: {
  payload: IdeasPayload
  pick?: PickMode
  actions?: IdeaActions
}) {
  const diffs = differingKeys(payload.items)
  const ids = payload.items.map((i) => i.id)
  const fresh = useFreshIds(ids)
  const grid = useRef<HTMLDivElement>(null)
  useFlip(grid, ids.join("\u0000"))
  const cols = payload.items.length >= 3 ? "@3xl:grid-cols-3" : "@2xl:grid-cols-2"
  return (
    <div className="@container">
      <VStack gap={4}>
        {payload.basis && (
          <VStack gap={0.5}>
            <Text type="supporting">{w.ideasBasis}</Text>
            <Text weight="medium">{payload.basis}</Text>
          </VStack>
        )}
        <div ref={grid} className={`grid grid-cols-1 gap-3 ${cols}`}>
          {payload.items.map((it, i) => (
            <div key={it.id} data-flip-id={it.id} data-fresh={fresh.includes(it.id) || undefined} className="flex">
              <VStack gap={1.5} width="100%">
                <div className="flex-1">
                  <Pickable id={it.id} pick={pick}>
                    <IdeaCard
                      item={it}
                      index={i}
                      diff={{ flavor: diffs.flavor[i], pack: diffs.pack[i], features: diffs.features[i] }}
                      actions={actions}
                    />
                  </Pickable>
                </div>
                {it.diff && (
                  <div className="px-1">
                    <Text type="supporting">{it.diff}</Text>
                  </div>
                )}
              </VStack>
            </div>
          ))}
        </div>
      </VStack>
    </div>
  )
}

/** 용기와 용량("250ml 캔")에서 용기를 읽는다. 모르면 null(그림 자리에 면만). */
export function containerOf(pack: string | undefined): Container | null {
  if (!pack) return null
  const names = copy.home.test.containers
  const found = (Object.keys(names) as Container[]).find((c) => pack.split(" ").includes(names[c]))
  return found ?? null
}

/** 고쳐진 글: 값이 바뀔 때 잠깐 옅은 면, 옆에 작은 점. */
function FreshLine({ isChanged, value, children }: { isChanged: boolean; value: string; children: ReactNode }) {
  return (
    <ChangedArea isChanged={isChanged} value={value}>
      <span className="inline-flex items-center gap-1.5">
        {children}
        {isChanged && <ChangedDot />}
      </span>
    </ChangedArea>
  )
}

/**
 * 컨셉 보드의 줄(spec)을 나누는 key. 11-25: 맛·탄산·당은 위쪽의 "믿을 수 있는 근거"에, 제품 유형·보관은 아래쪽 제품 스펙 표에,
 * 타깃·음용 상황과 비교 제품은 제품 스펙 구역의 묶음에 둔다. 여기에 없는 key(옛 형식의 용기와 용량, 판매 채널 등)는 표의 끝 줄로 남긴다.
 */
const RTB_KEYS = ["flavor", "carbonation", "sugar_caffeine"]
const TABLE_LEAD_KEYS = ["type"]
const TABLE_TAIL_KEYS = ["storage"]
const WHO_KEYS = ["target", "occasion"]
const RIVAL_KEYS = ["rivals", "own"]
const POD_KEY = "pod"
/** 옛 형식에서 표가 대신하는 줄(가격은 가격표가 보인다) */
const HIDDEN_KEYS = ["price"]
const KNOWN_KEYS = new Set([...RTB_KEYS, ...TABLE_LEAD_KEYS, ...TABLE_TAIL_KEYS, ...WHO_KEYS, ...RIVAL_KEYS, POD_KEY, ...HIDDEN_KEYS])

const b = boardCopy

/**
 * 보드의 한 묶음. 작은 제목(있으면)과 내용. align은 나란한 보드끼리 같은 묶음의 높이를 맞추는 이름이다(useAlignRows).
 * isGap이면 다른 보드에만 있는 묶음의 빈 자리다(선도 여백도 없이 높이만 맞춘다).
 */
function BoardSection({
  align,
  title,
  isGap = false,
  children,
}: {
  align: string
  title?: string
  isGap?: boolean
  children?: ReactNode
}) {
  if (isGap) return <div data-board-gap data-align={align} />
  return (
    <section data-board-section data-align={align} className="flex flex-col gap-3 px-6 py-4">
      {title && <Heading level={4}>{title}</Heading>}
      {children}
    </section>
  )
}

/** 매대에 올릴 규격의 가격과 이름: 가격표처럼 위에 굵은 선, 큰 가격 옆에 용기와 용량. */
function PriceTag({ item, changed }: { item: ConceptItem; changed: Set<string> }) {
  const v = item.variants?.[item.shelf_variant ?? 0]
  const price = v?.price != null ? specCopy.won(v.price) : item.price
  const pack = specHead(item, item.pack)
  if (!price) return null
  return (
    <ChangedArea isChanged={changed.has("price") || changed.has("variants")} value={`${price}\u0000${pack}`}>
      <div data-price-tag className="flex flex-wrap items-baseline gap-x-3 pt-3">
        <Text size="xl" weight="bold" hasTabularNumbers>
          {price}
        </Text>
        {pack && <Text weight="medium">{pack}</Text>}
      </div>
    </ChangedArea>
  )
}

type Spec = { key: string; label: string; value: string }

/** 이름 아래 값(타깃, 음용 상황, 경쟁 제품처럼 나란한 칸). 값 안의 줄바꿈은 줄을 나눠 그린다. */
function SpecBlock({ row, changed, differs }: { row: Spec; changed: Set<string>; differs: Set<string> }) {
  return (
    <ChangedArea isChanged={changed.has(row.key)} value={row.value}>
      <div className="flex min-w-0 flex-col gap-1">
        <span className="inline-flex items-center gap-1.5">
          <Text>{row.label}</Text>
          {changed.has(row.key) && <ChangedDot />}
        </span>
        {row.value.split("\n").map((line, k) => (
          <Text key={k} weight={differs.has(row.key) ? "semibold" : "medium"} hasTabularNumbers>
            {line}
          </Text>
        ))}
      </div>
    </ChangedArea>
  )
}

/** 컨셉끼리 값이 다른 줄의 key. 컨셉이 하나뿐이면 없다(줄이 없는 컨셉은 빈 값으로 본다). */
function differingSpecKeys(items: ConceptItem[]): Set<string> {
  const out = new Set<string>()
  if (items.length < 2) return out
  const keys = new Set(items.flatMap((it) => (it.spec ?? []).map((r) => r.key)))
  for (const k of keys) {
    const vals = items.map((it) => it.spec?.find((r) => r.key === k)?.value ?? "")
    if (vals.some((v) => v !== vals[0])) out.add(k)
  }
  return out
}

/** 보드에 그릴 것의 몫. 나란한 보드 가운데 하나라도 있으면 다른 보드에도 빈 자리를 둔다(같은 높이에서 시작하게). */
type BoardShape = { insight: boolean; rtb: boolean; who: boolean; compare: boolean }

function rowsOfItem(item: ConceptItem) {
  const rows = item.spec ?? []
  const byKeys = (keys: string[]) => keys.map((k) => rows.find((r) => r.key === k)).filter((r): r is Spec => Boolean(r))
  return {
    rtb: byKeys(RTB_KEYS),
    pod: rows.find((r) => r.key === POD_KEY),
    lead: byKeys(TABLE_LEAD_KEYS),
    tail: [...byKeys(TABLE_TAIL_KEYS), ...rows.filter((r) => !KNOWN_KEYS.has(r.key))],
    who: byKeys(WHO_KEYS),
    rivals: byKeys(RIVAL_KEYS),
  }
}

function shapeOf(items: ConceptItem[]): BoardShape {
  const parts = items.map(rowsOfItem)
  return {
    insight: items.some((it) => Boolean(it.insight)),
    rtb: parts.some((p) => p.rtb.length > 0 || Boolean(p.pod)),
    who: parts.some((p) => p.who.length > 0),
    compare: parts.some((p) => p.rivals.length > 0),
  }
}

/** 근거의 칩: 맛은 그대로, 탄산은 "탄산 보통", 당·카페인은 그대로. 줄바꿈은 띄어 쓴다. */
function rtbChip(r: Spec): string {
  const v = r.value.replace(/\n/g, " ")
  return r.key === "carbonation" ? b.carbonation(v) : v
}

/**
 * 컨셉 보드 한 장(11-25, 세로형). 위쪽은 소비자에게 보이는 보드: 제품 그림 → 제품명과 헤드라인 → 소비자 인식 → 혜택 →
 * 믿을 수 있는 근거 → 가격표. 아래쪽은 바탕이 다른 기획자용 구역 "제품 스펙": 표, 타깃과 음용 상황, 매대에서 비교되는 제품.
 * 머리에 보드 번호와 규격, 확정한 보드면 표시.
 */
function ConceptBoard({
  item,
  index,
  shape,
  differs,
  pickVariant = null,
  chatId,
}: {
  item: ConceptItem
  index: number
  shape: BoardShape
  differs: Set<string>
  pickVariant?: VariantPick
  chatId?: string
}) {
  const changed = new Set(item.changed ?? [])
  const parts = rowsOfItem(item)
  const head = specHead(item, item.pack)
  const points = item.points ?? []
  const lead: ExtraLine[] = parts.lead.map((r) => ({ ...r, label: r.key === "type" ? b.type : r.label }))
  const tail: ExtraLine[] = parts.tail.map((r) => ({ ...r, label: r.key === "storage" ? b.storage : r.label }))
  return (
    <div data-concept-card data-board className="h-full" role="group" aria-label={b.label(index + 1)}>
      <Card padding={0} height="100%">
        <div className="@container flex h-full flex-col">
          <div data-board-head data-align="board-head" className="flex items-center gap-3 px-6 py-3">
            <PickBox />
            <Text weight="bold">{b.number(index + 1)}</Text>
            {head && <Text weight="bold">{head}</Text>}
            <PickHint fallback={
              <span className={`ml-auto ${item.confirmed ? "" : "invisible"}`} aria-hidden={!item.confirmed || undefined}>
                <Tag>{b.confirmed}</Tag>
              </span>
            } />
          </div>
          {/* 위쪽: 소비자에게 보이는 컨셉 보드 */}
          <div data-board-face className="flex flex-col">
            <div data-align="visual" className="px-6 pt-5">
              <ConceptVisual chatId={chatId} concept={item} />
            </div>
            <BoardSection align="title">
              <div className="flex flex-col gap-2">
                <FreshLine isChanged={changed.has("name")} value={item.name}>
                  <Heading level={1}>{item.name}</Heading>
                </FreshLine>
                {item.headline && (
                  <FreshLine isChanged={changed.has("headline")} value={item.headline}>
                    <Text size="lg" weight="medium">
                      {item.headline}
                    </Text>
                  </FreshLine>
                )}
              </div>
            </BoardSection>
            {shape.insight && (
              <BoardSection align="insight" isGap={!item.insight}>
                <FreshLine isChanged={changed.has("insight")} value={item.insight ?? ""}>
                  <div data-board-insight className="pl-4">
                    <Text>{item.insight}</Text>
                  </div>
                </FreshLine>
              </BoardSection>
            )}
            {(points.length > 0 || item.benefit) && (
              <BoardSection align="benefits" title={b.benefits}>
                {item.benefit && (
                  <FreshLine isChanged={changed.has("benefit")} value={item.benefit}>
                    <Text weight="semibold">{item.benefit}</Text>
                  </FreshLine>
                )}
                {points.length > 0 && (
                  <ChangedArea isChanged={changed.has("points")} value={points.join("\u0000")}>
                    <ul className="flex flex-col gap-1.5">
                      {points.map((p, k) => (
                        <li key={k} className="flex items-start gap-2">
                          <span className="pt-0.5">
                            <Icon icon="check" size="sm" color="inherit" />
                          </span>
                          <Text>{p}</Text>
                          {k === 0 && changed.has("points") && <ChangedDot />}
                        </li>
                      ))}
                    </ul>
                  </ChangedArea>
                )}
              </BoardSection>
            )}
            {shape.rtb && (
              <BoardSection align="rtb" title={b.rtb} isGap={!parts.rtb.length && !parts.pod}>
                {parts.pod && (
                  <FreshLine isChanged={changed.has(POD_KEY)} value={parts.pod.value}>
                    <Text weight="semibold">{parts.pod.value}</Text>
                  </FreshLine>
                )}
                {parts.rtb.length > 0 && (
                  <ul className="flex flex-wrap gap-1.5">
                    {parts.rtb.map((r) => (
                      <li key={r.key} className="min-w-0 max-w-full">
                        <ChangedArea isChanged={changed.has(r.key)} value={r.value}>
                          <Tag>{rtbChip(r)}</Tag>
                        </ChangedArea>
                      </li>
                    ))}
                  </ul>
                )}
              </BoardSection>
            )}
            <div data-align="price" className="px-6 pt-2 pb-6">
              <PriceTag item={item} changed={changed} />
            </div>
          </div>
          {/* 아래쪽: 기획자용 제품 스펙(바탕이 다른 면) */}
          <div data-board-spec className="flex flex-col">
            <div data-align="spec-title" className="px-6 pt-5 pb-1">
              <Heading level={3}>{b.specZone}</Heading>
            </div>
            <div data-align="spec-table" className="px-6 py-3">
              <ChangedArea isChanged={changed.has("variants")} value={String(item.shelf_variant ?? 0)}>
                <SpecSheet
                  spec={item}
                  pack={item.pack}
                  withPack
                  lead={lead}
                  tail={tail}
                  shelf={{ conceptId: item.id, pick: pickVariant }}
                />
              </ChangedArea>
            </div>
            {shape.who && (
              <BoardSection align="who" title={b.who} isGap={!parts.who.length}>
                <div className="grid grid-cols-2 gap-4">
                  {parts.who.map((r) => (
                    <SpecBlock key={r.key} row={r} changed={changed} differs={differs} />
                  ))}
                </div>
              </BoardSection>
            )}
            {shape.compare && (
              <BoardSection align="compare" title={b.compare} isGap={!parts.rivals.length}>
                <div className="grid grid-cols-1 gap-4">
                  {parts.rivals.map((r) => (
                    <SpecBlock key={r.key} row={r} changed={changed} differs={differs} />
                  ))}
                </div>
              </BoardSection>
            )}
          </div>
        </div>
      </Card>
    </div>
  )
}

/**
 * 나란한 컨셉 카드에서 같은 이름(data-align)의 묶음이 같은 높이에 오게 한다. 같은 줄에 놓인 카드끼리만 맞춘다
 * (작업대가 좁아 세로로 쌓이면 맞추지 않는다). 폭이 바뀌거나 내용이 바뀌면 다시 잰다.
 */
function useAlignRows(box: RefObject<HTMLElement | null>, key: string) {
  useLayoutEffect(() => {
    const root = box.current
    if (!root) return
    let lastWidth = -1
    const align = () => {
      const cards = Array.from(root.querySelectorAll<HTMLElement>("[data-concept-card]"))
      const cells = Array.from(root.querySelectorAll<HTMLElement>("[data-align]"))
      cells.forEach((el) => (el.style.minHeight = ""))
      const rows = new Map<number, HTMLElement[]>()
      cards.forEach((c) => {
        const top = Math.round(c.getBoundingClientRect().top)
        rows.set(top, [...(rows.get(top) ?? []), c])
      })
      rows.forEach((group) => {
        if (group.length < 2) return
        const byName = new Map<string, HTMLElement[]>()
        group.forEach((c) =>
          c.querySelectorAll<HTMLElement>("[data-align]").forEach((el) => {
            const name = el.dataset.align!
            byName.set(name, [...(byName.get(name) ?? []), el])
          }),
        )
        byName.forEach((els) => {
          const h = Math.max(...els.map((el) => el.getBoundingClientRect().height))
          els.forEach((el) => (el.style.minHeight = `${h}px`))
        })
      })
    }
    align()
    const ro = new ResizeObserver(() => {
      const width = root.getBoundingClientRect().width
      if (width === lastWidth) return
      lastWidth = width
      align()
    })
    ro.observe(root)
    return () => ro.disconnect()
  }, [box, key])
}

/**
 * 컨셉 보드(약속 v1.4). 컨셉이 하나면 작업대 너비를 다 쓰고, 여럿이면 카드를 나란히(좁으면 세로로 쌓는다).
 * 나란할 때는 같은 묶음이 같은 높이에 온다. 옛 형식의 컨셉은 있는 칸만 그린다.
 */
export function ConceptsBody({
  payload,
  pick = null,
  say = null,
  chatId,
}: {
  payload: ConceptsPayload
  pick?: PickMode
  say?: CardSay
  chatId?: string
}) {
  const differs = differingSpecKeys(payload.items)
  const shape = shapeOf(payload.items)
  // 매대에 올릴 규격 고르기(지시서 33 후속): 규격이 둘 이상인 옛 컨셉에서만, 확정한 뒤에는 잠근다
  const pickVariant: VariantPick = say
    ? {
        isDisabled: say.isDisabled || Boolean(payload.locked),
        isLocked: Boolean(payload.locked),
        onPick: (id, index, label) => say.onSay(specCopy.switchSay(label), { to: "variant", ids: [id, String(index)] }),
      }
    : null
  const grid = useRef<HTMLDivElement>(null)
  useAlignRows(grid, JSON.stringify(payload.items))
  const n = payload.items.length
  // 11-25: 보드마다 따로 세로형. 하나면 가운데 한 장(너비 상한), 둘 이상이면 두 열로 나란히(셋부터 줄을 바꾼다)
  const layout = n === 1 ? "mx-auto grid w-full max-w-lg grid-cols-1" : "grid grid-cols-1 @2xl:grid-cols-2"
  return (
    <div className="@container">
      <div ref={grid} className={`${layout} items-stretch gap-5`}>
        {payload.items.map((it, i) => (
          <Pickable key={it.id} id={it.id} pick={pick}>
            <ConceptBoard
              item={it}
              index={i}
              shape={shape}
              differs={differs}
              pickVariant={pickVariant}
              chatId={chatId}
            />
          </Pickable>
        ))}
      </div>
    </div>
  )
}

export function ReportBody({ payload }: { payload: ReportPayload }) {
  return (
    <VStack gap={4}>
      {payload.sections.map((s) => (
        <VStack key={s.title} gap={1}>
          <Text type="supporting">{s.title}</Text>
          <Text>{s.body}</Text>
        </VStack>
      ))}
    </VStack>
  )
}
