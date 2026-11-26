/**
 * W6 UX 시안(/proto/w6)의 숫자.
 * survey는 제공 조사의 20대 응답(정제 뒤 134명) 집계, virtual은 예시(실제 테스트의 값이 아니다).
 */
export const survey = {
  raw: 304,
  removed: 28,
  clean: 276,
  target: 134,
  intent: 70,
  priceOk: 41,
  /** 가격마다 "이 돈을 낼 수 있다"의 비율(가중)과, 가격을 곱해 100명에게서 나오는 돈(만 원) */
  curve: [
    { price: 1400, share: 83, money: 11.6 },
    { price: 1500, share: 80, money: 12.0 },
    { price: 1600, share: 69, money: 11.0 },
    { price: 1700, share: 59, money: 10.1 },
    { price: 1800, share: 51, money: 9.2 },
    { price: 1900, share: 39, money: 7.5 },
    { price: 2000, share: 24, money: 4.8 },
  ],
}

export type PlanId = "base" | "a" | "b" | "c" | "ab"
/** 예시: 같은 가상 소비자 300명 */
export const plans: { id: PlanId; picked: number; gained?: number; lost?: number; sales: number; low: number; high: number; net: number; verdict?: "more" | "unclear" }[] = [
  { id: "base", picked: 24, sales: 48, low: 34, high: 62, net: 34 },
  { id: "a", picked: 34, gained: 12, lost: 2, sales: 57, low: 42, high: 72, net: 40, verdict: "more" },
  { id: "b", picked: 31, gained: 9, lost: 2, sales: 62, low: 45, high: 79, net: 44, verdict: "more" },
  { id: "c", picked: 26, gained: 6, lost: 4, sales: 52, low: 37, high: 67, net: 37, verdict: "unclear" },
  { id: "ab", picked: 43, gained: 22, lost: 3, sales: 72, low: 54, high: 90, net: 51, verdict: "more" },
]
export const people = 300
