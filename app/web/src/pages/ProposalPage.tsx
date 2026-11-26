/**
 * 신제품 제안서 /proposal/:chatId (지시서 14의 4절). 왼쪽 메뉴가 없는 화면(AppFrame 밖)이다.
 * 위에 얇은 줄(대화로 돌아가기, LLM용 복사, PDF로 저장하기), 그 아래 회색 바탕 위에 A4 종이가 컨셉마다 한 장씩 세로로 놓인다.
 * 종이(Paper, PaperSkeleton, useProposal)는 components/proposal/Paper.tsx에 있고 작업대의 결과 보고서 단계와 함께 쓴다(지시서 21).
 * PDF는 브라우저의 인쇄로 저장한다(window.print). 인쇄할 때는 위의 줄과 회색 바탕이 빠진다.
 */
import { useEffect, useMemo, useState } from "react"
import { useParams } from "react-router"
import { Button } from "@astryxdesign/core/Button"
import { HStack } from "@astryxdesign/core/HStack"
import { Icon } from "@astryxdesign/core/Icon"
import { Text } from "@astryxdesign/core/Text"
import { copy } from "../copy"
import { CopyMarkdownButton } from "../components/proposal/CopyMarkdownButton"
import { proposalMarkdown } from "../components/proposal/markdown"
import { Paper, PaperSkeleton, useProposal, useSeconds } from "../components/proposal/Paper"

const t = copy.proposal

export function ProposalPage() {
  const { chatId = "" } = useParams()
  const [attempt, setAttempt] = useState(0)
  const loaded = useProposal(chatId, attempt)
  const seconds = useSeconds(loaded.state === "loading")
  const markdown = useMemo(
    () => (loaded.state === "ready" ? proposalMarkdown(loaded.data.pages, loaded.data.dept, loaded.data.date) : null),
    [loaded],
  )

  // PDF로 저장할 때의 파일 이름은 창의 제목을 따른다
  useEffect(() => {
    if (loaded.state !== "ready" || loaded.data.pages.length === 0) return
    const before = document.title
    document.title = t.docTitle(loaded.data.pages.map((p) => p.title).join(", "))
    return () => {
      document.title = before
    }
  }, [loaded])

  return (
    <div data-proposal-screen>
      <div data-proposal-bar className="flex items-center justify-between gap-3 px-6 py-2">
        <Button
          label={t.back}
          variant="ghost"
          size="sm"
          icon={<Icon icon="chevronLeft" />}
          href={`/concept/${encodeURIComponent(chatId)}`}
        />
        <HStack gap={2} vAlign="center">
          <CopyMarkdownButton markdown={markdown} />
          <Button label={t.save} variant="primary" size="sm" isDisabled={loaded.state !== "ready"} onClick={() => window.print()} />
        </HStack>
      </div>
      <main data-proposal-desk className="flex flex-col items-center gap-6 px-6 py-8">
        {loaded.state === "loading" && <PaperSkeleton seconds={seconds} />}
        {loaded.state === "failed" && (
          <div className="flex flex-col items-center gap-3 py-24">
            <HStack gap={1.5} vAlign="center">
              <Icon icon="warning" size="sm" color="secondary" />
              <Text color="secondary">{t.failed}</Text>
            </HStack>
            <Button label={t.retry} variant="secondary" onClick={() => setAttempt((a) => a + 1)} />
          </div>
        )}
        {loaded.state === "ready" &&
          loaded.data.pages.map((p) => <Paper key={p.concept_id} page={p} dept={loaded.data.dept} date={loaded.data.date} />)}
      </main>
    </div>
  )
}
