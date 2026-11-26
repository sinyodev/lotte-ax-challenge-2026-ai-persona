import { EmptyState } from "@astryxdesign/core/EmptyState"
import { copy } from "../copy"

/** "준비하고 있어요" 빈 상태. */
export function PreparingState() {
  return <EmptyState title={copy.pages.preparing} headingLevel={2} />
}
