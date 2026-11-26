import { HStack } from "@astryxdesign/core/HStack"
import { Icon } from "@astryxdesign/core/Icon"
import { Text } from "@astryxdesign/core/Text"

/** 입력창 위의 안내 한 줄(작은 회색 글씨). 글이 없으면 자리만 지킨다. */
export function NoticeLine({ text }: { text: string | null }) {
  return (
    <div role="status" aria-live="polite" className="flex min-h-6 justify-center">
      {text && (
        <HStack gap={1.5} vAlign="center">
          <Icon icon="info" size="sm" color="secondary" />
          <Text type="supporting">{text}</Text>
        </HStack>
      )}
    </div>
  )
}
