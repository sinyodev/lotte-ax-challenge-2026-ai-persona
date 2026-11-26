import { useEffect, useRef, useState } from "react"
import { Button } from "@astryxdesign/core/Button"
import { Badge } from "@astryxdesign/core/Badge"
import { Icon } from "@astryxdesign/core/Icon"
import { CheckCircleIcon, PauseCircleIcon, ExclamationCircleIcon } from "@heroicons/react/24/outline"
import { Skeleton } from "@astryxdesign/core/Skeleton"
import { Text } from "@astryxdesign/core/Text"
import type { RunView } from "../../chat/contract"
import { EXPLORE_RESULT, type ExplorePayload, type ShelfRunView } from "../../chat/contract-shelf"
import { useRun } from "../../chat/runs"
import { useWorkbench, type WorkCard } from "../../chat/workbenchStore"
import { shelfCopy } from "../../copy/shelf"
import { AUTO_REPLY_TO, PlacementLine, type CardSay } from "./ShelfCards"
import { RunUsageLine } from "./RunUsageLine"
import { ExploreBreakdown } from "./ExploreBreakdown"
import { RunWaiting, useRunDoneTitle } from "./RunWaiting"
import { Collapsible } from "@astryxdesign/core/Collapsible"

const t = shelfCopy.explore
const sc = shelfCopy.stopped

function ExploreRun({ cardId, runId, say, sample }: { cardId: string; runId: string; say: CardSay; sample?: RunView | null }) {
  const { view, stop, resume } = useRun(runId, sample) as {
    view: ShelfRunView | null; stop: () => Promise<void>; resume: () => Promise<void> }
  const current = useWorkbench((state) => state.stage === "shelf" && !state.viewStage &&
    state.cards.filter((c) => c.kind === "explore" || c.kind === "shelf-run").at(-1)?.id === cardId)
  const fresh = useWorkbench((state) => !state.sample && state.flash?.id === cardId)
  const sawRunning = useRef(false)
  const sent = useRef(false)
  const [sentResult, setSentResult] = useState(false)
  const canSend = Boolean(current && say && !say.isDisabled && !sample)
  const running = view?.status === "running"
  const hasResult = view?.status === "done" && Boolean(view.explore)
  const stopped = view?.status === "stopped"
  // 멈춘 탐색: 칠성이가 지금까지 답한 손님으로 결과를 말한다(11-25)
  const seeSoFar = () => {
    if (!say || say.isDisabled || sample) return
    setSentResult(true)
    say.onSay(sc.seeSoFar, { to: "explore", ids: [EXPLORE_RESULT, runId] })
  }
  const stopAndSee = async () => {
    await stop()
    seeSoFar()
  }

  useEffect(() => {
    // 저장된 카드나 이미 끝난 테스트의 첫 조회에서는 사용자가 직접 열어요.
    if (!current) sawRunning.current = false
    else if (fresh && running) sawRunning.current = true
    if (hasResult && canSend && sawRunning.current && !sent.current) {
      sent.current = true
      setSentResult(true)
      say?.onSay(t.result, { to: AUTO_REPLY_TO, ids: [EXPLORE_RESULT, runId] })
    }
  }, [current, fresh, running, hasResult, canSend, say, runId])
  useRunDoneTitle(sample ? undefined : view?.status)

  if (running && view) {
    return (
      <div className="explore-card-content">
        <RunWaiting view={view} kind="explore"
          actions={current && !sample ? <Button label={t.stop} variant="ghost" onClick={() => void stopAndSee()} /> : null}>
          {view.requested != null && view.total < view.requested && <Text>{shelfCopy.fewerAssigned(view.total, view.requested)}</Text>}
          <PlacementLine placement={view.placement} />
          {view.explore && (
            <Collapsible trigger={<Text weight="medium">{shelfCopy.waiting.breakdown}</Text>} defaultIsOpen={false}>
              <ExploreBreakdown result={view.explore} done={false} running requested={view.requested} />
            </Collapsible>
          )}
        </RunWaiting>
      </div>
    )
  }

  return (
    <div className="explore-card-content">
      <div className="explore-status">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2" aria-live={current ? "polite" : "off"} aria-atomic="true">
          {view ? <>
            <Badge label={t.status[view.status]} variant="neutral" icon={
              <Icon size="sm" icon={view.status === "done" ? CheckCircleIcon : view.status === "failed" ? ExclamationCircleIcon : PauseCircleIcon} />} />
            <Text weight="semibold">{view.concept.name}</Text>
            <Text type="supporting" color="primary" hasTabularNumbers>
              {stopped ? sc.at(view.asked, view.total) : t.responded(view.asked)}
            </Text>
          </> : <span role="status" aria-label={t.loading}><Skeleton height={20} width={120} /></span>}
        </div>
        <RunUsageLine view={view} />
      </div>
      {view?.requested != null && view.total < view.requested && <Text>{shelfCopy.fewerAssigned(view.total, view.requested)}</Text>}
      <PlacementLine placement={view?.placement} />
      {view?.explore && <ExploreBreakdown result={view.explore} done={view.status === "done"} running={false} requested={view.requested} />}
      {view?.status === "done" && !view.explore && <Text>{t.noResult}</Text>}
      {stopped && current && !sample && (
        <div className="flex flex-wrap gap-2">
          {say && !sentResult && <Button label={sc.seeSoFar} variant="primary" isDisabled={say.isDisabled} onClick={seeSoFar} />}
          <Button label={sc.resume} variant="secondary" onClick={() => { setSentResult(false); void resume() }} />
        </div>
      )}
      {hasResult && current && say && !sentResult && (
        <div>
          <Button label={t.result} variant="primary" isDisabled={!canSend} onClick={() => {
            if (!canSend || sent.current) return
            sent.current = true
            setSentResult(true)
            say.onSay(t.result, { to: "explore", ids: [EXPLORE_RESULT, runId] })
          }} />
        </div>
      )}
    </div>
  )
}

export function ExploreBody({ card, say, sample }: { card: WorkCard; say: CardSay; sample?: RunView | null }) {
  const payload = card.payload as ExplorePayload | null
  return payload?.run_id ? <ExploreRun key={payload.run_id} cardId={card.id} runId={payload.run_id} say={say} sample={sample} /> : null
}
