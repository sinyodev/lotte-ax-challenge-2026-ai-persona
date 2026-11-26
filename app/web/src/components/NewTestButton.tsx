import { Button } from "@astryxdesign/core/Button"
import { Icon } from "@astryxdesign/core/Icon"
import { newTestItem } from "./navItems"

/**
 * 왼쪽 메뉴 맨 위의 "새 대화" 버튼. 고른 메뉴처럼 보이지 않게 메뉴 항목이 아니라 버튼으로 둔다.
 * 흰 바탕, 1px 테두리, 높이 40px은 테마(themes/lotte/overrides.css)에 있다.
 */
export function NewTestButton({ isIconOnly = false }: { isIconOnly?: boolean }) {
  return (
    <Button
      label={newTestItem.label}
      href={newTestItem.href}
      icon={<Icon icon={newTestItem.icon} />}
      isIconOnly={isIconOnly}
      tooltip={isIconOnly ? newTestItem.label : undefined}
      variant="secondary"
      size="lg"
      width="100%"
    />
  )
}
