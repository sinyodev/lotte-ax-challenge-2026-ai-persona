import { ArrowRightIcon } from "@heroicons/react/20/solid"
import { HStack } from "@astryxdesign/core/HStack"
import { Icon } from "@astryxdesign/core/Icon"
import { Text } from "@astryxdesign/core/Text"
import { VStack } from "@astryxdesign/core/VStack"
import { copy } from "../copy"
import type { ConfirmedConcept } from "../fixtures/confirmedConcepts"
import { CONTAINER_ICONS } from "./ContainerIcon"

/**
 * 첫 화면의 매대 테스트 쪽, 칩 자리에 놓이는 확정한 컨셉 카드. 카드 한 장 = 한 대화에서 확정한 컨셉 묶음.
 * 컨셉마다 두 줄: 컨셉의 이름(굵게), 그 아래 용기 아이콘과 용기와 용량, 오른쪽 끝에 줄 맞춘 가격. 맨 아래 점선 위로 "매대에 올리기".
 * 대화의 제목(제품)은 카드마다 비슷해 구별되지 않으므로 컨셉의 이름을 앞에 세운다(지시서 17의 D).
 * 확정한 컨셉이 없으면 안내 한 줄. 카드의 모양은 테마(themes/lotte/overrides.css의 data-concept-bundle)에 있다.
 */
export function ConfirmedConceptCards({
  concepts,
  onPick,
}: {
  concepts: ConfirmedConcept[]
  onPick?: (concept: ConfirmedConcept) => void
}) {
  if (concepts.length === 0) {
    return (
      <Text as="p" display="block" color="secondary" justify="center">
        {copy.home.test.noConcepts}
      </Text>
    )
  }
  const t = copy.home.test
  return (
    <div role="group" aria-label={t.conceptsLabel} className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
      {concepts.map((c) => (
        <button
          key={c.id}
          type="button"
          data-concept-bundle
          className="flex h-full flex-col text-start"
          onClick={onPick ? () => onPick(c) : undefined}
        >
          <div className="flex-1 px-4 pt-3 pb-2.5">
            <VStack gap={2}>
              {c.concepts.map((k) => (
                <VStack key={k.id} gap={0.5}>
                  <Text weight="semibold" maxLines={1}>
                    {k.name || c.name}
                  </Text>
                  <div className="flex items-center justify-between gap-3">
                    <HStack gap={1.5} vAlign="center">
                      {k.container ? (
                        <Icon icon={CONTAINER_ICONS[k.container]} size="sm" color="secondary" label={t.containers[k.container]} />
                      ) : (
                        <span aria-hidden className="inline-block w-4" />
                      )}
                      <Text hasTabularNumbers>{k.pack}</Text>
                    </HStack>
                    <Text weight="medium" hasTabularNumbers>
                      {k.price}
                    </Text>
                  </div>
                </VStack>
              ))}
            </VStack>
          </div>
          <div data-concept-bundle-foot className="mx-4 flex items-center justify-between py-2.5">
            <Text weight="medium">{t.toShelf}</Text>
            <Icon icon={ArrowRightIcon} size="sm" color="primary" />
          </div>
        </button>
      ))}
    </div>
  )
}
