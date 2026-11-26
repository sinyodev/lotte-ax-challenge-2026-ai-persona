import { useState } from "react"
import { useNavigate, useSearchParams } from "react-router"
import { generateId } from "ai"
import { VStack } from "@astryxdesign/core/VStack"
import { copy, type ModeValue } from "../copy"
import type { PartId } from "../chat/contract"
import { useRecentChats, type RecentChat } from "../chat/recentChats"
import type { ConfirmedConcept, Container } from "../fixtures/confirmedConcepts"
import { ChilseongAvatar } from "../components/ChilseongAvatar"
import { Composer } from "../components/Composer"
import { ConfirmedConceptCards } from "../components/ConfirmedConceptCards"
import { Greeting } from "../components/Greeting"
import { NoticeLine } from "../components/NoticeLine"
import { PartSwitch } from "../components/PartSwitch"
import { SuggestionChips } from "../components/SuggestionChips"

/** 서버의 용기 이름 → 아이콘. 아이콘이 없는 용기(팩, 컵)는 null. */
const CONTAINER_OF: Record<string, Container> = { 캔: "can", 페트: "pet", 병: "bottle" }

/** 확정한 컨셉이 있는 실제 대화(GET /api/chats의 concepts, 지시서 15). 최근 것부터. */
export function confirmedFrom(chats: RecentChat[]): ConfirmedConcept[] {
  return chats
    .filter((c) => c.concepts.length > 0)
    .map((c) => ({
      id: c.id,
      name: c.title,
      concepts: c.concepts.map((k) => ({
        id: k.id,
        name: k.name,
        container: CONTAINER_OF[k.container] ?? null,
        pack: k.pack,
        price: k.price,
      })),
    }))
}

/** 주소의 ?part=test면 매대 테스트, 아니면 컨셉 기획. */
export function partFromSearch(params: URLSearchParams): PartId {
  return params.get("part") === "test" ? "test" : "concept"
}

/**
 * 첫 화면: 위쪽 가운데에 일을 고르는 전환, 가운데에 칠성이와 인사, 아래쪽에 칩(또는 확정한 컨셉 카드)과 입력창.
 * 전환해도 인사와 입력창의 자리가 움직이지 않게 칩 자리와 안내 한 줄의 높이를 고정한다.
 */
export function HomePage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const part = partFromSearch(params)
  // 진행 방식 버튼은 첫 화면에 없다. 값은 기본값 그대로 대화 화면에 넘긴다(약속 4절).
  const [mode] = useState<ModeValue>(copy.mode.defaultValue)
  const [notice, setNotice] = useState<string | null>(null)
  const text = copy.home[part]

  const switchPart = (next: PartId) => {
    setNotice(null)
    setParams(next === "test" ? { part: "test" } : {}, { replace: true })
  }
  // 1부: 대화 id를 만들고(useChat의 id와 같다) 그 주소로 간다. 받은 문장과 진행 방식을 넘기면 대화 화면이 첫 메시지로 바로 보낸다.
  const startConcept = (t: string) => navigate(`/concept/${generateId()}`, { state: { text: t, mode } })
  // 2부: 확정한 컨셉이 있는 대화를 열고 "매대에 올려 보기"를 보낸다(지시서 15). 직접 적은 컨셉은 아직 받지 않는다.
  const confirmed = confirmedFrom(useRecentChats((st) => st.chats))
  const openTest = (c: ConfirmedConcept) =>
    navigate(`/test/${encodeURIComponent(c.id)}`, { state: { text: copy.home.test.sendToShelf, mode, existing: true } })
  const startTest = () => setNotice(copy.home.test.preparing)
  const submit = part === "concept" ? startConcept : startTest

  return (
    <div className="flex h-full min-h-0 flex-col px-6 pb-7">
      <div className="flex justify-center pt-6">
        <PartSwitch value={part} onChange={switchPart} />
      </div>
      <div className="flex flex-1 flex-col items-center justify-center pt-6">
        <VStack gap={8} hAlign="center">
          <ChilseongAvatar />
          <Greeting prompt={text.prompt} />
        </VStack>
      </div>
      <div className="mx-auto w-full max-w-190">
        <div className="flex flex-col gap-2">
          <div className="flex h-40 flex-col justify-end">
            {part === "concept" ? (
              <SuggestionChips items={copy.home.concept.suggestions} onPick={startConcept} />
            ) : (
              <ConfirmedConceptCards concepts={confirmed.slice(0, 2)} onPick={openTest} />
            )}
          </div>
          <NoticeLine text={part === "test" ? notice : null} />
          <Composer onSubmit={submit} placeholder={text.placeholder} hasModeMenu={false} />
        </div>
      </div>
    </div>
  )
}
