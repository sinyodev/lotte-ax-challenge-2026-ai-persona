import { useCallback, useEffect, useState } from "react"
import { useChat } from "@ai-sdk/react"
import { DefaultChatTransport, type ChatStatus } from "ai"
import type { ChilseongMessage } from "./contract"
import { useRecentChats } from "./recentChats"

export type ChatSnapshot = { messages: ChilseongMessage[]; working?: boolean }

const transport = new DefaultChatTransport<ChilseongMessage>({ api: "/api/chat" })
const chatUrl = (id: string) => `/api/chats/${encodeURIComponent(id)}`
const pollMs = 2000

// 화면을 떠나도 최근 대화 목록은 남아 있다. 일하는 대화가 모두 끝날 때까지 목록 표시도 갱신한다.
let recentTimer: number | undefined
function followRecentChats() {
  if (recentTimer !== undefined) return
  recentTimer = window.setTimeout(async () => {
    await useRecentChats.getState().refresh()
    recentTimer = undefined
    if (useRecentChats.getState().chats.some((chat) => chat.status === "working")) followRecentChats()
  }, pollMs)
}

export async function loadChat(id: string, signal?: AbortSignal): Promise<ChatSnapshot | null> {
  const response = await fetch(chatUrl(id), { signal, cache: "no-store" })
  if (response.status === 404) return null
  if (!response.ok) throw new Error(String(response.status))
  return response.json()
}

/** 다시 연 차례는 조회로 따라가고, 여기서 보낸 차례는 useChat의 스트림을 받는다. */
export function useChatTurn(id: string, initial: ChatSnapshot) {
  const { messages, setMessages, sendMessage, regenerate, stop, status, error } = useChat<ChilseongMessage>({
    id,
    messages: initial.messages,
    transport,
  })
  const [following, setFollowing] = useState(Boolean(initial.working))
  const [stopping, setStopping] = useState(false)
  const displayStatus: ChatStatus = following || stopping ? "streaming" : status
  const busy = displayStatus === "streaming" || displayStatus === "submitted"

  useEffect(() => {
    if (busy) return followRecentChats
  }, [busy])

  useEffect(() => {
    if (!following || stopping) return
    const controller = new AbortController()
    let timer: number
    async function poll() {
      try {
        const snapshot = await loadChat(id, controller.signal)
        if (controller.signal.aborted) return
        setMessages(snapshot?.messages ?? [])
        if (!snapshot?.working) {
          setFollowing(false)
          return
        }
      } catch {
        // 일시적으로 조회에 실패해도 현재 메시지를 두고 다시 받는다.
      }
      if (!controller.signal.aborted) timer = window.setTimeout(poll, pollMs)
    }
    timer = window.setTimeout(poll, pollMs)
    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [following, stopping, id, setMessages])

  const stopTurn = useCallback(async () => {
    if (stopping) return
    setStopping(true)
    try {
      const response = await fetch(`${chatUrl(id)}/stop`, { method: "POST" })
      if (!response.ok) return
      await stop()
      // 완료와 멈춤이 엇갈려도 서버가 저장한 마지막 차례와 같은 모습으로 맞춘다.
      setFollowing(true)
      const snapshot = await loadChat(id)
      setMessages(snapshot?.messages ?? [])
      setFollowing(Boolean(snapshot?.working))
    } catch {
      // 멈춤을 확인한 뒤 조회만 실패했으면 위의 주기적 조회가 이어받는다.
    } finally {
      setStopping(false)
    }
  }, [id, setMessages, stop, stopping])

  return { messages, sendMessage, regenerate, stopTurn, status: displayStatus, error }
}
