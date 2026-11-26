import { Button } from "@astryxdesign/core/Button"
import { Icon } from "@astryxdesign/core/Icon"
import { SideNavItem, SideNavSection } from "@astryxdesign/core/SideNav"
import { VStack } from "@astryxdesign/core/VStack"
import { copy } from "../copy"
import { mainNavItems } from "./navItems"

/**
 * 왼쪽 메뉴 아래쪽의 항목(지금은 매대 하나. 지시서 23).
 * 접었을 때: 더하기 버튼과 같은 40px 원형 버튼을 메뉴의 가운데 축에 세로로 놓는다. 올려놓으면 옅은 면과 이름 풍선.
 * 펼쳤을 때: 메뉴 항목(같은 아이콘, 20px). 아이콘은 보조 글씨색, 고른 것만 강조색.
 */
export function MainNavLinks({ isCollapsed, pathname }: { isCollapsed: boolean; pathname?: string }) {
  if (isCollapsed) {
    return (
      <nav aria-label={copy.nav.label} data-rail-links className="flex flex-col items-center">
        <VStack gap={1} hAlign="center">
          {mainNavItems.map((item) => {
            const isSelected = pathname === item.href
            return (
              <div key={item.href} data-rail-link data-selected={isSelected || undefined}>
                <Button
                  label={item.label}
                  href={item.href}
                  variant="ghost"
                  size="lg"
                  isIconOnly
                  tooltip={item.label}
                  icon={<Icon icon={item.icon} size="md" color={isSelected ? "accent" : "secondary"} />}
                  aria-current={isSelected ? "page" : undefined}
                />
              </div>
            )
          })}
        </VStack>
      </nav>
    )
  }
  return (
    <SideNavSection title={copy.nav.label} isHeaderHidden>
      {mainNavItems.map((item) => (
        <SideNavItem
          key={item.href}
          label={item.label}
          icon={<Icon icon={item.icon} size="md" color="secondary" />}
          selectedIcon={<Icon icon={item.icon} size="md" color="accent" />}
          href={item.href}
          isSelected={pathname === item.href}
        />
      ))}
    </SideNavSection>
  )
}
