import { useEffect, useRef, useState, type ReactNode } from "react"
import { ChatBubbleLeftRightIcon, UserIcon } from "@heroicons/react/24/outline"
import { Button } from "@astryxdesign/core/Button"
import { groupLiveCopy as c } from "../../copy/group-live"
import "./InterviewChat.css"

export function InterviewChat({ title, detail, count, children }: {
  title: string; detail: string; count: number; children: ReactNode
}) {
  const log = useRef<HTMLDivElement>(null)
  const follow = useRef(true)
  const previous = useRef(count)
  useEffect(() => {
    const el = log.current
    if (el && count > previous.current && follow.current) el.scrollTop = el.scrollHeight
    previous.current = count
  }, [count])
  return <section className="interview-chat" aria-label={title}>
    <header className="interview-chat__head">
      <ChatBubbleLeftRightIcon aria-hidden="true" />
      <div><h4>{title}</h4><p>{detail}</p></div>
    </header>
    <div ref={log} className="interview-chat__log" role="log" aria-label="인터뷰 대화" tabIndex={0}
      onScroll={e => { const el = e.currentTarget; follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 64 }}>
      {children}
    </div>
  </section>
}

export function InterviewBubble({ name = "칠성이", text, guest = false, reply, onQuote, disabled }: {
  name?: string; text: string; guest?: boolean; reply?: { label: string; text?: string }
  onQuote?: () => void; disabled?: boolean
}) {
  const [selected, setSelected] = useState(false)
  const body = <>
    {reply && <span className="interview-chat__reply"><strong>{reply.label}</strong>{reply.text && <span>{reply.text}</span>}</span>}
    <span className="interview-chat__text">{text}</span>
  </>
  return <div className="interview-chat__row" data-host={!guest || undefined}>
    {guest && <span aria-hidden="true" className="interview-chat__avatar"><UserIcon /></span>}
    <div className="interview-chat__message">
      <span className="interview-chat__name">{name}</span>
      {onQuote ? <button type="button" className="interview-chat__bubble" aria-pressed={selected}
        aria-label={name + " 발언 선택 · " + text} onClick={() => setSelected(!selected)}>{body}</button>
        : <div className="interview-chat__bubble">{body}</div>}
      {selected && onQuote && <Button label={c.quote} variant="secondary" size="sm" isDisabled={disabled} onClick={onQuote} />}
    </div>
  </div>
}
