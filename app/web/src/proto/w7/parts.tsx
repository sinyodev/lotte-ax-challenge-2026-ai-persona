import type { ReactNode } from "react"
import { Card } from "@astryxdesign/core/Card"
import { Heading } from "@astryxdesign/core/Heading"
import { HStack } from "@astryxdesign/core/HStack"
import { Icon } from "@astryxdesign/core/Icon"
import { Text } from "@astryxdesign/core/Text"
import { VStack } from "@astryxdesign/core/VStack"
import { Tag } from "../../components/workbench/OriginTag"
import { w7 } from "./copy"
import { people, type PersonId, type Source, type Turn } from "./data"

export const personOf = (id: PersonId) => people.find((p) => p.id === id)!

/** 발언 한 줄의 화자 이름(칠성이 또는 "24세 여성, 대학생") */
export function speakerLabel(t: Turn) {
  return t.person === "host" ? w7.c.host : w7.personLabel(personOf(t.person))
}

/** 기획자의 말풍선과 근거 표시에 쓰는 짧은 이름: "24세 여성, 대학생, 2차, 고름" */
export function quoteLabel(t: Turn) {
  if (t.person === "host") return w7.c.host
  const p = personOf(t.person)
  return w7.e.quoteBy(w7.personLabel(p), w7.d.round(t.round), p.picked ? w7.c.picked : w7.c.passed)
}

/** 자료의 출처 표시. 제공 자료 집계는 면, 시연용 응답은 점선. */
export function SourceMark({ source }: { source: Source }) {
  return <Tag isDashed={source === "demo"}>{w7.source[source]}</Tag>
}

/** 걸림 / 괜찮음 표시 */
export function FlagMark({ isFlag }: { isFlag: boolean }) {
  return (
    <span data-proto-flag={isFlag ? "flag" : "ok"} className="inline-flex shrink-0 items-center gap-1">
      <Icon icon={isFlag ? "warning" : "check"} size="sm" color={isFlag ? "primary" : "secondary"} />
      <Text type="supporting" weight="medium" color={isFlag ? "primary" : "secondary"}>
        {isFlag ? w7.mark.flag : w7.mark.ok}
      </Text>
    </span>
  )
}

/** 작업대의 카드 한 장. 제목 옆에 출처 표시. */
export function BenchCard({
  title,
  source,
  aside,
  children,
}: {
  title: string
  source?: Source
  aside?: ReactNode
  children: ReactNode
}) {
  return (
    <Card padding={5}>
      <VStack gap={4}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <HStack gap={2} vAlign="center" wrap="wrap">
            <Heading level={3}>{title}</Heading>
            {source && <SourceMark source={source} />}
          </HStack>
          {aside}
        </div>
        {children}
      </VStack>
    </Card>
  )
}

/** 카드 안의 작은 머리 */
export function SubHead({ children }: { children: ReactNode }) {
  return (
    <Text type="label" weight="semibold">
      {children}
    </Text>
  )
}

/** 고를 수 있는 한 줄의 표시 자리. 처음부터 자리가 있고 고르면 채워진다(크기가 바뀌지 않는다). */
export function RadioMark({ isOn }: { isOn: boolean }) {
  return <span data-proto-radio data-on={isOn || undefined} aria-hidden="true" />
}
