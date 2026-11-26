import { ClipboardDocumentIcon } from "@heroicons/react/20/solid"
import { useEffect, useState } from "react"
import { Button } from "@astryxdesign/core/Button"
import { Icon } from "@astryxdesign/core/Icon"
import { copy } from "../../copy"

const t = copy.proposal
const RESET_MS = 2000

/**
 * "LLM용 복사"(지시서 22의 E). 누르면 markdown을 클립보드에 넣고 2초 동안 "복사했어요"(막힌 환경이면 "복사하지 못했어요").
 * markdown이 없으면(종이가 아직 오지 않음) 누를 수 없다.
 */
export function CopyMarkdownButton({ markdown }: { markdown: string | null }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle")
  useEffect(() => {
    if (state === "idle") return
    const id = window.setTimeout(() => setState("idle"), RESET_MS)
    return () => window.clearTimeout(id)
  }, [state])

  const onClick = () => {
    if (!markdown) return
    const clip = typeof navigator !== "undefined" ? navigator.clipboard : undefined
    if (!clip?.writeText) {
      setState("failed")
      return
    }
    clip.writeText(markdown).then(
      () => setState("copied"),
      () => setState("failed"),
    )
  }

  return (
    <Button
      label={state === "copied" ? t.copied : state === "failed" ? t.copyFailed : t.copyLlm}
      variant="secondary"
      size="sm"
      icon={<Icon icon={ClipboardDocumentIcon} />}
      isDisabled={!markdown}
      onClick={onClick}
    />
  )
}
