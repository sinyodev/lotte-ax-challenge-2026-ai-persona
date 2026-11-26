import { ChatMessage, ChatMessageBubble } from "@astryxdesign/core/Chat"

/** 기획자의 말풍선 하나. */
export function PlannerBubble({ text }: { text: string }) {
  return (
    <ChatMessage sender="user">
      <ChatMessageBubble>{text}</ChatMessageBubble>
    </ChatMessage>
  )
}
