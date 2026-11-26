import type { ComponentProps, ReactNode } from "react"
import { lazy, Suspense } from "react"
import { Button } from "@astryxdesign/core/Button"
import { Card } from "@astryxdesign/core/Card"
import { Collapsible } from "@astryxdesign/core/Collapsible"
import "./fold.css"
import { Heading } from "@astryxdesign/core/Heading"
import { HStack } from "@astryxdesign/core/HStack"
import { Icon } from "@astryxdesign/core/Icon"
import { Skeleton } from "@astryxdesign/core/Skeleton"
import { Text } from "@astryxdesign/core/Text"
import { VStack } from "@astryxdesign/core/VStack"
import { copy } from "../../copy"
import { improveCopy } from "../../copy/improve"
import type {
  BriefPayload,
  ConceptsPayload,
  EvidencePayload,
  IdeasPayload,
  ImprovePayload,
  ReportPayload,
  ResultPayload,
  RunView,
  ShelfRunPayload,
} from "../../chat/contract"
import type { WorkCard } from "../../chat/workbenchStore"
import {
  BriefBody,
  ConceptsBody,
  EvidenceBody,
  ExploreBody,
  IdeasBody,
  ReportBody,
  type IdeaActions,
  type PickMode,
} from "./CardBodies"
import { ImproveBody } from "./ImproveCard"
import { ResultBody, ShelfRunBody, type CardSay } from "./ShelfCards"
import { OriginTag } from "./OriginTag"
import { TrendCard } from "./TrendCard"
import { HistoryCard } from "./HistoryCard"
import { AnalysisSpec, DiagnosisCard } from "./DiagnosisCard"
import { FollowupCard } from "./FollowupCard"
import type { FollowupPayload } from "../../chat/contract-followup"

const GroupDemoWorkbench = lazy(() => import("./GroupDemoWorkbench"))
const LiveGroupCard = lazy(() => import("./LiveGroupCard").then(({ LiveGroupCard }) => ({ default: LiveGroupCard })))

function Body({ card, pick, actions, say, runSample, runSamples, chatId }: {
  card: WorkCard
  pick: PickMode
  actions: IdeaActions
  say: CardSay
  runSample?: RunView | null
  runSamples?: Record<string, RunView>
  chatId?: string
}) {
  switch (card.kind) {
    case "brief":
      return <BriefBody payload={card.payload as BriefPayload} />
    case "evidence":
      return <EvidenceBody payload={card.payload as EvidencePayload} />
    case "ideas":
      return <IdeasBody payload={card.payload as IdeasPayload} pick={pick} actions={actions} />
    case "concepts":
      return <ConceptsBody payload={card.payload as ConceptsPayload} pick={pick} say={say} chatId={chatId} />
    case "shelf-run":
      return <ShelfRunBody payload={card.payload as ShelfRunPayload} say={say} sample={runSample} />
    case "result":
      return <ResultBody payload={card.payload as ResultPayload} say={say} sample={runSample} />
    case "improve":
      return <ImproveBody payload={card.payload as ImprovePayload} say={say} samples={runSamples} />
    case "report":
      return <ReportBody payload={card.payload as ReportPayload} />
    case "explore": return <ExploreBody card={card} say={say} sample={runSample} />
    case "trend": return <TrendCard {...card.payload as ComponentProps<typeof TrendCard>}/>
    case "history": return <HistoryCard {...card.payload as ComponentProps<typeof HistoryCard>} />
    case "diagnosis": return <DiagnosisCard payload={card.payload as ComponentProps<typeof DiagnosisCard>["payload"]} say={say} />
    case "followup": return <FollowupCard payload={card.payload as FollowupPayload} />
    case "group": {
      const payload = card.payload as ComponentProps<typeof GroupDemoWorkbench>["payload"] | ComponentProps<typeof LiveGroupCard>["payload"]
      if (payload.demo === false) {
        return <Suspense fallback={<LoadingBody />}><LiveGroupCard payload={payload} say={say} /></Suspense>
      }
      return <Suspense fallback={<LoadingBody />}><GroupDemoWorkbench key={payload.turn} payload={payload} say={say} /></Suspense>
    }
    default:
      return null
  }
}

/** loading이면 뼈대만. 글로 상태를 말하지 않는다. */
function LoadingBody() {
  return (
    <div aria-busy="true">
      <VStack gap={3}>
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} height={16} width={i === 2 ? "60%" : "100%"} index={i} />
        ))}
      </VStack>
    </div>
  )
}

function ErrorBody({ onRetry }: { onRetry?: () => void }) {
  return (
    <VStack gap={3} hAlign="start">
      <HStack gap={1.5} vAlign="center">
        <Icon icon="warning" size="sm" color="secondary" />
        <Text color="secondary">{copy.workbench.loadFailed}</Text>
      </HStack>
      <Button label={copy.workbench.retry} variant="secondary" onClick={onRetry} />
    </VStack>
  )
}

