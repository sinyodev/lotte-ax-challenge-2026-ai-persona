/**
 * 대화에 놓이는 부품: 칠성이의 말 한 덩이, 하는 일 한 줄, 칩, 버튼 묶음, 확인 카드, 요약 카드, 연결 끊김.
 * 약속 2절의 형식만 받는다. 글은 서버가 보낸 것을 그대로 쓰고, 화면이 갖는 글은 copy.ts에 있다.
 */
import { useEffect, useRef, useState, type ReactNode } from "react"
import { Avatar } from "@astryxdesign/core/Avatar"
import { Button } from "@astryxdesign/core/Button"
import { Card } from "@astryxdesign/core/Card"
import { ChatMessage, ChatMessageBubble } from "@astryxdesign/core/Chat"
import { Divider } from "@astryxdesign/core/Divider"
import { Heading } from "@astryxdesign/core/Heading"
import { HStack } from "@astryxdesign/core/HStack"
import { Icon } from "@astryxdesign/core/Icon"
import { Spinner } from "@astryxdesign/core/Spinner"
import { Text } from "@astryxdesign/core/Text"
import { VStack } from "@astryxdesign/core/VStack"
import { copy } from "../../copy"
import type { ActionsData, ActivityData, ChoicesData, ConfirmData, SummaryData } from "../../chat/contract"
import { ChilseongAvatar } from "../ChilseongAvatar"

/** 답을 받는 부품(칩, 버튼, 확인 카드)의 상태. 마지막 차례의 것만 누를 수 있다. */
export type ReplyState = {
  isActive: boolean
  /** 이 부품에 기획자가 답한 것의 id들. 고른 모습으로 남는다. */
  chosen: string[]
}

export type OnReply = (to: string, ids: string[], labels: string[]) => void

/** 칠성이의 한 차례. 작은 칠성이와, 말풍선 면 없는 글과 부품들. */
export function ChilseongTurn({ isThinking = false, children }: { isThinking?: boolean; children: ReactNode }) {
  return (
    <ChatMessage
      sender="assistant"
      name={null}
      avatar={<ChilseongAvatar size={30} mood={isThinking ? "thinking" : "idle"} />}
    >
      {children}
    </ChatMessage>
  )
}

/**
 * 테스트의 손님 한 명의 말(지시서 17, 약속 v1.7 say.speaker). 칠성이와 다른 화자로 보인다:
 * 캐릭터 대신 사람 윤곽의 중립색 동그라미(Avatar의 기본 그림), 이름 자리에 "24세 여자, 대학생". 초록과 강조색을 쓰지 않는다.
 * 이름은 첫 덩이(TurnBlock의 name)에 붙인다.
 */
export function ShopperTurn({ children }: { children: ReactNode }) {
  return (
    <ChatMessage sender="assistant" name={null} avatar={<Avatar size={32} tooltip={false} alt={copy.test.shopper} />}>
      {children}
    </ChatMessage>
  )
}

/** 칠성이의 한 차례 안에서 한 덩이(말, 칩 묶음 등). 글 칸에 맞춰 놓는다. name이 있으면 덩이 위에 화자의 이름. */
export function TurnBlock({ children, name }: { children: ReactNode; name?: string }) {
  return (
    <ChatMessageBubble variant="ghost" width="100%" name={name ? <Text type="supporting" weight="medium">{name}</Text> : undefined}>
      {children}
    </ChatMessageBubble>
  )
}

export function SayText({ text }: { text: string }) {
  return (
    <div className="whitespace-pre-line">
      <Text as="p" display="block">
        {text}
      </Text>
    </div>
  )
}

/** 하는 일이 이만큼 넘게 걸리면 이름 옆에 흐른 시간("12초")을 보인다. */
const ELAPSED_AFTER_MS = 5_000

/**
 * 하는 중인 동안 흐른 초. 처음 그린 때(또는 startedAgoMs만큼 앞)부터 1초마다 센다. 끝나면 그 자리에서 멈춘다.
 */
function useElapsedSeconds(isRunning: boolean, startedAgoMs: number) {
  const startedAt = useRef(Date.now() - startedAgoMs)
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!isRunning) return
    setNow(Date.now())
    const t = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(t)
  }, [isRunning])
  return Math.max(0, Math.floor((now - startedAt.current) / 1000))
}

