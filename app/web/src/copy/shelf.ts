const count = new Intl.NumberFormat("ko-KR")
const decimal = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 1 })
const won = new Intl.NumberFormat("ko-KR", { maximumSignificantDigits: 4 })
const dollar = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumSignificantDigits: 4 })

const people = (n: number) => `${count.format(n)}명`
/** 탐색 그룹 이름(여성·남성, 19~29세 등) 뒤의 주격 조사 */
const subject = (word: string) => {
  const code = word.charCodeAt(word.length - 1) - 0xac00
  return code >= 0 && code <= 11171 && code % 28 ? `${word}이` : `${word}가`
}
type AxisEnds = { hi: string; lo: string }
const percent = (n: number) => `${decimal.format(n)}%`

function elapsed(seconds: number) {
  if (seconds < 0.1) return "0.1초 미만"
  if (seconds < 60) return `${decimal.format(Math.floor(seconds * 10) / 10)}초`
  const minutes = Math.floor(seconds / 60)
  const remainder = Math.floor(seconds % 60)
  return `${count.format(minutes)}분${remainder ? ` ${remainder}초` : ""}`
}

/** 받침이 있으면 을, 없으면 를(한글이 아닌 끝 글자는 을/를을 그대로). */
function eulReul(word: string) {
  const last = word.trim().at(-1) ?? ""
  const code = last.charCodeAt(0) - 0xac00
  if (code < 0 || code > 11171) return "을(를)"
  return code % 28 ? "을" : "를"
}

