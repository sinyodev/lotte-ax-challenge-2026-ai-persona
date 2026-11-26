import { useEffect, useRef, useState, type ClipboardEvent } from "react"
import { ChatComposer, ChatSendButton } from "@astryxdesign/core/Chat"
import { IconButton } from "@astryxdesign/core/IconButton"
import { PaperClipIcon } from "@heroicons/react/20/solid"
import { copy, type ModeValue } from "../copy"
import { ModeMenu } from "./ModeMenu"

type Props = {
  onSubmit: (text: string) => void
  /** 견본 페이지에서 처음 글을 넣어 두려고 쓴다. */
  defaultValue?: string
  mode?: ModeValue
  onModeChange?: (mode: ModeValue) => void
  placeholder?: string
  /** 진행 방식 버튼을 보일지. 첫 화면에서는 뺀다(개선안 테스트에서만 뜻이 있다). */
  hasModeMenu?: boolean
  density?: "compact" | "balanced" | "spacious"
  /** 칠성이가 말하는 동안 보내기 버튼이 멈춤 버튼이 된다. */
  isStopShown?: boolean
  onStop?: () => void
  /** 값이 바뀔 때마다 입력칸에 커서를 둔다(직접 쓰기 칩을 눌렀을 때). */
  focusTick?: number
  /** 파일 올리기(입력창 아래 줄 왼쪽의 클립 버튼). 없으면 버튼을 두지 않는다. */
  onAttach?: () => void
  attachLabel?: string
}

/**
 * 발표 자료에서 복사한 글은 글과 그림이 함께 온다. 입력 부품은 파일이 있으면 글을 버리므로, 글만 다시 붙여 넣는다.
 */
function pasteTextOnly(e: ClipboardEvent<HTMLDivElement>) {
  const text = e.clipboardData.getData("text/plain")
  if (!text || e.clipboardData.files.length === 0) return
  e.preventDefault()
  e.stopPropagation()
  const data = new DataTransfer()
  data.setData("text/plain", text)
  e.target.dispatchEvent(new window.ClipboardEvent("paste", { clipboardData: data, bubbles: true, cancelable: true }))
}

/**
 * 입력창. 아래 줄 왼쪽에 진행 방식 버튼(hasModeMenu), 오른쪽에 보내기 버튼. 첨부와 마이크는 두지 않는다.
 * 보내기 버튼은 글이 없어도 흐려지지 않는다. 눌러도 빈 글은 넘기지 않을 뿐이다.
 */
export function Composer({
  onSubmit,
  defaultValue = "",
  mode: modeProp,
  onModeChange,
  placeholder = copy.home.concept.placeholder,
  hasModeMenu = true,
  density = "spacious",
  isStopShown = false,
  onStop,
  focusTick,
  onAttach,
  attachLabel,
}: Props) {
  const [draft, setDraft] = useState(defaultValue)
  const host = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!focusTick) return
    host.current?.querySelector<HTMLElement>("textarea, [contenteditable='true'], input")?.focus()
  }, [focusTick])
  const [ownMode, setOwnMode] = useState<ModeValue>(copy.mode.defaultValue)
  const mode = modeProp ?? ownMode
  const setMode = onModeChange ?? setOwnMode

  return (
    <div ref={host} onPasteCapture={pasteTextOnly}>
    <ChatComposer
      value={draft}
      onChange={setDraft}
      onSubmit={(text) => {
        if (!text.trim()) return
        onSubmit(text.trim())
        setDraft("")
      }}
      onStop={onStop}
      isStopShown={isStopShown}
      placeholder={placeholder}
      density={density}
      footerActions={hasModeMenu || onAttach ? (
        <>
          {onAttach && (
            <IconButton label={attachLabel ?? ""} tooltip={attachLabel} size="sm" variant="ghost"
              icon={<PaperClipIcon aria-hidden="true" />} onClick={onAttach} />
          )}
          {hasModeMenu && <ModeMenu value={mode} onChange={setMode} />}
        </>
      ) : undefined}
      sendButton={<ChatSendButton isDisabled={false} />}
    />
    </div>
  )
}