/**
 * 하는 일 표시(Agent Progress처럼): 움직이는 작은 표시, 짧은 이름, 5초가 넘으면 흐른 시간.
 * 하는 중에는 이름의 글씨에 빛이 지나가고(Text Shimmer), 끝나면 표시가 체크로 바뀌고 빛이 멈춘다.
 * 움직임과 빛의 모양은 테마(overrides.css의 data-activity)에 있다.
 *
 * 도는 것은 그 메시지가 마지막이고 대화가 지금 흘러오는 중일 때뿐이다(isLive, 지시서 11).
 * "하는 중"으로 왔더라도 멈췄거나 끊겼거나 지난 차례이면 돌지 않고, 시간도 빛도 멈춘다.
 * 멈춘 차례(isStopped)에는 표시 자리에 멈춤 아이콘이 오고 이름 뒤에 "멈춤"이 붙는다.
 */
export function ActivityLine({
  data,
  startedAgoMs = 0,
  isLive = true,
  isStopped = false,
}: {
  data: ActivityData
  startedAgoMs?: number
  isLive?: boolean
  isStopped?: boolean
}) {
  const isRunning = data.status === "running" && isLive
  const isHalted = data.status === "running" && !isLive
  const seconds = useElapsedSeconds(isRunning, startedAgoMs)
  const showElapsed = seconds * 1000 >= ELAPSED_AFTER_MS
  const state = isRunning ? "running" : isHalted ? "stopped" : "done"
  return (
    <div data-activity={state} role={isRunning ? "status" : undefined}>
      <HStack gap={2} vAlign="center">
        <span data-activity-mark className="inline-flex shrink-0">
          {isRunning ? (
            <Spinner size="sm" shade="subtle" aria-label={copy.test.activityRunning} />
          ) : isHalted ? (
            <Icon icon="stop" size="sm" color="secondary" label={copy.test.stopped} />
          ) : (
            <Icon icon="check" size="sm" color="secondary" label={copy.test.activityDone} />
          )}
        </span>
        <span data-shimmer={isRunning || undefined} className="min-w-0">
          <Text type="supporting" weight="medium">
            {state === "done" ? copy.test.activityDoneLabel(data.label) : data.label}
          </Text>
        </span>
        {showElapsed && (
          <span className="shrink-0">
            <Text type="supporting" hasTabularNumbers>
              {copy.test.elapsed(seconds)}
            </Text>
          </span>
        )}
        {isHalted && isStopped && (
          <span className="shrink-0">
            <Text type="supporting" weight="medium">
              {copy.test.stopped}
            </Text>
          </span>
        )}
      </HStack>
    </div>
  )
}

/** 하는 일 표시가 없는 채로 멈춘 차례: 같은 자리에 멈춤 아이콘과 "멈춤"만. */
export function StoppedLine() {
  return (
    <div data-activity="stopped">
      <HStack gap={2} vAlign="center">
        <span data-activity-mark className="inline-flex shrink-0">
          <Icon icon="stop" size="sm" color="secondary" />
        </span>
        <Text type="supporting" weight="medium">
          {copy.test.stopped}
        </Text>
      </HStack>
    </div>
  )
}

/** 멈춘 차례 아래의 "다시 하기": 같은 말을 다시 보낸다. */
export function RetryStoppedButton({ onRetry }: { onRetry: () => void }) {
  return (
    <ChipRow>
      <Button label={copy.test.retryStopped} variant="secondary" onClick={onRetry} />
    </ChipRow>
  )
}

/**
 * 고를 수 있다는 네모 칸. 칸의 자리는 늘 있고, 고르면 채워진다(크기가 바뀌지 않는다).
 * 모양은 테마(themes/lotte/overrides.css의 data-check-box)에 있다.
 */
export function CheckBox({ isChecked }: { isChecked: boolean }) {
  return (
    <span data-check-box data-checked={isChecked || undefined} aria-hidden="true">
      <Icon icon="check" size="xsm" />
    </span>
  )
}

