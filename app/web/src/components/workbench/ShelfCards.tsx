/**
 * 2부 매대 테스트의 카드 둘(지시서 15, 약속 v1.6): 매대 테스트(shelf-run)와 결과(result).
 * 숫자는 대화에 박혀 있지 않고 카드가 GET /api/runs/{run_id}를 2초마다 읽는다(chat/runs.ts). 끝나면 멈춘다.
 * 카드의 버튼은 그 말을 기획자의 말로 대화에 보낸다("먼저 온 결과 보기", "결과 보기"). 멈추기만 통로를 바로 부른다.
 */
import { lazy, Suspense, useEffect, useMemo, useRef } from "react"
import { Badge } from "@astryxdesign/core/Badge"
import { Button } from "@astryxdesign/core/Button"
import { HStack } from "@astryxdesign/core/HStack"
import { ProgressBar } from "@astryxdesign/core/ProgressBar"
import { Skeleton } from "@astryxdesign/core/Skeleton"
import { Spinner } from "@astryxdesign/core/Spinner"
import { Text } from "@astryxdesign/core/Text"
import { VStack } from "@astryxdesign/core/VStack"
import { copy } from "../../copy"
import { shelfCopy } from "../../copy/shelf"
import type { ResultPayload, RunQuote, RunView, ShelfRunPayload } from "../../chat/contract"
import type { ShelfPlacement, ShelfRunView } from "../../chat/contract-shelf"
import { RunWaiting, useRunDoneTitle } from "./RunWaiting"
import { ResultDashboard } from "./ResultDashboard"
import { canSeeEarly, useRun } from "../../chat/runs"

// 입체 매장은 카드를 그릴 때에만 받는다(three와 그 도구가 다른 화면의 묶음에 섞이지 않게)
const StoreView = lazy(() => import("../../store3d/StoreView"))

const r = copy.workbench.result
const k = copy.workbench.run
const sc = shelfCopy.stopped

/** 칩이나 버튼의 답에 붙는 것(약속 4절의 metadata.reply). 결과 카드의 "이 손님 인터뷰하기"는 to "visitor"(지시서 17). */
export type CardReply = { to: string; ids: string[] }
/** 카드의 버튼이 기획자의 말로 보내는 곳. isDisabled면(칠성이가 말하는 중) 누를 수 없다. */
export type CardSay = { onSay: (text: string, reply?: CardReply) => void; isDisabled: boolean } | null

/** 결과 카드의 "이 손님 인터뷰하기"가 보내는 metadata.reply.to(서버의 phrases.INTERVIEW_TO와 같다). */
export const VISITOR_REPLY_TO = "visitor"
/** 카드가 스스로 보낸 말(결과가 나오면 칠성이가 먼저 말하게 한다). 대화에는 기획자의 말풍선으로 그리지 않는다. */
export const AUTO_REPLY_TO = "auto"

function StatusMark({ view }: { view: RunView }) {
  if (view.status === "running") return <Spinner size="sm" aria-label={k.running} />
  if (view.status === "stopped") return <Badge label={k.stopped} />
  if (view.status === "failed") return <Badge label={k.failed} variant="warning" />
  return null
}

export function PlacementLine({ placement }: { placement?: ShelfPlacement | null }) {
  if (!placement) return null
  const { storage, store_rate } = placement
  return <Text>{store_rate == null ? shelfCopy.placement.storage(storage) : shelfCopy.placement.rate(storage, store_rate)}</Text>
}

// ---------- 매대 테스트 카드 ----------

