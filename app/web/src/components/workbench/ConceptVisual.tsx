/**
 * 컨셉 보드의 그림 자리. 그림이 없으면 옅은 면에 용기 아이콘의 윤곽을 그리고,
 * 대화 안(chatId가 있을 때)에서는 그 아래에 예시 이미지를 만드는 버튼이 붙는다.
 * 너비는 부모가 정한다.
 */
import { copy } from "../../copy"
import type { ConceptItem } from "../../chat/contract"
import type { Container } from "../../fixtures/confirmedConcepts"
import { CONTAINER_ICONS } from "../ContainerIcon"
import { ConceptImage } from "../concept/ConceptImage"

/** 매대에 올릴 규격의 이름(없으면 용기와 용량)에서 용기를 읽는다. 모르면 null(면만). */
function containerFor(concept: ConceptItem): Container | null {
  const shelf = concept.variants?.[concept.shelf_variant ?? 0]?.label
  for (const text of [shelf, concept.pack]) {
    if (!text) continue
    if (/캔/.test(text)) return "can"
    if (/PET|페트/i.test(text)) return "pet"
    if (/병/.test(text)) return "bottle"
  }
  return null
}

export type ConceptVisualProps = { chatId?: string; concept: ConceptItem }

export function ConceptVisual(props: ConceptVisualProps) {
  const { concept } = props
  const container = containerFor(concept)
  const Shape = container ? CONTAINER_ICONS[container] : null
  const blank = (
    <div
      data-concept-image
      role="img"
      aria-label={copy.workbench.conceptImage}
      className="flex min-h-36 w-full items-center justify-center"
    >
      {Shape && <Shape aria-hidden className="h-24 w-24" data-concept-shape />}
    </div>
  )
  if (!props.chatId) return blank
  return <ConceptImage chatId={props.chatId} conceptId={concept.id} placeholder={blank} />
}
