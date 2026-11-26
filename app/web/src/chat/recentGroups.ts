/** 최근 대화를 날짜 묶음(오늘, 어제, 지난 7일, 그 전)으로 나눈다. 묶음 안은 받은 순서 그대로다. */
export const RECENT_GROUPS = ["today", "yesterday", "week", "older"] as const
export type RecentGroup = (typeof RECENT_GROUPS)[number]

const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
const DAY = 24 * 60 * 60 * 1000

export function recentGroupOf(date: Date, now = new Date()): RecentGroup {
  const days = Math.round((startOfDay(now) - startOfDay(date)) / DAY)
  if (days <= 0) return "today"
  if (days === 1) return "yesterday"
  if (days < 7) return "week"
  return "older"
}

export function groupRecent<T extends { updatedAt: Date }>(items: T[], now = new Date()) {
  return RECENT_GROUPS.map((g) => ({ group: g, items: items.filter((i) => recentGroupOf(i.updatedAt, now) === g) })).filter(
    (g) => g.items.length > 0,
  )
}
