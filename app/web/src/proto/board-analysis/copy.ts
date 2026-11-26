import { diagnoseCopy as d } from "../../copy/diagnose"

const count = (n: number) => ["", "한", "두", "세", "네"][n] ?? String(n)

/** 견본(/proto/analysis)의 대화: 칠성이가 분석을 인사이트로 정리하고 매대 테스트를 제안한다. 숫자는 코드가 넣는다. */
export const boardAnalysisCopy = {
  stage: "컨셉 보드 분석",
  planner: "이 컨셉으로 확정하기",
  placeholder: "칠성이에게 말하기",
  loading: "분석 자료를 불러오고 있어요.",
  missing: "이 대화에서 컨셉 보드 분석을 찾지 못했어요. 주소 끝에 ?chat=대화 id를 붙여 주세요.",
  lead: (flags: number) => flags
    ? `이 컨셉으로 정했어요. 분석에서 살펴볼 점이 ${count(flags)} 가지 나왔어요.`
    : "이 컨셉으로 정했어요. 분석에서 테스트를 막는 점은 없었어요.",
  cooling: (word: string, pct: number) => `${word} 검색은 올여름 정점이 작년 여름의 ${pct}%예요.`,
  priceOver: (current: number, median: number, gap: number) =>
    `${d.won(current)}은 소비자가 내겠다는 값(${d.won(median)})보다 ${d.won(gap)} 높아요.`,
  cheaper: (n: number, low: number) => `다만 같은 용량의 다른 제품 ${n}종(${d.won(low)}부터)보다는 싸요.`,
  propose: (a: number, b: number) => `가격만 바꿔 ${d.won(a)}과 ${d.won(b)}을 매대에서 견줘 볼까요?`,
  proposeOne: "이대로 매대에 올려 볼까요?",
}
