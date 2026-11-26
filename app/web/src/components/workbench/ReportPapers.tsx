import { useEffect, useRef, useState } from "react"
import type { ProposalPage } from "../../chat/contract"
import { Button } from "@astryxdesign/core/Button"
import { HStack } from "@astryxdesign/core/HStack"
import { Icon } from "@astryxdesign/core/Icon"
import { Text } from "@astryxdesign/core/Text"
import { copy } from "../../copy"
import { Paper, PaperSkeleton, useSeconds, type LoadedProposal } from "../proposal/Paper"

const t = copy.proposal

/** A4 종이의 폭(210mm)을 화면의 px로. */
const PAPER_PX = (210 * 96) / 25.4

/** 감싼 칸의 폭에 맞춘 종이의 배율. 종이보다 넓으면 1(키우지 않는다). */
function useFitScale() {
  const ref = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(1)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => setScale(Math.min(1, el.clientWidth / PAPER_PX))
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return { ref, scale }
}

/** 작업대에 놓는 종이의 차례: 매대 테스트를 한 컨셉의 종이(page.test가 있는 것)를 먼저, 나머지는 온 차례대로. */
export function reportOrder(pages: ProposalPage[]): ProposalPage[] {
  return [...pages].sort((a, b) => Number(Boolean(b.test)) - Number(Boolean(a.test)))
}

/**
 * 작업대의 결과 보고서 단계(지시서 21). /proposal/:chatId와 같은 종이를 작업대의 폭에 맞춰 종이째로 줄여 그린다.
 * 종이의 자료는 작업대(Workbench)가 받아 넘긴다(머리의 "LLM용 복사"와 같은 것을 쓴다, 지시서 22).
 */
export function ReportPapers({ loaded, onRetry }: { loaded: LoadedProposal; onRetry: () => void }) {
  const seconds = useSeconds(loaded.state === "loading")
  const { ref, scale } = useFitScale()
  const zoom = { zoom: scale } as const

  const pages = loaded.state === "ready" ? reportOrder(loaded.data.pages) : []

  return (
    <div ref={ref} data-paper-fit className="flex w-full min-w-0 flex-col items-center gap-6">
      {loaded.state === "loading" && (
        <div style={zoom}>
          <PaperSkeleton seconds={seconds} />
        </div>
      )}
      {loaded.state === "failed" && (
        <div className="flex flex-col items-center gap-3 py-24">
          <HStack gap={1.5} vAlign="center">
            <Icon icon="warning" size="sm" color="secondary" />
            <Text color="secondary">{t.failed}</Text>
          </HStack>
          <Button label={t.retry} variant="secondary" onClick={onRetry} />
        </div>
      )}
      {loaded.state === "ready" &&
        pages.map((p) => (
          <div key={p.concept_id} style={zoom} className="flex flex-col gap-6">
            <Paper page={p} dept={loaded.data.dept} date={loaded.data.date} />
          </div>
        ))}
    </div>
  )
}