export const shelfCopy = {
  // 11-25: 테스트가 도는 동안의 기다리는 화면(임시 문구). 숫자는 서버가 센 값이다
  waiting: {
    status: "테스트 진행 중",
    remaining: (seconds: number) => seconds < 60 ? "곧 끝나요" : `약 ${count.format(Math.round(seconds / 60))}분 남았어요`,
    // 아직 속도를 모를 때의 어림(테스트 종류별)
    guess: { explore: "10분쯤 걸려요", target: "5분쯤 걸려요", improve: "5분쯤 걸려요" } as Record<string, string>,
    progress: "테스트 진행", // 진행 막대의 이름(화면 읽기용)
    visited: (n: number, total: number) => `${people(total)} 중 ${people(n)}이 다녀갔어요`,
    allVisited: (total: number) => `${people(total)}이 모두 다녀갔어요. 원래 매대에서 고르던 제품을 확인하고 있어요.`,
    leadGroup: (group: string, picked: number, n: number) => `지금까지는 ${group}이 가장 많이 골랐어요(${people(n)} 중 ${people(picked)})`,
    leadTarget: (picked: number, n: number, name: string) => `지금까지 ${people(n)} 중 ${people(picked)}이 ${name}${eulReul(name)} 골랐어요`,
    recent: "방금 다녀간 손님",
    guest: (age: string, sex: string) => `${age} ${({ 여자: "여성", 남자: "남성" } as Record<string, string>)[sex] ?? sex}`,
    ours: "이 제품을 고른 손님", // 우리 컨셉을 고른 줄의 표시(화면 읽기용)
    breakdown: "연령·성별로 보기",
    leave: "다른 대화를 보셔도 테스트는 계속돼요. 끝나면 여기에 결과가 떠요.",
    doneTitle: "테스트가 끝났어요",
    designTitle: "기다리는 화면", // 견본 페이지의 절 이름
  },

  usage: {
    elapsed: (seconds: number) => `걸린 시간 ${elapsed(seconds)}`,
    calls: (n: number) => `실제 호출 ${count.format(n)}회`,
    costKrw: (amount: number) => `API 추정 비용 ${won.format(amount)}원`,
    costUsd: (amount: number) => `API 추정 비용 ${dollar.format(amount)}`,
  },
  placement: {
    storage: (storage: string) => `${storage} 진열이 필요해요.`,
    rate: (storage: string, rate: number) => `${storage} 진열은 편의점의 ${percent(rate)}에서 할 수 있어요.`,
  },
  targetBasis: "타깃을 정한 근거",
  fewerAssigned: (total: number, requested: number) => `목표 ${people(requested)} 중 테스트에 참여할 수 있는 손님은 ${people(total)}이에요.`,
  // 멈춘 테스트(11-25). seeSoFar는 서버의 phrases.BTN_STOPPED_RESULT와 같아야 한다
  stopped: {
    stop: "멈추고 결과 보기",
    seeSoFar: "지금까지의 결과 보기",
    resume: "이어서 테스트하기", // 임시
    at: (asked: number, total: number) => `${people(total)} 중 ${people(asked)}에서 멈췄어요`, // 임시
  },
  explore: {
    result: "탐색 결과 보기",
    stop: "멈추고 결과 보기",
    loading: "탐색 결과 불러오는 중",
    status: { running: "테스트 진행 중", done: "테스트 완료", stopped: "중지됨", failed: "테스트 실패" },
    progress: (n: number, total: number) => `${people(total)} 중 ${people(n)} 응답`,
    responded: (n: number) => `${people(n)} 응답`,
    goal: (n: number) => `그룹당 목표 ${people(n)}`,
    topGroup: "선택률이 가장 높은 그룹",
    observedGroup: "응답한 그룹 중 최고",
    tied: (n: number) => `${count.format(n)}개 그룹 공동 최고`,
    nonePicked: "선택한 손님 없음",
    overall: "전체 평균 선택률",
    overallHelp: "평균 선택률 계산 방법",
    populationHelp: "각 연령대의 남녀가 인구에서 차지하는 비율에 맞춰 이 제품의 평균 선택률을 구했어요.",
    equalHelp: "연령·성별 그룹마다 이 제품을 고른 비율을 구하고, 응답이 있는 그룹끼리 평균을 냈어요.",
    partial: "응답이 있는 그룹만 평균에 포함했어요.",
    keepTarget: "기존 타깃 유지 추천",
    confirmTarget: (group: string) => `${group} 타깃 테스트 추천`,
    overlap: "오차를 감안하면 그룹 간 차이가 뚜렷하지 않아요.",
    clear: "오차를 감안해도 이 그룹의 선택률이 가장 높아요.",
    tiedReason: "가장 높은 선택률을 보인 그룹이 여럿이에요.",
    zeroReason: "이번 탐색에서 이 제품을 선택한 손님이 없었어요.",
    missingReason: "응답이 없는 그룹이 있어 전체 그룹을 비교하기 어려워요.",
    axisTitles: { sex: "성별", age: "연령대" } as Record<string, string>,
    axisCount: (picked: number, n: number) => `${people(n)} 중 ${people(picked)}`,
    axisVerdict: { clear: "뚜렷한 차이", none: "차이 없음" },
    axesHeadline: (sex: AxisEnds | null, age: AxisEnds | null, overall: number) => {
      const clear = [sex, age].filter((x): x is AxisEnds => !!x)
      if (!clear.length) return `연령대와 성별 어느 쪽으로도 뚜렷한 차이가 없었어요. 전체로는 ${percent(overall)}가 골랐어요.`
      const heads = clear.map(x => `${subject(x.hi)} ${x.lo}보다`).join(", ")
      const tail = sex && !age ? " 연령대별로는 차이가 없었어요." : age && !sex ? " 성별로는 차이가 없었어요." : ""
      return `${heads} 많이 골랐어요.${tail}`
    },
    comparison: "그룹별 선택률",
    byGroupProgress: "연령·성별 응답 현황",
    liveRate: (rate: number) => `현재 선택률 ${percent(rate)}`,
    groupTab: "연령·성별",
    occasionTab: "음용 상황",
    byGroup: "연령·성별 선택률",
    byOccasion: "음용 상황별 선택률",
    pickedPeople: "선택자",
    respondents: "응답자",
    selectionRate: "선택률",
    people,
    age: "연령",
    ageRange: (age: string) => /^\d+-\d+$/.test(age) ? `${age.replace("-", "~")}세` : age,
    sexes: { 여자: "여성", 남자: "남성" } as Record<string, string>,
    cellCountLabel: (n: number, total: number) => `${people(total)} 중 ${people(n)} 응답`,
    noAnswers: "응답 없음",
    noResult: "비교할 수 있는 응답이 없어요.",
    percent,
    intervalLabel: "95% 구간",
    intervalHelp: "선택률의 95% 구간",
    intervalNote: "윌슨 방식으로 구한 범위예요. 응답 수가 적을수록 범위가 넓어져요.",
    interval: (low: number, high: number) => `${percent(low)}~${percent(high)}`,
    details: "응답 수와 95% 구간",
    reference: (rate: number) => `전체 평균 ${percent(rate)}`,
    occurrenceCount: (picked: number, n: number) => `${people(n)} 중 ${people(picked)} 선택`,
  },
}
