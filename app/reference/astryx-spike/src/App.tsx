import { useState } from "react"
import { useChat } from "@ai-sdk/react"
import { DefaultChatTransport, type UIMessage } from "ai"
import { Theme } from "@astryxdesign/core/theme"
import { themes, defaultThemeSlug } from "./astryx-themes"
import {
  ChatLayout,
  ChatComposer,
  ChatMessageList,
  ChatMessage,
  ChatMessageBubble,
  ChatToolCalls,
} from "@astryxdesign/core/Chat"
import { Markdown } from "@astryxdesign/core/Markdown"
import { Stepper, Step } from "@astryxdesign/core/Stepper"
import { Card } from "@astryxdesign/core/Card"
import { Button } from "@astryxdesign/core/Button"
import { SegmentedControl, SegmentedControlItem } from "@astryxdesign/core/SegmentedControl"
import { RadioList, RadioListItem } from "@astryxdesign/core/RadioList"
import { Token } from "@astryxdesign/core/Token"
import { Text, Heading } from "@astryxdesign/core/Text"
import { VStack, HStack } from "@astryxdesign/core/Stack"
import { Divider } from "@astryxdesign/core/Divider"

const STEPS = ["아이디어 회의", "컨셉 보드", "매대 테스트", "테스트 결과", "개선안 테스트", "결과 보고서"]
const SUGGESTIONS = [
  { label: "신제품 아이디어 내기", value: "제로 탄산 신제품 하나 검토해 보고 싶어" },
  { label: "있는 컨셉 테스트하기", value: "있는 컨셉을 테스트하고 싶어" },
]

type QOption = { id: string; label: string; description?: string }
type QInput = { questions: { kind: string; title: string; options?: QOption[] }[] }

/* ---------- UIMessage -> Astryx 대화 부품 ---------- */

function QuestionCard({ input, answered, onAnswer }: { input: QInput; answered: boolean; onAnswer: (t: string) => void }) {
  const q = input.questions?.[0]
  const [value, setValue] = useState("")
  if (!q) return null
  return (
    <Card padding={4} variant="muted">
      <VStack gap={3}>
        <RadioList label={q.title} value={value} onChange={setValue} isDisabled={answered}>
          {(q.options ?? []).map((o) => (
            <RadioListItem key={o.id} value={o.id} label={o.label} description={o.description} />
          ))}
        </RadioList>
        {!answered && (
          <HStack gap={2} hAlign="end">
            <Button label="칠성이가 골라 줘" variant="ghost" onClick={() => onAnswer("칠성이가 골라 줘")} />
            <Button
              label="이걸로 할게요"
              variant="primary"
              isDisabled={!value}
              onClick={() => onAnswer(q.options?.find((o) => o.id === value)?.label ?? value)}
            />
          </HStack>
        )}
      </VStack>
    </Card>
  )
}

type AnyPart = UIMessage["parts"][number] & {
  toolCallId?: string
  state?: string
  input?: unknown
  text?: string
}

function AssistantParts({ msg, streaming, answered, onAnswer }: {
  msg: UIMessage; streaming: boolean; answered: boolean; onAnswer: (t: string) => void
}) {
  return (
    <>
      {(msg.parts as AnyPart[]).map((p, i) => {
        if (p.type === "text")
          return (
            <ChatMessageBubble key={i} variant="ghost">
              <Markdown density="compact" isStreaming={streaming}>{p.text ?? ""}</Markdown>
            </ChatMessageBubble>
          )
        if (p.type === "tool-Question")
          return (
            <ChatMessageBubble key={i} variant="ghost" width="100%">
              <QuestionCard input={p.input as QInput} answered={answered} onAnswer={onAnswer} />
            </ChatMessageBubble>
          )
        if (p.type.startsWith("tool-"))
          return (
            <ChatMessageBubble key={i} variant="ghost" width="100%">
              <ChatToolCalls
                calls={[{
                  name: p.type.slice(5),
                  status: p.state === "output-available" ? "complete" : "running",
                  target: JSON.stringify(p.input),
                }]}
              />
            </ChatMessageBubble>
          )
        return null
      })}
    </>
  )
}

