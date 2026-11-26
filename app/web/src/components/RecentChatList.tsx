import { Text } from "@astryxdesign/core/Text"
import { VStack } from "@astryxdesign/core/VStack"
import { copy } from "../copy"
import { groupRecent } from "../chat/recentGroups"
import { isChatPath, type RecentChat } from "../chat/recentChats"
import { RecentTestItem } from "./RecentTestItem"

/**
 * 최근 대화(Thread List처럼): 날짜 묶음의 머리(오늘, 어제, 지난 7일, 그 전) 아래에 제목 한 줄씩.
 * onDelete가 있으면 줄에 올려놓았을 때 지우기 버튼이 나온다.
 */
export function RecentChatList({
  chats,
  selectedHref,
  onDelete,
}: {
  chats: RecentChat[]
  selectedHref?: string
  onDelete?: (id: string) => Promise<unknown> | void
}) {
  return (
    <VStack gap={3}>
      {groupRecent(chats).map(({ group, items }) => (
        <VStack key={group} gap={0.5}>
          <div className="px-2 pb-0.5">
            <Text type="supporting">{copy.nav.recentGroups[group]}</Text>
          </div>
          {items.map((t) => (
            <RecentTestItem
              key={t.id}
              test={t}
              isSelected={isChatPath(selectedHref, t.id)}
              onDelete={onDelete}
            />
          ))}
        </VStack>
      ))}
    </VStack>
  )
}
