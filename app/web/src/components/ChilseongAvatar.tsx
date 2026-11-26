import { useEffect, useRef } from "react"
import { mountAvatar, type MountedAvatar } from "open-bot-avatar/dom"
import { copy } from "../copy"
import { chilseongShape } from "./chilseongShape"

export type ChilseongMood = "idle" | "thinking" | "happy"

/**
 * 칠성이. 통통한 캔 모양의 캐릭터이고 눈을 깜빡이며 마우스를 따라 본다.
 * 초록은 칠성이에게만 쓰는 색이다. 값은 테마의 --color-chilseong(themes/lotte/overrides.css)에 있다.
 */
export function ChilseongAvatar({ size = 120, mood = "idle" }: { size?: number; mood?: ChilseongMood }) {
  const host = useRef<HTMLDivElement>(null)
  const avatar = useRef<MountedAvatar | null>(null)

  useEffect(() => {
    const el = host.current
    if (!el) return
    const color = getComputedStyle(el).getPropertyValue("--color-chilseong").trim()
    avatar.current = mountAvatar(el, {
      definition: chilseongShape,
      color,
      followPointer: true,
      label: copy.home.avatar,
    })
    return () => {
      avatar.current?.destroy()
      avatar.current = null
    }
  }, [])

  useEffect(() => {
    avatar.current?.update({ mood })
  }, [mood])

  return <div ref={host} style={{ width: size, aspectRatio: "1" }} />
}