function ChatPanel() {
  const { messages, sendMessage, status, stop } = useChat({
    transport: new DefaultChatTransport({ api: "/api/chat" }),
  })
  const [draft, setDraft] = useState("")
  const busy = status === "streaming" || status === "submitted"
  const send = (text: string) => { if (text.trim()) { sendMessage({ text }); setDraft("") } }

  return (
    <ChatLayout
      density="compact"
      style={{ flex: 1, minHeight: 0 }}
      composer={
        <ChatComposer
          value={draft}
          onChange={setDraft}
          onSubmit={send}
          onStop={stop}
          isStopShown={busy}
          placeholder="칠성이에게 말하기"
        />
      }
      emptyState={
        <VStack gap={3} hAlign="center">
          <Heading level={3}>무엇을 해 볼까요?</Heading>
          <HStack gap={2}>
            {SUGGESTIONS.map((s) => (
              <Token key={s.label} label={s.label} size="lg" onClick={() => send(s.value)} />
            ))}
          </HStack>
        </VStack>
      }
    >
      {messages.length > 0 && (
        <ChatMessageList isStreaming={busy}>
          {messages.map((m, idx) => {
            const isLast = idx === messages.length - 1
            if (m.role === "user")
              return (
                <ChatMessage key={m.id} sender="user">
                  {m.parts.map((p, i) => p.type === "text" ? <ChatMessageBubble key={i}>{p.text}</ChatMessageBubble> : null)}
                </ChatMessage>
              )
            return (
              <ChatMessage key={m.id} sender="assistant" name="칠성이">
                <AssistantParts msg={m} streaming={isLast && busy} answered={!isLast || busy} onAnswer={send} />
              </ChatMessage>
            )
          })}
        </ChatMessageList>
      )}
    </ChatLayout>
  )
}

/* ---------- 작업대 카드 ---------- */

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <HStack gap={2} style={{ justifyContent: "space-between" }}>
      <Text type="body" color={strong ? "primary" : "secondary"} weight={strong ? "semibold" : undefined}>{label}</Text>
      <Text type="body" weight={strong ? "semibold" : "medium"}>{value}</Text>
    </HStack>
  )
}

function Workbench() {
  const [mode, setMode] = useState("recommend")
  return (
    <Card padding={6} elevation="low">
      <VStack gap={4}>
        <Heading level={4}>컨셉 B · 제로 탄산 500ml</Heading>
        <VStack gap={1}>
          <Text type="display-1" color="accent" weight="bold">18%</Text>
          <Text type="supporting">선택률 · 300명 중 54명</Text>
        </VStack>
        <VStack gap={2}>
          <Row label="경쟁사 전환" value="31명" />
          <Row label="자사 간 이동(카니발)" value="19명" />
          <Row label="신규 구매" value="4명" />
          <Divider />
          <Row label="합계" value="54명" strong />
        </VStack>
        <Text type="supporting">결과 신뢰도: A와의 차이 뚜렷함</Text>
        <VStack gap={2}>
          <Button label="바꾼 이유 물어보기" variant="primary" width="100%" />
          <HStack gap={2}>
            <Button label="개선안 받아 보기" variant="secondary" width="100%" />
            <Button label="보고서 만들기" variant="secondary" width="100%" />
          </HStack>
        </VStack>
        <SegmentedControl label="개선 방식" value={mode} onChange={setMode} layout="fill">
          <SegmentedControlItem value="self" label="직접 바꾸기" />
          <SegmentedControlItem value="recommend" label="추천받기" />
          <SegmentedControlItem value="delegate" label="칠성이에게 맡기기" />
        </SegmentedControl>
      </VStack>
    </Card>
  )
}

export default function App() {
  return (
    <Theme theme={themes[defaultThemeSlug]}>
      <div className="flex h-dvh flex-col bg-white">
        <div className="border-b px-6 py-3">
          <Stepper activeStep={3} label="진행 단계">
            {STEPS.map((s, i) => <Step key={s} step={i} label={s} />)}
          </Stepper>
        </div>
        <div className="flex min-h-0 flex-1">
          <div className="flex min-w-0 flex-1 flex-col border-r">
            <ChatPanel />
          </div>
          <div className="w-[400px] shrink-0 overflow-auto bg-neutral-50 p-6">
            <Workbench />
          </div>
        </div>
      </div>
    </Theme>
  )
}
