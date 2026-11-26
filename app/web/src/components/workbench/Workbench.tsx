import { ArrowDownTrayIcon } from "@heroicons/react/20/solid"
import { useEffect, useMemo, useRef, useState } from "react"
import { Button } from "@astryxdesign/core/Button"
import { Heading } from "@astryxdesign/core/Heading"
import { HStack } from "@astryxdesign/core/HStack"
import { Icon } from "@astryxdesign/core/Icon"
import { VStack } from "@astryxdesign/core/VStack"
import { copy, STAGES } from "../../copy"
import { foldCopy } from "../../copy/fold"
import { STAGE_IDS, type BriefPayload } from "../../chat/contract"
import { useWorkbench, type WorkCard } from "../../chat/workbenchStore"
import { hasBriefContent, type IdeaActions, type PickMode } from "./CardBodies"
import { CopyMarkdownButton } from "../proposal/CopyMarkdownButton"
import { proposalMarkdown } from "../proposal/markdown"
import { useProposal } from "../proposal/Paper"
import { ReportPapers, reportOrder } from "./ReportPapers"
import type { CardReply } from "./ShelfCards"
import { WorkbenchCard } from "./WorkbenchCard"
import { FOLDABLE_KINDS, foldSummary } from "./foldSummary"

const FLASH_MS = 1400

/** 방금 바뀐 카드의 id를 잠깐 들고 있다가 놓는다. */
function useFlashing(flash: { id: string; tick: number } | null) {
  const [id, setId] = useState<string | null>(null)
  useEffect(() => {
    if (!flash) return
    setId(flash.id)
    const t = window.setTimeout(() => setId(null), FLASH_MS)
    return () => window.clearTimeout(t)
  }, [flash])
  return id
}

/** 보일 것이 있는 카드인지. 아무것도 정해지지 않은 브리프는 카드 자체가 없다(약속 v1.3). */
const isShown = (c: WorkCard) => {
  return c.kind !== "brief" || c.status !== "ready" || hasBriefContent(c.payload as BriefPayload | null)
}

/**
 * 작업대. 보고 있는 단계의 카드를 온 순서대로 세로로 쌓는다. 카드가 없으면 그냥 비어 있다.
 * canPick이 거짓이면(칠성이가 말하는 중) 카드 안에서 고르기와 카드의 버튼을 누를 수 없다.
 * 결과 보고서 단계(report)에서는 카드 위에 제안서의 종이를 그린다(지시서 21. chatId가 없으면 그리지 않는다).
 */
