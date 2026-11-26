import { NewspaperIcon, PlusIcon, TableCellsIcon } from "@heroicons/react/20/solid"
import { ideasCopy } from "../copy/ideas"
import { copy } from "../copy"
import { trendCopy } from "../copy/trend"

/**
 * 왼쪽 메뉴의 아이콘은 모두 heroicons의 20px 묶음(20/solid) 하나에서 가져와 20px로 쓴다.
 * 더하기와 아래쪽 항목의 굵기와 크기가 같다. 고른 항목은 같은 아이콘을 강조색으로 칠한다.
 * 지시서 23: "소비자 패널"(/panel, UserGroupIcon)과 "신뢰도"(/reliability, ShieldCheckIcon)는 메뉴에서만 숨긴다.
 * 11-24(참가자 검수): "매대"(/store, Squares2X2Icon)도 메뉴에서만 숨긴다.
 * 화면, 주소, copy의 문구는 남아 있어 이 목록에 다시 넣으면 되살아난다.
 */
export const newTestItem = { href: "/", label: copy.nav.newChat, icon: PlusIcon }

export const mainNavItems = [
  { href: "/trends", label: trendCopy.title, icon: NewspaperIcon },
  { href: "/ideas", label: ideasCopy.title, icon: TableCellsIcon },
] as const
