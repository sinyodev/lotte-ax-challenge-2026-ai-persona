import { ChatLayout, ChatMessageList } from "@astryxdesign/core/Chat"
import type { ChatStatus } from "ai"
import { copy } from "../../copy"
import type { ChilseongMessage } from "../../chat/contract"
import { Composer } from "../Composer"
import { PlannerBubble } from "../PlannerBubble"
import { AssistantMessage } from "./AssistantMessage"
import { ChilseongTurn, DisconnectedNotice, TurnBlock, type OnReply } from "./ChatParts"

type Props = {
  messages: ChilseongMessage[]
  status: ChatStatus
  hasError: boolean
  onSend: (text: string) => void
  onReply: OnReply
  onStop: () => void
  onResend: () => void
  /** 멈춘 마지막 차례의 "다시 하기". */
  onRetryStopped: () => void
  /** 파일 올리기(입력창의 클립 버튼). */
  onAttach?: () => void
  attachLabel?: string
}

function textOf(m: ChilseongMessage) {
  return m.parts.map((p) => (p.type === "text" ? p.text : "")).join("")
}

/**
 * 대화. 칠성이의 말과 부품, 기획자의 말풍선, 입력창. 새 말이 오면 ChatLayout이 아래로 따라 내려간다.
 * 입력창은 ChatLayout이 흐름 안에 붙여 두므로(sticky) 맨 아래에 따로 여백을 두지 않는다.
 */
export function ChatPanel({ messages, status, hasError, onSend, onReply, onStop, onResend, onRetryStopped, onAttach, attachLabel }: Props) {
  const busy = status === "submitted" || status === "streaming"
  const last = messages[messages.length - 1]

  return (
    <ChatLayout
      density="compact"
      composer={
        <div>
          <Composer
            onSubmit={(text) => {
              if (busy) return
              onSend(text)
            }}
            hasModeMenu={false}
            placeholder={copy.test.placeholder}
            density="balanced"
            isStopShown={busy}
            onStop={onStop}
            onAttach={onAttach}
            attachLabel={attachLabel}
          />
        </div>
      }
    >
      <ChatMessageList isStreaming={busy} align="top" gap={5}>
        {messages.map((m, idx) => {
          // 카드가 스스로 보낸 말(결과가 나왔을 때)은 기획자의 말풍선으로 그리지 않는다
          if (m.role === "user" && m.metadata?.reply?.to === "auto") return null
          if (m.role === "user") return <PlannerBubble key={m.id} text={textOf(m)} />
          const next = messages[idx + 1]
          const isLast = m === last
          return (
            <AssistantMessage
              key={m.id}
              message={m}
              isActive={isLast && !busy && !hasError}
              isThinking={isLast && busy}
              isStreaming={isLast && busy}
              reply={next?.role === "user" ? next.metadata?.reply : undefined}
              onReply={onReply}
              onRetryStopped={isLast && !busy ? onRetryStopped : undefined}
            />
          )
        })}
        {status === "submitted" && last?.role === "user" && (
          <ChilseongTurn isThinking>
            <TurnBlock>{null}</TurnBlock>
          </ChilseongTurn>
        )}
        {hasError && (
          <ChilseongTurn>
            <TurnBlock>
              <DisconnectedNotice onResend={onResend} />
            </TurnBlock>
          </ChilseongTurn>
        )}
      </ChatMessageList>
    </ChatLayout>
  )
}
