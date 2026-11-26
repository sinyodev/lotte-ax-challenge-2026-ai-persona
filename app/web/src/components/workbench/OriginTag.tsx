import type { ReactNode } from "react"
import { Link } from "@astryxdesign/core/Link"
import { Text } from "@astryxdesign/core/Text"
import { copy, ORIGIN_LABELS } from "../../copy"
import { researchCopy } from "../../copy/trend"
import type { Origin } from "../../chat/contract"

/** 작은 이름표 하나. 모양은 테마(overrides.css의 data-tag)에 있다. */
export function Tag({ children, isDashed = false }: { children: ReactNode; isDashed?: boolean }) {
  return (
    <span data-tag={isDashed ? "dashed" : "plain"}>
      <Text type="supporting" weight="medium" color="primary">
        {children}
      </Text>
    </span>
  )
}

/**
 * 카드 제목 옆의 표시(약속 v1.3). 칠성이가 낸 카드("suggestion")에만 "칠성이의 제안"을 붙이고, 나머지는 그리지 않는다.
 */
export function OriginTag({ origin }: { origin: Origin }) {
  const label = origin === "internal" ? researchCopy.internal : ORIGIN_LABELS[origin]
  if (!label) return null
  return <Tag>{label}</Tag>
}

/**
 * 찾아본 것의 항목에 붙는 출처의 이름(약속 v1.3 source). 길면 한 줄에서 자르고 올려놓으면 전부 보인다.
 * 웹에서 찾은 것은 면 없이 점선이고, 주소가 있으면 이름표가 새 창 링크다.
 */
export function SourceTag({ source, isWeb, url }: { source: string; isWeb: boolean; url?: string }) {
  const name = (
    <Text type="supporting" weight="medium" color="primary" maxLines={1}>
      {source}
    </Text>
  )
  return (
    <span data-tag={isWeb ? "dashed" : "plain"} data-source-tag>
      {url ? (
        <Link href={url} isExternalLink newTabLabel={copy.workbench.newTab} type="supporting" color="primary">
          {name}
        </Link>
      ) : (
        name
      )}
    </span>
  )
}