/**
 * 작업대 카드 한 장. 제목과 몸통. 새로 열리거나 바뀌면 잠깐 테두리가 강조된다(isFlashing).
 * loading이면 뼈대, error면 "불러오지 못했어요"와 다시 하기.
 */
export function WorkbenchCard({
  card,
  isFlashing = false,
  onRetry,
  pick = null,
  actions = null,
  headerAction = null,
  say = null,
  runSample = null,
  runSamples,
  fold = null,
  chatId,
}: {
  /** 접히는 카드(기획 브리프, 찾아본 것, 트렌드 조사, 비슷한 과거 사례). 없으면 늘 펼친다. ready가 아니면 무시한다. */
  fold?: { isOpen: boolean; onOpenChange: (isOpen: boolean) => void; summary: string } | null
  card: WorkCard
  isFlashing?: boolean
  onRetry?: () => void
  /** 카드 안에서 고르기(약속 v1.2 choices.on_card). */
  pick?: PickMode
  /** 아이디어 카드의 남기기, 빼기(약속 v1.3). 기획자의 말로 보낸다. */
  actions?: IdeaActions
  /** 카드 머리 오른쪽에 두는 조용한 버튼(컨셉 보드의 제안서로 내려받기). */
  headerAction?: ReactNode
  /** 매대 테스트 카드의 버튼("먼저 온 결과 보기", "결과 보기")이 기획자의 말로 보내는 곳(지시서 15). */
  say?: CardSay
  /** 견본 페이지: 통로를 부르지 않고 이 값으로 그린다. */
  runSample?: RunView | null
  /** 견본 페이지의 개선안 카드: 테스트 id → 모양. 통로를 부르지 않는다. */
  runSamples?: Record<string, RunView>
  /** 컨셉 보드의 그림 자리(ConceptVisual)에 넘기는 대화 id. */
  chatId?: string
}) {
  const head = headerAction ?? (card.kind === "diagnosis" && card.status === "ready" && card.payload ? (
    <AnalysisSpec payload={card.payload as ComponentProps<typeof AnalysisSpec>["payload"]} />
  ) : null)
  // 컨셉 보드 분석의 카드 제목은 제품명이다(단계 이름은 작업대 머리에 있다. 컨셉이 둘이면 카드가 둘)
  const title =
    card.kind === "diagnosis" && card.status === "ready" && (card.payload as { concept_name?: string } | null)?.concept_name
      ? (card.payload as { concept_name: string }).concept_name
      : card.kind === "improve" ? improveCopy.title : card.title
  if (fold && card.status === "ready") {
    return (
      <div data-workbench-card={card.id} data-flash={isFlashing || undefined} data-fold={fold.isOpen ? "open" : "closed"}>
        <Card padding={0}>
          <Collapsible
            isOpen={fold.isOpen}
            onOpenChange={fold.onOpenChange}
            className="workbench-fold"
            trigger={
              <span className="flex min-w-0 flex-1 items-center gap-2">
                <Heading level={3} className="shrink-0">{title}</Heading>
                {card.origin && <span className="shrink-0"><OriginTag origin={card.origin} /></span>}
                {!fold.isOpen && fold.summary && (
                  <span className="min-w-0 flex-1">
                    <Text maxLines={1} hasTruncateTooltip={false}>{fold.summary}</Text>
                  </span>
                )}
              </span>
            }
          >
            <div className="px-5 pt-1 pb-5">
              <Body card={card} pick={pick} actions={actions} say={say} runSample={runSample} runSamples={runSamples} chatId={chatId} />
            </div>
          </Collapsible>
        </Card>
      </div>
    )
  }
  return (
    <div data-workbench-card={card.id} data-flash={isFlashing || undefined}>
      <Card padding={5}>
        <VStack gap={4}>
          {(card.kind !== "improve" || card.status !== "ready" || !card.payload) && <div className="flex flex-wrap items-center justify-between gap-2">
            <HStack gap={2} vAlign="center" wrap="wrap">
              <Heading level={3} className={card.kind === "explore" ? "explore-card-title" : undefined}>{title}</Heading>
              {card.origin && <OriginTag origin={card.origin} />}
            </HStack>
            {head}
          </div>}
          {card.status === "loading" ? (
            <LoadingBody />
          ) : card.status === "error" ? (
            <ErrorBody onRetry={onRetry} />
          ) : (
            <Body card={card} pick={pick} actions={actions} say={say} runSample={runSample} runSamples={runSamples} chatId={chatId} />
          )}
        </VStack>
      </Card>
    </div>
  )
}
