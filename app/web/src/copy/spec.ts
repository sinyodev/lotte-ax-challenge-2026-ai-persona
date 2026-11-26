/** 지시서 33: 아이디어 카드와 컨셉 보드의 제품 사양 묶음(규격이 열, 항목이 행인 표). */
export const specCopy = {
  /** 표의 행 이름 */
  factoryPrice: "출고가",
  retail: "권장 소비자가",
  /** 좁은 카드에서만 쓰는 짧은 이름 */
  retailShort: "소비자가",
  shelfLife: "유통기한",
  /** 11-25: 규격이 하나인 표의 첫 줄 */
  pack: "용기와 용량",
  kcal: "열량",
  /** 표 아래, 규격과 상관없는 것 */
  launch: "출시",
  channels: "채널",
  /** 칠성이가 어림한 값(유통기한, 열량)에 붙는 표시 */
  estimated: "추정값",
  /** 컨셉 보드: 매대에 올린 규격의 열 머리에 붙는 표시 */
  shelfMark: "매대 테스트", // 임시
  onShelf: "매대에 올릴 규격",
  /** /design 견본 페이지의 절 이름 */
  designTitle: "제품 사양 묶음",
  lockedShelf: "확정한 컨셉이라 규격을 바꿀 수 없어요.",
  /** 매대에 올릴 규격을 바꿀 때 대화에 남는 기획자의 말. */
  switchSay: (label: string) => `매대에 올릴 규격을 ${label}로 바꿔 줘`,
  won: (n: number) => `${n.toLocaleString("ko-KR")}원`,
  volume: (n: number) => `${n} mL`,
  months: (n: number) => `${n}개월`,
  days: (n: number) => `${n}일`,
  kcalValue: (n: number) => `${n} kcal`,
  /** "2027-05" → "2027. 05". 형식이 다르면 그대로. */
  launchValue: (v: string) => {
    const m = /^(\d{4})-(\d{1,2})$/.exec(v.trim())
    return m ? `${m[1]}. ${m[2].padStart(2, "0")}` : v
  },
} as const
