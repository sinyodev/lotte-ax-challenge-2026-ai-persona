export const ideasHistoryCopy = {
  empty: "비슷한 과거 사례를 찾지 못했어요.",
  noOriginal: "기획 원문 기록 없음",
  noReason: "사유 기록 없음",
  noConcept: "기록 없음",
  concept: "당시 컨셉",
  reasonLabel: "접은 이유",
  overlapLabel: "겹치는 조건",
  overlap: (conditions: string) => `겹치는 조건 · ${conditions}`,
  status: { 출시: "출시", 단종: "단종", 폐기: "개발 중단" },
} as const
