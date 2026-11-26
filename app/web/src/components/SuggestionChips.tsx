import { Token } from "@astryxdesign/core/Token"
import { copy } from "../copy"

/** 추천 칩. 누르면 칩의 말을 그대로 넘긴다. 칩 사이 10px. */
export function SuggestionChips({
  items = copy.home.concept.suggestions,
  onPick,
}: {
  items?: readonly string[]
  onPick?: (text: string) => void
}) {
  return (
    <div role="group" className="flex flex-wrap justify-center gap-2.5" aria-label={copy.home.suggestionsLabel}>
      {items.map((s) => (
        <Token key={s} label={s} size="lg" onClick={onPick ? () => onPick(s) : undefined} />
      ))}
    </div>
  )
}