export function Workbench({
  onRetry,
  onSay,
  onDownload,
  chatId,
  canPick = true,
}: {
  onRetry?: () => void
  /** 카드의 버튼(남기기, 빼기, 이 손님에게 묻기 등)이 기획자의 말로 보내는 곳. reply는 metadata.reply. */
  onSay?: (text: string, reply?: CardReply) => void
  /** 컨셉 보드 카드 머리의 "제안서로 내려받기"(지시서 14). 없으면 버튼을 두지 않는다. */
  onDownload?: () => void
  /** 지금 대화의 id. 결과 보고서 단계의 종이를 받는 데 쓴다(지시서 21). */
  chatId?: string
  canPick?: boolean
}) {
  const { stage, cards, viewStage, flash, view, picks, pending, togglePick } = useWorkbench()
  /** 카드 안에서 고르기의 상태. 답하기 전이면 누를 수 있고, 보낸 뒤면 고른 것만 남는다. */
  const pickFor = (cardId: string): PickMode => {
    const p = picks[cardId]
    // 고르는 차례가 아니면(이미 답했으면) 네모 칸을 그리지 않는다(약속 v1.3)
    if (!p || p.chosen) return null
    return {
      selected: pending[p.choicesId] ?? [],
      isLocked: !canPick,
      onToggle: (itemId) => togglePick(p.choicesId, itemId, p.kind),
    }
  }
  const shown = viewStage ?? stage
  const shownIndex = STAGE_IDS.indexOf(shown)
  const isReport = shown === "report"
  // 결과 보고서 단계의 종이: 여기서 한 번 받아 종이(ReportPapers)와 머리의 "LLM용 복사"가 함께 쓴다(지시서 22)
  const [paperAttempt, setPaperAttempt] = useState(0)
  const papers = useProposal(chatId ?? "", paperAttempt, isReport && Boolean(chatId))
  const markdown = useMemo(
    () =>
      papers.state === "ready" ? proposalMarkdown(reportOrder(papers.data.pages), papers.data.dept, papers.data.date) : null,
    [papers],
  )
  const hasPapers = isReport && Boolean(chatId)
  // 기획 브리프는 늘 맨 위(지시서 11). 나머지는 온 순서대로
  // 테스트의 카드(매대 테스트, 결과)는 가장 최근 것 하나만 보인다. 지난 컨셉의 테스트는 대화에서 다시 부르면 그것이 올라온다
  const lastOf = (kind: string) => cards.filter((c) => c.kind === kind && isShown(c)).at(-1)?.id
  const lastRun = { "shelf-run": lastOf("shelf-run"), result: lastOf("result") } as Record<string, string | undefined>
  const improveCard = cards.filter(c => c.stage === "improve" && isShown(c) && (c.kind === "group" || c.kind === "improve")).at(-1)
  const stageCards = cards
    .filter((c) => c.stage === shown && isShown(c) && (!(c.kind in lastRun) || lastRun[c.kind] === c.id))
    .filter(c => shown !== "improve" || (c.kind !== "improve" && c.kind !== "group") || c.id === improveCard?.id)
    .sort((a, b) => Number(b.kind === "brief") - Number(a.kind === "brief"))
  const actions: IdeaActions = onSay ? { onSay, isDisabled: !canPick } : null
  const scroller = useRef<HTMLDivElement>(null)
  const flashing = useFlashing(flash)

  // 접히는 카드: 그 단계의 주된 카드(아이디어, 컨셉 등)가 와 있으면 접는다. 아직이면 새로 오거나 바뀐 카드(fresh)와
  // 가장 최근에 온 것을 편다. 기획자가 직접 접거나 편 것(overrides)은 그 대화 안에서 유지한다
  const [overrides, setOverrides] = useState<Record<string, boolean>>({})
  const [fresh, setFresh] = useState<Record<string, boolean>>({})
  useEffect(() => {
    setOverrides({})
    setFresh({})
  }, [chatId])
  useEffect(() => {
    if (flash) setFresh((o) => (o[flash.id] ? o : { ...o, [flash.id]: true }))
  }, [flash])
  const foldable = stageCards.filter((c) => FOLDABLE_KINDS.has(c.kind) && c.status === "ready")
  const hasMain = stageCards.some((c) => !FOLDABLE_KINDS.has(c.kind) && c.status === "ready")
  const latestFoldable = cards.filter((c) => foldable.includes(c)).at(-1)?.id
  const isOpen = (c: WorkCard) => overrides[c.id] ?? (!hasMain && (Boolean(fresh[c.id]) || c.id === latestFoldable))
  const allOpen = foldable.every(isOpen)
  const setAll = (open: boolean) =>
    setOverrides((o) => ({ ...o, ...Object.fromEntries(foldable.map((c) => [c.id, open])) }))

  // 새로 열리거나 바뀐 카드로 스크롤한다
  useEffect(() => {
    if (!flash) return
    const el = scroller.current?.querySelector(`[data-workbench-card="${CSS.escape(flash.id)}"]`)
    el?.scrollIntoView({ behavior: "smooth", block: "nearest" })
  }, [flash])

  return (
    <section aria-label={copy.workbench.label} className="flex h-full min-h-0 flex-col">
      <div className="flex min-h-14 items-center justify-between gap-3 px-6 pt-5 pb-3">
        <Heading level={2}>{STAGES[shownIndex]}</Heading>
        {(viewStage || (isReport && onDownload) || hasPapers || foldable.length > 1) && (
          <HStack gap={2} vAlign="center">
            {foldable.length > 1 && (
              <Button
                label={allOpen ? foldCopy.collapseAll : foldCopy.expandAll}
                variant="ghost"
                size="sm"
                onClick={() => setAll(!allOpen)}
              />
            )}
            {hasPapers && <CopyMarkdownButton markdown={markdown} />}
            {isReport && onDownload && (
              <Button
                label={copy.workbench.savePdf}
                variant="secondary"
                size="sm"
                icon={<Icon icon={ArrowDownTrayIcon} />}
                onClick={onDownload}
              />
            )}
            {viewStage && (
              <Button
                label={copy.workbench.backToCurrent}
                variant="secondary"
                size="sm"
                icon={<Icon icon="chevronLeft" />}
                onClick={() => view(null)}
              />
            )}
          </HStack>
        )}
      </div>
      <div ref={scroller} className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-6 pt-1 pb-8">
        {hasPapers && (
          <div className={stageCards.length > 0 ? "pb-6" : undefined}>
            <ReportPapers loaded={papers} onRetry={() => setPaperAttempt((a) => a + 1)} />
          </div>
        )}
        {stageCards.length > 0 && (
          <VStack gap={4}>
            {stageCards.map((c) => (
              <WorkbenchCard
                key={c.id}
                card={c}
                isFlashing={flashing === c.id}
                onRetry={onRetry}
                pick={pickFor(c.id)}
                actions={c.kind === "ideas" ? actions : null}
                say={onSay ? { onSay, isDisabled: !canPick } : null}
                chatId={chatId}
                fold={
                  FOLDABLE_KINDS.has(c.kind)
                    ? {
                        isOpen: isOpen(c),
                        onOpenChange: (open) => setOverrides((o) => ({ ...o, [c.id]: open })),
                        summary: foldSummary(c),
                      }
                    : null
                }
                headerAction={
                  c.kind === "concepts" && c.status === "ready" && onDownload ? (
                    <Button
                      label={copy.workbench.download}
                      variant="secondary"
                      size="sm"
                      icon={<Icon icon={ArrowDownTrayIcon} />}
                      onClick={onDownload}
                    />
                  ) : null
                }
              />
            ))}
          </VStack>
        )}
      </div>
    </section>
  )
}