export function ShelfRunBody({ payload, say, sample }: { payload: ShelfRunPayload; say: CardSay; sample?: RunView | null }) {
  const { view, stop, resume } = useRun(payload.run_id, sample) as {
    view: ShelfRunView | null; stop: () => Promise<void>; resume: () => Promise<void> }
  const c = payload.concept
  const stopped = view?.status === "stopped"
  // 멈추면 칠성이가 지금까지의 답으로 결과를 말한다(11-25)
  const stopAndSee = async () => {
    await stop()
    if (say && !say.isDisabled) say.onSay(sc.seeSoFar)
  }
  const total = view?.total ?? 0
  const asked = view?.asked ?? 0
  const running = view?.status === "running"
  const early = view ? canSeeEarly(view) : false
  const done = view?.status === "done"
  // 기다리던 결과가 나오면(100명이 다녀갔거나 끝남) 누르지 않아도 칠성이가 먼저 말한다. 이 화면에서 기다리는 것을 본 때에만, 한 번만.
  const wasWaiting = useRef(false)
  const told = useRef(false)
  const canSay = Boolean(say && !say.isDisabled)
  useEffect(() => {
    if (!view || sample) return
    if (view.status === "running" && !early) {
      wasWaiting.current = true
      return
    }
    if ((early || done) && wasWaiting.current && !told.current && canSay) {
      told.current = true
      say?.onSay(done ? k.result : k.early, { to: AUTO_REPLY_TO, ids: [] })
    }
  }, [view, early, done, canSay, say, sample])
  useRunDoneTitle(sample ? undefined : view?.status)
  // 손님 머리 위의 말풍선: 지금까지 온 답 가운데 결과가 고른 말(구매한 손님, 구매하지 않은 손님)
  const quotes = view?.result?.quotes
  const picked = quotes?.picked.map((q) => q.said).join("\n") ?? ""
  const passed = quotes?.passed.map((q) => q.said).join("\n") ?? ""
  const thoughts = useMemo(
    () => ({ picked: picked ? picked.split("\n") : [], passed: passed ? passed.split("\n") : [] }),
    [picked, passed],
  )
  return (
    <VStack gap={4}>
      <div data-run-store role="region" aria-label={k.store} className="aspect-video w-full">
        <Suspense fallback={<Skeleton height="100%" width="100%" />}>
          <StoreView
            compact
            concept={{ name: c.name, container: c.container, volume: c.volume, price: c.price }}
            flow={view ? { asked, picked: view.result?.picked ?? 0, total, running } : null}
            thoughts={thoughts}
          />
        </Suspense>
      </div>
      {view && running ? (
        <RunWaiting view={view} kind="target" actions={<>
          {early && <Button label={k.early} variant="primary" onClick={() => say?.onSay(k.early)} isDisabled={!say || say.isDisabled} />}
          <Button label={k.stop} variant="ghost" onClick={() => void stopAndSee()} />
        </>}>
          {view.requested != null && total < view.requested && <Text>{shelfCopy.fewerAssigned(total, view.requested)}</Text>}
          <PlacementLine placement={view.placement} />
        </RunWaiting>
      ) : view ? (
        <VStack gap={3}>
          <div className="flex items-center justify-between gap-3">
            <Text weight="medium">{k.asking(payload.who, total)}</Text>
            <StatusMark view={view} />
          </div>
          {view.requested != null && total < view.requested && <Text>{shelfCopy.fewerAssigned(total, view.requested)}</Text>}
          <PlacementLine placement={view.placement} />
          <VStack gap={1.5}>
            <div className="flex items-baseline justify-between gap-3">
              <Text>{k.visitedLabel}</Text>
              <Text weight="semibold" hasTabularNumbers>
                {k.visited(asked, total)}
              </Text>
            </div>
            <ProgressBar
              label={k.progress}
              isLabelHidden
              value={asked}
              max={Math.max(1, total)}
              variant="neutral"
              isDisabled={view.status === "stopped" || view.status === "failed"}
            />
          </VStack>
          {(early || done || running || stopped) && (
            <HStack gap={2} wrap="wrap">
              {stopped && <Button label={sc.seeSoFar} variant="primary" onClick={() => say?.onSay(sc.seeSoFar)} isDisabled={!say || say.isDisabled} />}
              {stopped && <Button label={sc.resume} variant="secondary" onClick={() => void resume()} isDisabled={!!sample} />}
              {early && <Button label={k.early} variant="primary" onClick={() => say?.onSay(k.early)} isDisabled={!say || say.isDisabled} />}
              {done && <Button label={k.result} variant="primary" onClick={() => say?.onSay(k.result)} isDisabled={!say || say.isDisabled} />}
              {running && <Button label={k.stop} variant="ghost" onClick={() => void stopAndSee()} />}
            </HStack>
          )}
        </VStack>
      ) : (
        <Skeleton height={16} width="60%" />
      )}
    </VStack>
  )
}

// ---------- 결과 카드 ----------

/** 결과 카드: 결과 화면(ResultDashboard, 본문은 ResultReport). brief가 없는 옛 결과도 같은 화면으로 그린다. */
export function ResultBody({ payload, say, sample }: { payload: ResultPayload; say?: CardSay; sample?: RunView | null }) {
  const { view }: { view: ShelfRunView | null } = useRun(payload.run_id, sample)
  // 가상 소비자의 말마다 "이 가상 소비자 인터뷰하기"(지시서 17의 A, 18의 B). 말하는 중이면 누를 수 없다
  const askFor = (q: RunQuote) =>
    say ? (say.isDisabled ? null : () => say.onSay(r.askSay(q.who), { to: VISITOR_REPLY_TO, ids: [payload.run_id, q.visitor] })) : undefined
  if (!view || !view.result) {
    return (
      <VStack gap={3}>
        <Skeleton height={16} width="50%" />
        <Skeleton height={40} width="30%" index={1} />
      </VStack>
    )
  }
  return <ResultDashboard view={view} askFor={askFor} />
}
