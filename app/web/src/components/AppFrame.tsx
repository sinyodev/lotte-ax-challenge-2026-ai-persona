import { useEffect, useState, type ReactNode } from "react"
import { useLocation, useNavigate } from "react-router"
import { AppShell } from "@astryxdesign/core/AppShell"
import { Avatar } from "@astryxdesign/core/Avatar"
import { SideNav, SideNavCollapseButton, SideNavHeading, SideNavSection } from "@astryxdesign/core/SideNav"
import { HStack } from "@astryxdesign/core/HStack"
import { Text } from "@astryxdesign/core/Text"
import { VStack } from "@astryxdesign/core/VStack"
import { copy } from "../copy"
import { isChatPath, useRecentChats } from "../chat/recentChats"
import { MainNavLinks } from "./MainNavLinks"
import { NewTestButton } from "./NewTestButton"
import { RecentChatList } from "./RecentChatList"

/** 맨 아래 담당자 줄. 접으면 원만 메뉴의 가운데 축에 놓인다. */
export function OwnerRow({ isCollapsed }: { isCollapsed: boolean }) {
  if (isCollapsed) {
    return (
      <div className="flex justify-center">
        <Avatar name={copy.app.owner} size={32} tooltip={copy.app.owner} />
      </div>
    )
  }
  return (
    <HStack gap={2} vAlign="center" paddingInline={2}>
      <Avatar name={copy.app.owner} size={32} tooltip={false} />
      <Text weight="medium">{copy.app.owner}</Text>
    </HStack>
  )
}

/**
 * 앱의 틀: 왼쪽 메뉴(둥근 판) + 흰 본문. 대화 화면(/concept/..., /test/...)에 들어가면 메뉴가 접힌다.
 * 메뉴 안: 새 대화 버튼 → 최근 대화 → (아래쪽) 트렌드 피드·매대 → 담당자 줄.
 * 최근 대화는 서버의 실제 목록이다(지시서 11). 주소가 바뀔 때와 차례가 시작하고 끝날 때(대화 화면이 부른다) 다시 받는다.
 * 비어 있으면 "최근 대화" 제목도 보이지 않는다.
 */
export function AppFrame({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const { chats, refresh, remove } = useRecentChats()
  const inTest = pathname.startsWith("/test") || pathname.startsWith("/concept")
  const [isCollapsed, setIsCollapsed] = useState(inTest)

  useEffect(() => {
    setIsCollapsed(inTest)
  }, [inTest])

  useEffect(() => {
    void refresh()
  }, [pathname, refresh])

  const deleteChat = async (id: string) => {
    const wasOpen = isChatPath(pathname, id)
    const ok = await remove(id)
    // 지금 열린 대화를 지웠으면 첫 화면으로 간다
    if (ok && wasOpen) navigate("/")
  }

  return (
    <AppShell
      variant="surface"
      sideNav={
        <SideNav
          aria-label={copy.nav.label}
          collapsible={{ isCollapsed, onCollapsedChange: setIsCollapsed, hasButton: false }}
          header={
            <HStack gap={1} vAlign="center" justify="between">
              {!isCollapsed && <SideNavHeading heading={copy.app.name} headingHref="/" />}
              <SideNavCollapseButton />
            </HStack>
          }
          topContent={<NewTestButton isIconOnly={isCollapsed} />}
          footer={
            <VStack gap={3}>
              <MainNavLinks isCollapsed={isCollapsed} pathname={pathname} />
              <OwnerRow isCollapsed={isCollapsed} />
            </VStack>
          }
        >
          {!isCollapsed && chats.length > 0 && (
            <SideNavSection title={copy.nav.recentChats}>
              <RecentChatList chats={chats} selectedHref={pathname} onDelete={deleteChat} />
            </SideNavSection>
          )}
        </SideNav>
      }
    >
      {children}
    </AppShell>
  )
}
