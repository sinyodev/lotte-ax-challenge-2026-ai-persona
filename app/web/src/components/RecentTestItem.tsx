import { useState } from "react"
import { TrashIcon } from "@heroicons/react/20/solid"
import { AlertDialog } from "@astryxdesign/core/AlertDialog"
import { Icon } from "@astryxdesign/core/Icon"
import { IconButton } from "@astryxdesign/core/IconButton"
import { Item } from "@astryxdesign/core/Item"
import { Spinner } from "@astryxdesign/core/Spinner"
import { StatusDot } from "@astryxdesign/core/StatusDot"
import { Text } from "@astryxdesign/core/Text"
import { Tooltip } from "@astryxdesign/core/Tooltip"
import { copy } from "../copy"
import { recentChatHref, type RecentChat, type RecentChatStatus } from "../chat/recentChats"

/**
 * 줄 오른쪽 끝의 작은 표시 하나: 칠성이가 일하는 중이면 돌아가는 원, 기획자의 답을 기다리면 강조색 점.
 * 그 밖에는 없다. 올려놓으면 뜻을 말해 준다.
 */
export function RecentStatusMark({ status }: { status: RecentChatStatus }) {
  if (status === "working") {
    return (
      <Tooltip content={copy.nav.recentWorking} placement="end">
        <span className="inline-flex">
          <Spinner size="sm" shade="subtle" aria-label={copy.nav.recentWorking} />
        </span>
      </Tooltip>
    )
  }
  if (status === "waiting") {
    return (
      <span className="inline-flex px-1">
        <StatusDot variant="accent" label={copy.nav.recentWaiting} tooltip={copy.nav.recentWaiting} />
      </span>
    )
  }
  return null
}

/**
 * 최근 대화 한 줄: 제목 한 줄과 오른쪽 끝의 표시(있으면). 날짜는 묶음의 머리가 맡는다.
 * onDelete가 있으면 줄에 올려놓았을 때(또는 키보드로 들어왔을 때) 오른쪽 끝에 지우기 버튼이 겹쳐 나온다.
 * 버튼은 줄(Item) 밖의 형제로 두어 링크 안에 버튼이 들어가지 않게 하고, 자리를 차지하지 않아 줄의 크기가 바뀌지 않는다.
 * 누르면 한 번 확인한다(AlertDialog).
 */
export function RecentTestItem({
  test,
  isSelected,
  onDelete,
}: {
  test: RecentChat
  isSelected?: boolean
  onDelete?: (id: string) => Promise<unknown> | void
}) {
  const [isAsking, setIsAsking] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const row = (
    <Item
      href={recentChatHref(test)}
      isSelected={isSelected}
      density="compact"
      label={
        <Text weight="medium" maxLines={1}>
          {test.title}
        </Text>
      }
      endContent={
        <span data-recent-mark className="inline-flex">
          <RecentStatusMark status={test.status} />
        </span>
      }
    />
  )
  if (!onDelete) return row
  return (
    <div data-recent-row className="relative">
      {row}
      <div data-recent-delete className="absolute inset-y-0 right-1 flex items-center">
        <IconButton
          label={copy.nav.recentDelete}
          tooltip={copy.nav.recentDelete}
          icon={<Icon icon={TrashIcon} />}
          variant="ghost"
          size="sm"
          onClick={() => setIsAsking(true)}
        />
      </div>
      <AlertDialog
        isOpen={isAsking}
        onOpenChange={setIsAsking}
        title={copy.nav.deleteTitle}
        description={copy.nav.deleteDesc}
        actionLabel={copy.nav.deleteAction}
        cancelLabel={copy.nav.deleteCancel}
        isActionLoading={isDeleting}
        onAction={async () => {
          setIsDeleting(true)
          try {
            await onDelete(test.id)
          } finally {
            setIsDeleting(false)
            setIsAsking(false)
          }
        }}
      />
    </div>
  )
}
