import type { ComparisonKind } from "../chat/contract-diagnose"
import type { ImproveKind } from "../chat/contract-improve"
import { copy } from "../copy"

const number = (value: number) => value.toLocaleString("ko-KR")
const decimal = (value: number) => value.toFixed(1)
const won = (value: number) => `${number(value)}원`
/** 어림 금액: 10억 이상은 억, 1억 이상은 소수 한 자리 억, 그 아래는 만 원 */
const rough = (value: number) => {
  const abs = Math.abs(value)
  if (abs >= 1e9) return `${number(Math.round(value / 1e8))}억`
  if (abs >= 1e8) return `${(value / 1e8).toFixed(1)}억`
  return abs >= 1e4 ? `${number(Math.round(value / 1e4))}만` : number(Math.round(value))
}
const people = (n: number) => `${number(n)}명`
const tally = (picked: number, n: number) => `${people(n)} 중 ${people(picked)}`
const percent = (value: number) => `${decimal(value)}%`
const rateInterval = ([low, high]: [number, number]) => `95% 구간 ${decimal(low)}~${decimal(high)}%`
const delta = (value: number) => `${value > 0 ? "+" : ""}${decimal(value)}%p`
const deltaInterval = ([low, high]: [number, number]) => `95% 구간 ${decimal(low)}~${decimal(high)}%p`
const topics: Record<ComparisonKind, { label: string; hypothesis: string; evidence: string }> = {
  form: {
    label: "제형",
    hypothesis: "탄산을 빼면 식사에 곁들일 손님은 더 고르고, 청량감을 찾는 손님은 지나칠까요?",
    evidence: "화채처럼 가볍게 마실 음료를 찾는 손님의 선택이 달라지는지 살펴봐요.",
  },
  flavor: {
    label: "맛",
    hypothesis: "수박 향을 줄이면 익숙한 맛을 찾는 손님도 고를까요? 여름 한정 맛을 기대한 손님의 선택도 함께 봐요.",
    evidence: "수박화채 맛을 유지하면서 수박 향만 줄였을 때 선택이 달라지는지 살펴봐요.",
  },
  price: {
    label: "가격",
    hypothesis: "가격을 한 단계 낮추면 가격 때문에 망설였던 손님이 고를까요?",
    evidence: "현재 가격의 아래와 위를 함께 비교해 손님이 어느 가격에서 선택을 바꾸는지 살펴봐요.",
  },
}

export const improveCopy = {
  useQuote: (round: number, person: string) => `${round}차 참석자 ${person.replace(/^p/, "")}의 발언으로 개선안을 만들어 주세요.`,
  title: "개선안 비교",
  source: "데모용 가상 소비자의 선택을 집계했어요.",
  topics,
  comparisonOptions: "비교할 조건",
  quoteLabel: (person: string) => `${/^p\d+$/i.test(person) ? `참석자 ${person.slice(1)}` : person} 발언 · 데모 대본`,
  hypothesis: "확인할 가설",
  original: "원래 안",
  variant: "바꾼 안",
  change: "바꿀 조건",
  run: "같은 손님에게 비교하기",
  hide: "비교 결과 접기",
  back: "인터뷰로 돌아가기",
  result: "같은 손님의 선택 변화",
  resultReady: "비교 결과가 나왔어요.",
  conditions: (volume: number, price?: number) =>
    `${number(volume)}mL 페트 기준${price === undefined ? "" : ` · ${won(price)}`}`,
  headcount: (n: number) => `같은 가상 소비자 ${number(n)}명의 선택을 짝지어 봤어요.`,
  people,
  tally,
  percent,
  rateInterval,
  delta,
  deltaInterval,
  changeLabel: "선택률 차이",
  lost: "골랐다가 지나쳤어요",
  gained: "지나쳤다가 골랐어요",
  intervalLabel: "95% 구간은 어떻게 계산했나요?",
  intervalInfo: "각 안의 선택률은 윌슨 방식으로 범위를 구했어요. 선택률 차이는 같은 손님의 두 선택을 한 쌍으로 묶어 다시 뽑아 범위를 구했어요. 차이의 구간에 0이 들어가면 증가나 감소 방향이 뚜렷하지 않아요. 이 구간은 데모용 응답의 흔들림을 보여줘요.",
  priceTitle: "가격 세 점에서의 선택률",
  pricePosition: ["낮춘 가격", "원래 가격", "높인 가격"],
  joinedPriceStep: (step: number, medianGap: number, rivals: number, prices: number) =>
    `결합 매대 집계 · 타사 탄산 단품 ${number(rivals)}종에서 서로 다른 가격 ${number(prices)}개를 찾았어요. 이웃한 가격 간격의 중앙값 ${won(medianGap)}을 100원 단위로 맞춰 ${won(step)}씩 바꿨어요.`,
  demoPriceStep: (step: number) => `견본 가격 · 결합 매대에서 쓸 수 있는 가격 간격이 없어 데모 기준 ${won(step)}을 적용했어요.`,
  values: {
    form: { before: "탄산", after: "무탄산" },
    flavor: { before: "수박화채 맛", after: "수박 향을 줄인 화채 맛" },
  },
  won,
}