/**
 * 칩과 버튼 하나. 모두 Astryx Button 한 줄이라 높이와 글씨 크기가 같다. 덧말(note)은 올려놓았을 때의 풍선 도움말로만.
 * 주 버튼만 채운 면, 나머지는 테두리(대화 안의 모양은 overrides.css의 data-chat-actions).
 * 고른 상태는 테두리로만 보이고, 여럿 고르기의 네모 칸은 처음부터 자리가 있어 고르기 전후로 크기가 같다.
 */
function ReplyButton({
  label,
  note,
  isChosen = false,
  hasCheckBox = false,
  isPrimary = false,
  onClick,
}: {
  label: string
  note?: string
  isChosen?: boolean
  hasCheckBox?: boolean
  isPrimary?: boolean
  onClick?: () => void
}) {
  return (
    <div
      data-choice-chip
      data-chosen={isChosen || undefined}
      data-static={onClick ? undefined : true}
      className="min-w-0 max-w-full"
    >
      <Button
        label={label}
        variant={isPrimary ? "primary" : "secondary"}
        icon={hasCheckBox ? <CheckBox isChecked={isChosen} /> : undefined}
        tooltip={note}
        onClick={onClick}
        aria-pressed={hasCheckBox ? isChosen : undefined}
      />
    </div>
  )
}

/** 칩과 버튼의 줄: 가로로 놓고 넘치면 줄을 바꾼다. 세로로 쌓지 않는다. */
function ChipRow({ children }: { children: ReactNode }) {
  return (
    <div data-chat-actions className="flex flex-wrap items-center gap-2">
      {children}
    </div>
  )
}

/** 여럿 고르기의 보내기 버튼. 고른 개수를 말한다. 하나도 안 고르면 못 누른다. */
export function PickedSendButton({ count, onSend }: { count: number; onSend: () => void }) {
  return (
    <ChipRow>
      <Button
        label={count > 0 ? copy.test.pickedSend(count) : copy.test.pickNone}
        variant="primary"
        isDisabled={count === 0}
        onClick={onSend}
      />
    </ChipRow>
  )
}

/**
 * 질문의 답 고르기(Quick Replies처럼). 하나 고르기는 누르면 바로 보낸다. 여럿 고르기는 칩 앞에 네모 칸,
 * 묶음 위에 안내, 아래에 고른 개수를 말하는 보내기 버튼. 직접 쓰기(free)는 그리지 않는다(입력창이 그 일을 한다).
 * 지난 차례에는 고른 것만 남긴다(나머지는 접는다).
 */
export function ChoiceChips({
  id,
  data,
  state,
  onReply,
}: {
  id: string
  data: ChoicesData
  state: ReplyState
  onReply: OnReply
}) {
  const [picked, setPicked] = useState<string[]>([])
  const isMulti = data.kind === "multi"
  const send = (ids: string[]) =>
    onReply(
      id,
      ids,
      ids.map((i) => data.options.find((o) => o.id === i)?.label ?? i),
    )

  if (!state.isActive) {
    const chosen = data.options.filter((o) => state.chosen.includes(o.id))
    if (chosen.length === 0) return null
    return (
      <ChipRow>
        {chosen.map((o) => (
          <ReplyButton key={o.id} label={o.label} note={o.note} isChosen hasCheckBox={isMulti} />
        ))}
      </ChipRow>
    )
  }

  return (
    <VStack gap={2} hAlign="start">
      {isMulti && <Text type="supporting">{copy.test.multiHint}</Text>}
      <ChipRow>
        {data.options.map((o) => (
          <ReplyButton
            key={o.id}
            label={o.label}
            note={o.note}
            isChosen={picked.includes(o.id)}
            hasCheckBox={isMulti}
            onClick={() => {
              if (!isMulti) return send([o.id])
              setPicked((p) => (p.includes(o.id) ? p.filter((x) => x !== o.id) : [...p, o.id]))
            }}
          />
        ))}
      </ChipRow>
      {isMulti && <PickedSendButton count={picked.length} onSend={() => send(picked)} />}
    </VStack>
  )
}

/**
 * 카드 안에서 고르기(choices.on_card)의 대화 쪽: 보내기 버튼만.
 * 고르는 것은 작업대의 카드에서 하고, 고른 개수만 여기서 받는다.
 */
