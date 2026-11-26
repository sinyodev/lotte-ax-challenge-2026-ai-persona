import { VStack } from "@astryxdesign/core/VStack"
import { PageHeader } from "../components/PageHeader"
import { PreparingState } from "../components/PreparingState"

/** 아직 만들지 않은 화면: 제목, 설명 한 줄, "준비하고 있어요". */
export function PlaceholderPage({ title, description }: { title: string; description: string }) {
  return (
    <div className="px-10 py-10">
      <VStack gap={10}>
        <PageHeader title={title} description={description} />
        <PreparingState />
      </VStack>
    </div>
  )
}
