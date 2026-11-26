import { Heading } from "@astryxdesign/core/Heading"
import { Text } from "@astryxdesign/core/Text"
import { VStack } from "@astryxdesign/core/VStack"

/** 본문 화면의 제목과 설명 한 줄. */
export function PageHeader({ title, description }: { title: string; description?: string }) {
  return (
    <VStack gap={1}>
      <Heading level={1}>{title}</Heading>
      {description && <Text color="secondary">{description}</Text>}
    </VStack>
  )
}