const legacy = copy.workbench.improve

// 개선안 카드. 기존 대화의 동작 문구는 서버의 명령과 맞춰 그대로 쓴다.
export const improveCardCopy = {
  ...legacy,
  kindNames: {
    ...legacy.kindNames, flavor: "맛 변경안", form: "제형 변경안", container: "용기 변경안", appeal: "소구점 변경안", volume: "용량 변경안",
  } satisfies Record<ImproveKind, string>,
  changePrefixes: {
    ...legacy.changePrefixes, flavor: "맛 ", form: "제형 ", container: "용기 ", appeal: "소구점 ", volume: "용량 ",
  } satisfies Record<ImproveKind, string>,
  select: "비교할 후보",
  condition: "비교 항목",
  picked: "고른 손님",
  tableTitle: "개선안 비교",
  switchCandidate: "후보 바꾸기",
  candidate: (kind: string, value: string) => `${kind} · ${value}`,
  focusSay: (label: string) => `‘${label}’ 안을 비교해 주세요.`,
  edit: "값 바꾸기",
  applyEdit: "이 값으로 비교",
  cancelEdit: "취소",
  editSay: (values: string) => `${values} 안을 비교해 주세요.`,
  fields: { price: "가격(원)", volume: "용량(mL)", container: "용기", name: "제품명", promo: "행사", flavor: "맛", form: "제형", appeal: "소구점" } as Record<string, string>,
  evidenceDetails: "이 안을 제안한 근거",
  adopted: "채택한 안",
  adopt: "이 안 채택하기",
  adoptSay: (name: string) => `${name}을 채택해 주세요.`,
  hypothesis: "확인할 가설",
  evidence: "근거",
  change: "바꿀 조건",
  changeOne: "바꿀 조건 하나",
  changeValues: (before: string, after: string) => `${before} → ${after}`,
  quote: "가상 소비자 발언",
  quoteRef: (session?: string, quote?: string) => [session && `인터뷰 ${session}`, quote && `발언 ${quote}`].filter(Boolean).join(" / "),
  origins: {
    record: "소비자 기록",
    shelf: "매대 테스트",
    sales: "판매 자료",
    web: "웹에서 찾은 것",
    suggestion: "칠성이의 제안",
    internal: "내부 자료",
    interview: "가상 소비자 인터뷰",
    group: "가상 소비자 집단 인터뷰",
  } as Record<string, string>,
  noItems: "아직 비교할 변경안이 없어요.",
  retryTest: "다시 테스트하기",
  waiting: "테스트 결과를 불러오고 있어요.",
  failed: "테스트가 실패했어요.",
  stopped: "테스트를 멈췄어요.",
  stopAndSee: "멈추고 지금까지의 결과 보기",
  runMissing: "저장된 테스트를 찾지 못했어요.",
  runUnavailable: "테스트 결과를 불러오지 못했어요. 다시 확인하고 있어요.",
  noResult: "집계할 응답이 없어요.",
  awaitingPairs: "두 안에 모두 응답한 손님의 선택을 집계하고 있어요.",
  noPairs: "두 안에 모두 응답한 손님이 없어 각 매대의 결과만 보여드려요.",
  progress: (asked: number, total: number) => `${number(total)}명 중 ${number(asked)}명 응답`,
  target: (who: string) => `테스트 대상 ${who}`,
  baseSpec: (pack: string, price: number) => `${pack} / ${won(price)}`,
  people,
  tally,
  percent,
  rateInterval,
  delta,
  deltaInterval,
  pairedTitle: "같은 손님의 선택 변화",
  pairedDenominator: (n: number) => `두 안에 모두 응답한 가상 소비자 ${number(n)}명 기준이에요.`,
  provisional: "지금까지 응답한 손님의 선택",
  segments: { both: "둘 다 고름", gained: "바꾼 안만 고름", lost: "원래 안만 고름", neither: "둘 다 지나침" },
  original: "원래 안",
  changed: "바꾼 안",
  rateTitle: "선택률",
  deltaTitle: "선택률 차이",
  watch: "지켜볼 점",
  verdict: {
    more: "바꾼 안을 더 많이 골랐어요",
    less: "원래 안을 더 많이 골랐어요",
    unclear: "두 안의 선택 차이가 뚜렷하지 않아요",
  },
  turnover: (gained: number, lost: number) => gained || lost
    ? `${number(gained)}명이 새로 골랐고, 원래 고르던 ${number(lost)}명은 지나쳤어요.`
    : "두 매대에서 이 제품을 고른 손님은 같았어요.",
  gainedTitle: (n: number) => `새로 고른 ${number(n)}명`,
  lostTitle: (n: number) => `고르다 지나친 ${number(n)}명`,
  noGroups: "이 손님들의 집단별 기록이 없어요.",
  independentTitle: "각 매대에서 제품을 고른 손님",
  responses: "매대 응답 현황",
  waitChanged: "바꾼 안을 손님에게 보여주고 있어요",
  waitOriginal: "원래 안의 응답을 모으고 있어요",
  baselinePicked: (picked: number, n: number) => `원래 제품은 ${people(n)} 중 ${people(picked)}이 골랐어요 (${percent(100 * picked / n)}).`,
  separateBasis: "각 매대에 응답한 손님을 기준으로 집계했어요.",
  intervalMeaning: "차이의 범위에 0이 들어가면 어느 쪽을 더 많이 고른다고 말하기 어려워요.",
  pairDetails: "선택이 어떻게 바뀌었나요?",
  priceTitle: "가격 세 점의 선택률",
  priceCaption: "세 가격 모두에 응답한 가상 소비자 중 각 가격에서 컨셉을 고른 비율이에요.",
  originalPrice: "원래 가격",
  pricePending: "결과 대기",
  priceMissing: "결과 없음",
  priceResponded: (n: number) => `${people(n)} 응답`,
  salesTitle: "가상 매출",
  salesHighest: "가격 세 점 중 가상 매출의 중앙 추정값이 가장 높아요.",
  salesTie: "가상 매출의 중앙 추정값이 공동 1위예요.",
  salesSeason: "출시 시즌 합계",
  salesScope: (first: string, last: string) => first === last ? first : `${first}~${last}`,
  salesAmount: (low: number, mid: number, high: number) => `약 ${rough(mid)} 원 (${rough(low)}~${rough(high)} 원)`,
  salesRange: "선택률의 오차만 넣은 범위예요.",
  planWithValue: (name: string, value: string) => `${name} (${value})`,
  salesAssumptions: "매출 산정 가정",
}
