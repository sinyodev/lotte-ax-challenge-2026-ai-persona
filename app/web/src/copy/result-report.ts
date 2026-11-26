const count = new Intl.NumberFormat("ko-KR")
const n = (x: number) => count.format(x)

/** 받침이 있으면 앞의 것, 없으면 뒤의 것("을/를"). */
function josa(word: string, pair: string) {
  const [yes, no] = pair.split("/")
  const code = word.trim().replace(/['’”")\]]+$/, "").slice(-1).charCodeAt(0) - 0xac00
  return code >= 0 && code <= 11171 && code % 28 !== 0 ? yes : no
}

/** 테스트 결과의 새 화면(보고서 한 장)에서 새로 쓰는 글. 나머지는 copy/result-dashboard.ts의 글을 그대로 쓴다. */
export const resultReportCopy = {
  rateOf: (total: number, k: number, lo: number, hi: number) => `${n(total)}명 중 ${n(k)}명, 범위 ${n(lo)}~${n(hi)}명`,
  ownShare: (k: number, pct: number) => `고른 ${n(k)}명 가운데 ${pct}%`,
  // 차트의 범례
  keySelf: "이번 컨셉",
  keyOwn: "자사 제품",
  keyRival: "경쟁사 제품",
  people: (x: number) => `${n(x)}명`,
  share: (x: number, pct: number) => `${n(x)}명 (${pct}%)`,
  average: (pct: number) => `전체 ${pct}%`,
  fromList: "많이 옮겨 온 제품",
  // 막대 표의 칸 머리와 숫자 칸
  colProduct: "제품",
  colPicked: "고른 사람",
  colMoved: "옮겨 온 사람",
  colBarrier: "요인",
  colAnswered: "답한 사람",
  colShare: (total: number) => `${n(total)}명 중`,
  colOccasion: "음용 상황",
  colRate: "선택률",
  total: "전체",
  pct: (x: number) => `${x}%`,
  of: (total: number, k: number) => `${n(total)}명 중 ${n(k)}명`,
  // 견본 페이지(/proto/result)의 대화
  proto: {
    stage: "테스트 결과",
    planner: "결과 보기",
    placeholder: "칠성이에게 말하기",
    loading: "테스트 결과를 불러오고 있어요.",
    missing: "이 테스트의 결과를 찾지 못했어요. 주소 끝에 ?run=실행 id를 붙여 주세요.",
    done: (group: string, total: number, k: number, pct: number, name: string, products: number, rank: number | null) =>
      `테스트가 끝났어요. ${group} ${n(total)}명 중 ${n(k)}명(${pct}%)이 ${name}${josa(name, "을/를")} 골랐고` +
      (rank ? `, 매대 ${products}개 가운데 ${rank}위예요.` : " 순위에는 들지 못했어요."),
    learned: (count: number) => `이번 테스트로 알게 된 것은 ${["", "한", "두", "세"][count] ?? count} 가지예요.`,
    own: (k: number, own: number) => `고른 ${n(k)}명 중 ${n(own)}명은 자사 제품을 고르던 가상 소비자예요.`,
    barrier: (passed: number, c: number, label: string) => `고르지 않은 ${n(passed)}명 중 ${n(c)}명은 '${label}'${josa(label, "을/를")} 들었어요.`,
    // 관찰한 것과 아직 모르는 것을 가른다: 까닭은 테스트가 말해 주지 않는다
    unknown: (own: boolean, barrier: boolean) =>
      `${[own ? "왜 옮겨 왔는지" : "", barrier ? "왜 망설였는지" : ""].filter(Boolean).join(", ")}는 아직 몰라요. 개선안 테스트에서 가상 소비자에게 물어보고 고칠 점을 찾아볼까요?`,
    next: "개선안 테스트로 넘어가 볼까요?",
    btnImprove: "개선안 테스트로 이동",
    btnReport: "결과 보고서 내려받기",
  },
}