export function OnCardPrompt({ count, onSend }: { count: number; onSend: () => void }) {
  return <PickedSendButton count={count} onSend={onSend} />
}

/**
 * 다음에 할 일. 칩과 같은 한 줄 버튼을 가로로 놓고 넘치면 줄을 바꾼다. 주 버튼만 채운 면, 나머지는 테두리.
 * 설명(note)은 올려놓았을 때의 풍선 도움말로만. 지난 차례에는 누른 것만 고른 모양으로 남긴다.
 */
export function ActionButtons({
  id,
  data,
  state,
  onReply,
}: {
  id: string
  data: ActionsData
  state: ReplyState
  onReply: OnReply
}) {
  const shown = state.isActive ? data.actions : data.actions.filter((a) => state.chosen.includes(a.id))
  if (shown.length === 0) return null
  return (
    <ChipRow>
      {shown.map((a) => (
        <ReplyButton
          key={a.id}
          label={a.label}
          note={a.note}
          isPrimary={state.isActive && Boolean(a.primary)}
          isChosen={!state.isActive}
          onClick={state.isActive ? () => onReply(id, [a.id], [a.label]) : undefined}
        />
      ))}
    </ChipRow>
  )
}

/** 되돌리기 어려운 일의 확인 카드. 제목과 설명(desc), 줄 맞춘 내역(줄마다 덧말), 버튼 둘. */
export function ConfirmCard({
  id,
  data,
  state,
  onReply,
}: {
  id: string
  data: ConfirmData
  state: ReplyState
  onReply: OnReply
}) {
  const buttons = [
    { ...data.confirm, primary: true },
    { ...data.cancel, primary: false },
  ]
  // 지난 차례에는 누른 버튼만 남긴다
  const shownButtons = buttons.filter((b) => state.isActive || state.chosen.includes(b.id))
  return (
    <Card padding={4}>
      <VStack gap={3}>
        <VStack gap={1}>
          <Heading level={4}>{data.title}</Heading>
          {data.desc && <Text type="supporting">{data.desc}</Text>}
        </VStack>
        <VStack gap={2}>
          {data.rows.map((r) => (
            <HStack key={r.label} gap={4} justify="between" vAlign="start">
              <span className="shrink-0 whitespace-nowrap">
                <Text color="secondary">{r.label}</Text>
              </span>
              <VStack gap={0} hAlign="end">
                <Text weight="medium" hasTabularNumbers>
                  {r.value}
                </Text>
                {r.note && (
                  <Text type="supporting" justify="end">
                    {r.note}
                  </Text>
                )}
              </VStack>
            </HStack>
          ))}
        </VStack>
        {shownButtons.length > 0 && <Divider />}
        <div data-chat-actions>
          <HStack gap={2} wrap="wrap">
            {shownButtons.map((b) => (
                <Button
                  key={b.id}
                  label={b.label}
                  variant={state.isActive && b.primary ? "primary" : "secondary"}
                  onClick={state.isActive ? () => onReply(id, [b.id], [b.label]) : undefined}
                />
              ))}
          </HStack>
        </div>
      </VStack>
    </Card>
  )
}

/** 대화에 남기는 한 줄 결과. 제목(회색 작은 글씨), 값(본문보다 조금 큰 글씨), 덧말. */
export function SummaryCard({ data }: { data: SummaryData }) {
  return (
    <Card padding={4}>
      <VStack gap={1}>
        <Text type="supporting">{data.title}</Text>
        <Text type="large" weight="semibold" hasTabularNumbers>
          {data.value}
        </Text>
        {data.note && <Text type="supporting">{data.note}</Text>}
      </VStack>
    </Card>
  )
}

/** 서버가 꺼져 있거나 스트림이 끊겼을 때. */
export function DisconnectedNotice({ onResend }: { onResend?: () => void }) {
  return (
    <VStack gap={2} hAlign="start">
      <HStack gap={1.5} vAlign="center">
        <Icon icon="warning" size="sm" color="secondary" />
        <Text color="secondary">{copy.test.disconnected}</Text>
      </HStack>
      <div data-chat-actions>
        <Button label={copy.test.resend} variant="secondary" onClick={onResend} />
      </div>
    </VStack>
  )
}
