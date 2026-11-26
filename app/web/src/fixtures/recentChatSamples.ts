/**
 * 견본 자료. 견본 페이지(/design)에서만 쓰는 최근 대화의 견본이다. 실제 목록은 서버의 GET /api/chats(chat/recentChats.ts).
 * 날짜는 오늘로부터 며칠 전인지로 적어 둔다(언제 열어도 "오늘", "어제" 묶음이 보이게).
 */
import type { RecentChat } from "../chat/recentChats"

const daysAgo = (n: number, hour = 10) => {
  const d = new Date()
  d.setDate(d.getDate() - n)
  d.setHours(hour, 0, 0, 0)
  return d
}

export const recentChatSamples: RecentChat[] = [
  { id: "zero-soda-500", title: "제로 탄산 500ml 페트", updatedAt: daysAgo(0, 15), status: "working", part: "concept", step: 1, concepts: [] },
  { id: "na-highball-can", title: "무알코올 하이볼 캔", updatedAt: daysAgo(0, 11), status: "waiting", part: "concept", step: 0, concepts: [] },
  { id: "lime-zero", title: "라임 제로 캔과 페트", updatedAt: daysAgo(1), status: "idle", part: "concept", step: 2, concepts: [] },
  { id: "low-sugar-ade", title: "저당 과일 에이드", updatedAt: daysAgo(3), status: "idle", part: "test", step: 4, concepts: [] },
  { id: "barley-tea-pet", title: "보리차 1.5L 페트", updatedAt: daysAgo(12), status: "idle", part: "concept", step: 2, concepts: [] },
]
