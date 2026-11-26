import { Heading } from "@astryxdesign/core/Heading"
import { Text } from "@astryxdesign/core/Text"
import { VStack } from "@astryxdesign/core/VStack"
import { copy } from "../copy"

/**
 * 첫 화면의 인사 두 줄. 첫 줄은 검정, 둘째 줄은 같은 크기의 회색. 두 줄 사이를 띄우지 않는다.
 * 둘째 줄과 그 아래 작은 한 줄은 고른 부분(컨셉 기획, 매대 테스트)에 따라 바뀐다.
 * 낱말 단위로 줄을 바꾸고 좁으면 한 단계 작은 글씨가 된다(테마의 data-greeting).
 */
export function Greeting({
  prompt = copy.home.concept.prompt,
  sub,
}: {
  prompt?: string
  sub?: string
}) {
  return (
    <div data-greeting>
    <VStack gap={3} hAlign="center">
      <VStack gap={0} hAlign="center">
        <Heading level={1} type="display-2" justify="center">
          {copy.home.greeting}
        </Heading>
        <Heading level={2} type="display-2" color="secondary" justify="center" accessibilityLevel={2}>
          {prompt}
        </Heading>
      </VStack>
      {sub && (
        <Text color="secondary" justify="center">
          {sub}
        </Text>
      )}
    </VStack>
    </div>
  )
}
