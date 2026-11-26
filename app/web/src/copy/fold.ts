/** 작업대에서 접히는 카드(기획 브리프, 찾아본 것, 트렌드 조사, 비슷한 과거 사례)의 글. 접히면 결론 한 줄만 보인다. */

/** 끝 글자에 받침이 있는가(한글이 아니면 없다고 본다). */
const hasFinal = (word: string) => {
  const code = word.trim().charCodeAt(word.trim().length - 1)
  return code >= 0xac00 && code <= 0xd7a3 && (code - 0xac00) % 28 !== 0
}

export const foldCopy = {
  expandAll: "모두 펼치기",
  collapseAll: "요약만 보기",
  brief: (target: string, occasion: string) => `${target} 타깃의 '${occasion}' 음료예요`,
  trend: (keyword: string, stages: string[]) => {
    const stage = stages.join(", ")
    return `${keyword} 검색은 ${stage}${hasFinal(stage) ? "이에요" : "예요"}`
  },
  history: (name: string, status: string) => `비슷한 제품이 ${status}된 적이 있어요(${name})`,
} as const
