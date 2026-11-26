/** 견본: 가상 소비자 300명의 예시 선택. 실제 테스트의 값이 아니다. */
import type { PlanId } from "./data"

export type Phase = "prev" | PlanId
export const SIZE = 300
// 씨앗을 고정해 섞는다
const P = (() => {
  const a = Array.from({ length: SIZE }, (_, i) => i)
  let x = 20261124
  for (let i = SIZE - 1; i > 0; i--) {
    x = (x * 48271) % 2147483647
    const j = x % (i + 1)
    ;[a[i], a[j]] = [a[j], a[i]]
  }
  return a
})()
const span = (a: number, b: number) => P.slice(a, b)
export const picks: Record<Phase, Set<number>> = {
  prev: new Set([...span(0, 18), ...span(200, 212)]),
  base: new Set(span(0, 24)),
  a: new Set([...span(2, 24), ...span(30, 42)]),
  b: new Set([...span(0, 22), ...span(42, 51)]),
  c: new Set([...span(0, 20), ...span(24, 30)]),
  ab: new Set([...span(3, 24), ...span(30, 52)]),
}

const jobs = ["대학생", "취업 준비생", "회사원", "대학원생", "매장 직원", "간호사"]
const places = ["오후 수업 뒤 편의점에 들러요", "점심 먹고 편의점에 들러요", "퇴근길 편의점에 들러요", "공부하다 편의점에 나와요"]
const usual = ["칠성사이다 제로", "코카콜라 제로", "밀키스 오리지널", "보리차", "아메리카노", "포카리스웨트"]

export function person(i: number) {
  const at = P.indexOf(i)
  const kind =
    (at >= 30 && at < 42) || (at >= 204 && at < 212) ? "price"
    : (at >= 42 && at < 52) || (at >= 200 && at < 204) ? "sweet"
    : at >= 18 && at < 24 ? "soda"
    : at < 18 ? "fan"
    : at < 30 ? "memory"
    : i % 5 === 0 ? "sweet" : i % 3 === 0 ? "price" : "habit"
  const drink = usual[(i * 5) % usual.length]
  return {
    who: `${19 + ((i * 3) % 11)}세 ${i % 2 ? "여성" : "남성"}, ${jobs[(i * 7) % jobs.length]}`,
    own: [places[i % places.length], `늘 ${drink}를 마셔요`],
    real: [
      kind === "price" ? "1,500원까지 낼 수 있어요" : "1,800원을 낼 수 있어요",
      kind === "sweet" ? "단맛이 걱정돼요" : "맛에는 걱정이 없어요",
      kind === "soda" || kind === "memory" || kind === "fan" ? "화채 맛이 궁금해요" : "화채에는 별생각이 없어요",
    ],
    drink,
    kind,
  }
}

export function said(i: number, phase: Phase): string {
  const p = person(i)
  if (picks[phase].has(i)) {
    if ((phase === "a" || phase === "ab") && p.kind === "price") return "1,500원이면 한번 마셔 볼 만해서 골랐어요."
    if ((phase === "b" || phase === "ab") && p.kind === "sweet") return "덜 달다고 해서 골랐어요."
    if (p.kind === "soda" && phase !== "prev") return "화채 맛이 궁금해서 골랐어요."
    return "화채 맛이 궁금해서 골랐어요."
  }
  const why = p.kind === "price" ? "가격이 부담돼요." : p.kind === "sweet" ? "너무 달 것 같아요." : p.kind === "fan" || p.kind === "soda" ? "오늘은 다른 게 끌려요." : "늘 마시던 게 있어요."
  return `${p.drink}를 골랐어요. ${why}`
}
