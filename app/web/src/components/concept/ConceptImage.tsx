import type { ReactNode } from "react"
import { useCallback, useEffect, useRef, useState } from "react"
import { Button } from "@astryxdesign/core/Button"
import { Spinner } from "@astryxdesign/core/Spinner"
import { Text } from "@astryxdesign/core/Text"
import { conceptImageCopy as t } from "../../copy/concept-image"
import { Tag } from "../workbench/OriginTag"

/** 서버의 status와 화면에서만 생기는 상태(처음 읽는 중, 실패). */
export type ConceptImageState = "loading" | "none" | "working" | "ready" | "failed" | "unavailable"

type StatusBody = { status: "none" | "working" | "ready" | "unavailable"; url?: string; version?: number }

const POLL_MS = 2000

function base(chatId: string, conceptId: string) {
  return `/api/chats/${encodeURIComponent(chatId)}/concepts/${encodeURIComponent(conceptId)}/image`
}

/**
 * 컨셉의 예시 패키지 이미지. 기획자가 버튼을 누를 때만 만든다(자동으로 만들지 않는다).
 * placeholder는 그림이 없을 때 보이는 지금의 빈 면(용기 아이콘)이다.
 */
export function ConceptImage({
  chatId,
  conceptId,
  placeholder,
}: {
  chatId: string
  conceptId: string
  placeholder: ReactNode
}) {
  const [state, setState] = useState<ConceptImageState>("loading")
  const [url, setUrl] = useState<string | undefined>()
  const alive = useRef(true)

  const read = useCallback(async () => {
    try {
      const r = await fetch(`${base(chatId, conceptId)}/status`)
      // 보드가 막 올라온 때는 그 차례가 아직 저장되지 않아 404가 온다. 그림이 없는 것으로 보고 버튼을 내민다.
      if (r.status === 404) {
        if (alive.current) setState("none")
        return
      }
      if (!r.ok) throw new Error(String(r.status))
      const body = (await r.json()) as StatusBody
      if (!alive.current) return
      setUrl(body.url)
      setState(body.status)
    } catch {
      if (alive.current) setState("unavailable")
    }
  }, [chatId, conceptId])

  useEffect(() => {
    alive.current = true
    setState("loading")
    void read()
    return () => {
      alive.current = false
    }
  }, [read])

  // 다른 곳에서 만들기 시작한 것(또는 갔다 온 사이에 도는 것)은 2초마다 다시 읽는다.
  useEffect(() => {
    if (state !== "working") return
    const id = window.setInterval(() => void read(), POLL_MS)
    return () => window.clearInterval(id)
  }, [state, read])

  const make = useCallback(
    async (again: boolean) => {
      setState("working")
      try {
        const r = await fetch(base(chatId, conceptId), {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ again }),
        })
        if (!alive.current) return
        if (r.status === 409) {
          setState("unavailable")
          return
        }
        if (!r.ok) throw new Error(String(r.status))
        const body = (await r.json()) as StatusBody
        if (!alive.current) return
        setUrl(body.url)
        setState("ready")
      } catch {
        if (alive.current) setState("failed")
      }
    },
    [chatId, conceptId],
  )

  return (
    <ConceptImageView
      state={state}
      url={url}
      placeholder={placeholder}
      onMake={() => void make(false)}
      onAgain={() => void make(true)}
    />
  )
}

/** 상태만 받아 그리는 부분. /design 견본 페이지가 네 상태를 그대로 보인다. */
export function ConceptImageView({
  state,
  url,
  placeholder,
  onMake,
  onAgain,
}: {
  state: ConceptImageState
  url?: string
  placeholder: ReactNode
  onMake: () => void
  onAgain: () => void
}) {
  if (state === "ready" && url) {
    return (
      <div data-concept-image-ready className="flex w-full flex-col items-center gap-2">
        <div data-concept-image className="relative w-full overflow-hidden">
          <img src={url} alt={t.alt} className="h-80 w-full object-contain" />
          <span className="absolute top-2 left-2"><Tag>{t.alt}</Tag></span>
        </div>
        <Button label={t.again} variant="ghost" size="sm" onClick={onAgain} />
      </div>
    )
  }
  return (
    <div className="flex w-full flex-col items-center gap-2">
      {placeholder}
      {state === "none" && <Button label={t.make} size="sm" onClick={onMake} />}
      {state === "working" && <Spinner size="sm" label={t.working} aria-label={t.workingLabel} />}
      {state === "failed" && (
        <div className="flex flex-col items-center gap-1 text-center">
          <Text>{t.failed}</Text>
          <Button label={t.retry} size="sm" onClick={onMake} />
        </div>
      )}
    </div>
  )
}
