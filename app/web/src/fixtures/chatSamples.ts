/**
 * 견본 자료. 견본 페이지(/design)에서 대화 부품과 작업대 카드의 모양을 보이려고 넣은 예시 값이다.
 * 실제 화면은 서버가 보낸 값만 그린다. 숫자는 모두 견본이다.
 */
import type {
  ActionsData,
  ActivityData,
  BriefPayload,
  ChoicesData,
  ConceptItem,
  ConceptsPayload,
  ConfirmData,
  EvidenceItem,
  IdeaItem,
  RunView,
  SpecRow,
  SummaryData,
} from "../chat/contract"
import type { WorkCard } from "../chat/workbenchStore"

export const sampleSay = "편의점 음료 매대부터 봤어요. 제로 탄산이 9개인데 500ml 페트는 하나뿐이에요. 누구를 먼저 볼까요?"
export const samplePlanner = "제로 탄산 신제품 하나 검토해 보고 싶어"

// 08: 하는 일은 짧은 이름이다(서버가 "요즘 소식 찾는 중"처럼 보낸다)
export const sampleActivityRunning: ActivityData = { label: "요즘 소식 찾는 중", status: "running" }
export const sampleActivityDone: ActivityData = { label: "요즘 소식 찾는 중", status: "done" }

export const sampleChoices: ChoicesData = {
  kind: "single",
  options: [
    { id: "a", label: "20대 직장인", note: "당을 신경 쓰는 사람 82%" },
    { id: "b", label: "30~40대 직장인", note: "오후에 가장 많이 마셔요" },
    { id: "c", label: "칠성이가 골라 줘" },
  ],
}
export const sampleChoicesMulti: ChoicesData = {
  kind: "multi",
  options: [
    { id: "price", label: "가격", note: "1,600~2,000원" },
    { id: "volume", label: "용량", note: "355ml, 500ml" },
    { id: "promo", label: "행사", note: "1+1, 2+1" },
  ],
}

export const sampleActions: ActionsData = {
  actions: [
    { id: "go", label: "컨셉으로 만들기", primary: true },
    { id: "more", label: "아이디어 더 받기" },
    { id: "mine", label: "내 아이디어 추가하기" },
  ],
}

// 04: 설명이 붙은 버튼 묶음(둘이면 버튼 아래에 설명, 셋이면 세로로 쌓는다)
export const sampleActionsNotedTwo: ActionsData = {
  actions: [
    { id: "to-shelf", label: "매대 테스트로 넘어가기", note: "두 컨셉을 가상 매대에 올려요", primary: true },
    { id: "download", label: "컨셉 보드 내려받기", note: "한 장으로 저장해요" },
  ],
}
export const sampleActionsNotedThree: ActionsData = {
  actions: [
    { id: "confirm", label: "컨셉 확정하기", note: "이 두 컨셉으로 정해요", primary: true },
    { id: "price", label: "가격 바꾸기", note: "컨셉의 가격을 다시 정해요" },
    { id: "more", label: "컨셉 더 만들기", note: "남은 아이디어도 컨셉으로 만들어요" },
  ],
}

// 04: 설명(desc)과 줄의 덧말(note)이 붙은 확인 카드
export const sampleConfirmNoted: ConfirmData = {
  title: "매대 테스트",
  desc: "두 컨셉을 하나씩 매대에 올려서 봐요",
  rows: [
    { label: "컨셉", value: "2개", note: "라임 제로 캔, 라임 제로 페트" },
    { label: "가상 소비자", value: "컨셉마다 300명" },
    { label: "걸리는 시간", value: "8분쯤", note: "끝나면 알려 드려요" },
  ],
  confirm: { id: "start", label: "테스트 시작하기" },
  cancel: { id: "change", label: "조건 바꾸기" },
}

// 08: 이름이 긴 버튼(한 줄을 지키고 넘치면 줄을 바꾼다)
export const sampleActionsLong: ActionsData = {
  actions: [
    { id: "confirm", label: "이 두 컨셉으로 확정하고 매대에 올려 보기", primary: true },
    { id: "price", label: "가격을 매대의 다른 제로 탄산과 맞춰 바꾸기" },
    { id: "more", label: "남은 아이디어로 컨셉 더 만들기" },
  ],
}

export const sampleConfirm: ConfirmData = {
  title: "매대 테스트",
  rows: [
    { label: "컨셉", value: "3개" },
    { label: "가상 소비자", value: "컨셉마다 300명" },
    { label: "걸리는 시간", value: "12분쯤" },
  ],
  confirm: { id: "start", label: "테스트 시작하기" },
  cancel: { id: "change", label: "조건 바꾸기" },
}

export const sampleSummary: SummaryData = { title: "컨셉 B 선택", value: "300명 중 54명", note: "세 컨셉 중 가장 많아요" }

const card = (id: string, rest: Omit<WorkCard, "id">): WorkCard => ({ id, ...rest })

// 10: 브리프는 대화에서 나온 것의 요약이다. 서버는 다섯 칸을 모두 보내지만 정해진 칸(set)만 보인다.
const briefFields = (setKeys: string[]): BriefPayload["fields"] => {
  const all = [
    { key: "product", label: "제품", value: "제로 탄산" },
    { key: "channel", label: "채널", value: "편의점 음료 매대", note: "칠성이가 정했어요" },
    { key: "target", label: "타깃", value: "20대 직장인" },
    { key: "occasion", label: "음용 상황", value: "아침 출근길, 혼자" },
    { key: "need", label: "핵심 니즈", value: "당 걱정 없이 잠 깨기" },
  ] as const
  return all.map((f) => {
    const isSet = setKeys.includes(f.key)
    return { ...f, value: isSet ? f.value : null, state: isSet ? "set" : "empty" }
  })
}

const brief = (id: string, payload: BriefPayload): WorkCard =>
  card(id, { stage: "idea", kind: "brief", title: "기획 브리프", status: "ready", payload })

export const sampleBriefs: WorkCard[] = [
  brief("brief-one", { fields: briefFields(["product"]) }),
  brief("brief-many", {
    fields: briefFields(["product", "channel", "target", "occasion"]),
    thoughts: ["아침용", "유자", "한 손에 드는 크기"],
  }),
]
/** 아무것도 정해지지 않은 브리프. 작업대에 카드가 그려지지 않는다. */
export const sampleBriefEmpty = brief("brief-empty", { fields: briefFields([]) })

const features = ["당 0", "카페인 없음", "탄산"]

export const sampleIdeas = card("ideas", {
  stage: "idea",
  kind: "ideas",
  title: "아이디어",
  status: "ready",
  payload: {
    basis: "오후에 일하다가 마시는 20대 직장인은 \"당 걱정 없이 기분 전환\"을 가장 바라요",
    items: [
      { id: "a", name: "제로 라임 스파클링 캔", flavor: "라임", pack: "캔 355ml", features, line: "한 손에 들고 한 번에 마셔요", diff: "셋 중 가장 작아요" },
      { id: "b", name: "제로 라임 스파클링 페트", flavor: "라임", pack: "페트 500ml", features, line: "책상에 두고 오후 내내 나눠 마셔요", diff: "A와 용기와 용량만 달라요" },
      { id: "c", name: "제로 자몽 스파클링 페트", flavor: "자몽", pack: "페트 500ml", features, line: "쌉쌀해서 단맛 없이 개운해요", diff: "B와 맛만 달라요" },
    ],
  },
})

// 12: 컨셉 보드(약속 v1.4). 경쟁 제품의 이름과 가격은 매대 자료(data/ours/shelf_products.csv)의 것이고, 나머지 값은 견본이다.
const specOf = (rows: [string, string, string][]): SpecRow[] => rows.map(([key, label, value]) => ({ key, label, value }))
const conceptA: ConceptItem = {
  id: "a",
  name: "라임 제로 캔",
  headline: "오후 세 시, 당 없이 한 캔",
  benefit: "한 번에 마시고 자리로 돌아가요",
  points: ["당 0g", "라임 향", "강한 탄산"],
  price: "1,500원",
  pack: "355ml 캔",
  spec: specOf([
    ["type", "제품 유형", "제로 탄산"],
    ["flavor", "맛", "라임"],
    ["pack", "용기와 용량", "355ml 캔"],
    ["sugar_caffeine", "당, 카페인", "당 0g, 카페인 없음"],
    ["carbonation", "탄산", "강함"],
    ["target", "타깃", "20대 직장인"],
    ["occasion", "음용 상황", "오후에 일하다가"],
    ["channel", "판매 채널", "편의점 음료 매대(냉장)"],
    ["price", "목표 판매가", "1,500원"],
    ["rivals", "경쟁 제품", "칠성사이다 캔 355ml 2,100원 2+1\n펩시콜라 캔 355ml 2,100원 1+1"],
    ["pod", "차별점", "당 0g에 라임 향"],
  ]),
}
const conceptB: ConceptItem = {
  id: "b",
  name: "라임 제로 페트",
  headline: "책상 위의 기분 전환",
  benefit: "뚜껑을 닫아 두고 오후 내내 마셔요",
  points: ["당 0g", "라임 향", "다시 닫는 뚜껑"],
  price: "2,000원",
  pack: "500ml 페트",
  spec: specOf([
    ["type", "제품 유형", "제로 탄산"],
    ["flavor", "맛", "라임"],
    ["pack", "용기와 용량", "500ml 페트"],
    ["sugar_caffeine", "당, 카페인", "당 0g, 카페인 없음"],
    ["carbonation", "탄산", "보통"],
    ["target", "타깃", "20대 직장인"],
    ["occasion", "음용 상황", "오후에 일하다가 책상에 두고"],
    ["channel", "판매 채널", "편의점 음료 매대(냉장)"],
    ["price", "목표 판매가", "2,000원"],
    ["rivals", "경쟁 제품", "칠성사이다 제로 페트 500ml 2,500원 1+1\n펩시 제로슈거 라임 페트 500ml 2,500원 1+1"],
    ["pod", "차별점", "오후 내내 나눠 마시는 라임 향"],
  ]),
}

export const sampleConcepts: WorkCard = card("concepts", {
  stage: "concept",
  kind: "concepts",
  title: "컨셉 보드",
  status: "ready",
  payload: { items: [conceptA, conceptB] } satisfies ConceptsPayload,
})

// 12: 컨셉 하나(값이 다른 줄이 없어 모두 보통 굵기)
export const sampleConceptOne: WorkCard = { ...sampleConcepts, id: "concepts-one", payload: { items: [conceptA] } }

// 12: 경쟁 제품이 없는 컨셉(매대에 같은 종류가 없다. 경쟁 제품과 차별점의 줄을 내지 않는다)
export const sampleConceptNoRivals: WorkCard = {
  ...sampleConcepts,
  id: "concepts-no-rivals",
  payload: {
    items: [
      {
        id: "c",
        name: "참치마요 주먹밥",
        headline: "출근길 빈속을 채우는 한 개",
        benefit: "한 손으로 들고 먹어요",
        points: ["국산 쌀", "참치마요", "뜯기 쉬운 포장"],
        price: "1,800원",
        pack: "",
        spec: specOf([
          ["type", "제품 유형", "삼각김밥"],
          ["flavor", "맛", "참치마요"],
          ["target", "타깃", "20대 직장인"],
          ["occasion", "음용 상황", "출근길 아침"],
          ["channel", "판매 채널", "편의점 음료 매대(냉장)"],
          ["price", "목표 판매가", "1,800원"],
        ]),
      },
    ],
  } satisfies ConceptsPayload,
}

// 10, 12: 기획자가 "첫 번째 컨셉 용량을 250으로 줄여 줘"라고 한 뒤 다시 온 컨셉 보드(바뀐 줄에 changed)
export const sampleConceptsChanged: WorkCard = {
  ...sampleConcepts,
  id: "concepts-changed",
  payload: {
    items: [
      {
        ...conceptA,
        pack: "250ml 캔",
        price: "1,400원",
        spec: conceptA.spec!.map((r) =>
          r.key === "pack"
            ? { ...r, value: "250ml 캔" }
            : r.key === "price"
              ? { ...r, value: "1,400원" }
              : r.key === "rivals"
                ? { ...r, value: "밀키스 캔 340ml 1,800원\n코카콜라 캔 350ml 2,200원" }
                : r.key === "pod"
                  ? { ...r, value: "더 작은 캔에 당 0g" }
                  : r,
        ),
        changed: ["pack", "price", "rivals", "pod"],
      },
      conceptB,
    ],
  } satisfies ConceptsPayload,
}

// 12: 저장된 옛 대화의 컨셉(v1.3). 있는 칸(이름, 헤드라인, 혜택, 가격)만 그린다
export const sampleConceptOld: WorkCard = {
  ...sampleConcepts,
  id: "concepts-old",
  payload: {
    items: [{ id: "a", name: "라임 제로 캔", headline: "오후 세 시, 당 없이 한 캔", benefit: "한 번에 마시고 자리로 돌아가요", price: "1,500원" }],
  } satisfies ConceptsPayload,
}

// 10: 아이디어 보드. 같은 카드가 차례마다 다시 와서 늘거나 줄거나 고쳐진다.
const ideaYuja: IdeaItem = {
  id: "y",
  name: "유자 제로 스파클링 캔",
  flavor: "유자",
  pack: "캔 250ml",
  features: ["당 0", "비타민C", "탄산"],
  line: "출근길 한 손에 들고 금방 마셔요",
  diff: "가장 작아요",
  by: "planner",
  kept: true,
}
const ideaLime: IdeaItem = {
  id: "l",
  name: "라임 제로 스파클링 페트",
  flavor: "라임",
  pack: "페트 500ml",
  features: ["당 0", "카페인 없음", "탄산"],
  line: "책상에 두고 오전 내내 나눠 마셔요",
  diff: "유자 캔보다 크고 다시 닫을 수 있어요",
  by: "chilseong",
}
const ideaGrapefruit: IdeaItem = {
  id: "g",
  name: "자몽 제로 스파클링 캔",
  flavor: "자몽",
  pack: "캔 355ml",
  features: ["당 0", "카페인 조금", "탄산"],
  line: "쌉쌀해서 아침에 잠이 깨요",
  diff: "카페인이 조금 들어 있어요",
  by: "chilseong",
  changed: ["features", "line"],
}
const ideaBoard = (id: string, items: IdeaItem[]): WorkCard =>
  card(id, {
    stage: "idea",
    kind: "ideas",
    title: "아이디어",
    status: "ready",
    origin: "suggestion",
    payload: { basis: "아침 출근길의 20대 직장인은 \"당 걱정 없이 잠 깨기\"를 바라요", items },
  })
/** 첫 차례: 기획자의 아이디어(남김), 칠성이의 아이디어 둘, 그중 하나는 방금 고쳐짐. */
export const sampleIdeaBoard = ideaBoard("idea-board", [ideaYuja, ideaLime, ideaGrapefruit])
/** 다음 차례: 라임이 빠지고, 자몽의 용기가 고쳐지고, 새 아이디어가 들어와 순서가 바뀐다. */
export const sampleIdeaBoardNext = ideaBoard("idea-board", [
  { ...ideaGrapefruit, pack: "캔 250ml", diff: "유자 캔과 크기가 같아요", changed: ["pack"] },
  { ...ideaYuja, changed: undefined },
  {
    id: "p",
    name: "배 제로 스파클링 캔",
    flavor: "배",
    pack: "캔 250ml",
    features: ["당 0", "탄산 약하게"],
    line: "아침 빈속에도 부드러워요",
    diff: "탄산이 가장 약해요",
    by: "chilseong",
  },
])
/** 고르는 차례(on_card). */
export const sampleIdeaBoardPick = ideaBoard("idea-board-pick", [ideaYuja, ideaLime, { ...ideaGrapefruit, changed: undefined }])

export const sampleOtherCards: WorkCard[] = [
  card("shelf-run", {
    stage: "shelf",
    kind: "shelf-run",
    title: "매대 테스트",
    status: "ready",
    payload: {
      run_id: "run-sample00000",
      concept: { name: "녹차 견본", pack: "500ml 페트", container: "페트", volume: 500, price: 2200 },
      who: "20대 손님",
    },
  }),
  card("result", {
    stage: "result",
    kind: "result",
    title: "테스트 결과",
    status: "ready",
    payload: { run_id: "run-sample00000" },
  }),
  card("report", {
    stage: "report",
    kind: "report",
    title: "결과 보고서",
    status: "ready",
    payload: {
      sections: [
        { title: "타깃과 니즈", body: "20대 직장인, 오후에 일하다가 혼자. 당 걱정 없이 기분 전환" },
        { title: "테스트 결과", body: "500ml 페트 1,800원 안이 300명 중 61명으로 가장 많았어요" },
      ],
    },
  }),
]

export const sampleLoading = card("loading", { stage: "idea", kind: "ideas", title: "아이디어", status: "loading", payload: null })
export const sampleError = card("error", { stage: "idea", kind: "ideas", title: "아이디어", status: "error", payload: null })

// 06, 10: 찾아본 것. 이름표는 출처의 이름이다. 출처의 이름과 숫자는 모양을 보이려고 넣은 견본이다.
export const sampleEvidenceItems: EvidenceItem[] = [
  { id: "e1", origin: "record", text: "20대 직장인은 아침 출근길에 탄산음료를 혼자 마시는 때가 많아요", source: "국민건강영양조사 2024(견본)", date: "2024년", note: "응답한 사람이 적어서 참고만 해 주세요" },
  { id: "e2", origin: "sales", text: "편의점 탄산음료 매출에서 제로 탄산의 몫을 보여 주는 견본 문장이에요", source: "aT 식품산업통계정보 소매 POS(견본)", date: "2025년" },
  { id: "e3", origin: "shelf", text: "편의점 음료 매대의 제로 탄산 9개 중 250ml 캔은 하나도 없어요", source: "편의점 음료 매대", date: "11월 20일" },
  { id: "e4", origin: "web", text: "유자 향 제로 탄산이 새로 나왔다는 글이 있어요", source: "예시 웹 글: 올가을 편의점 음료 신제품을 한꺼번에 정리해 봤어요", url: "https://example.com/", date: "2023년 5월", note: "오래된 글이에요" },
]
// 08: 본문이 긴 것(세 줄에서 자르고 누르면 펼친다)
export const sampleEvidenceLong: EvidenceItem = {
  id: "e-long",
  origin: "record",
  text: "20대 직장인은 아침 일곱 시에서 아홉 시 사이에 출근하면서 혼자 음료를 마시는 때가 많고, 그때 고르는 음료는 탄산과 커피가 비슷하게 나뉘어요. 탄산을 고른 사람 가운데 제로 탄산의 몫은 해마다 늘어 왔고, 같은 끼니에 빵이나 김밥을 함께 먹는 경우가 많아요. 같은 시간대의 30대 직장인은 커피를 고르는 때가 더 많아서, 아침의 탄산은 20대에서 더 두드러져요. 다만 이 묶음은 응답한 사람이 적어서 다른 연령과 견줄 때는 참고만 해 주세요.",
  source: "국민건강영양조사 2024(견본)",
  date: "2024년",
}

export const sampleEvidenceExtra: EvidenceItem = {
  id: "e5",
  origin: "web",
  text: "출근길에 탄산으로 잠을 깨는 직장인이 많다는 글이 있어요",
  source: "예시 웹 글 2",
  url: "https://example.com/",
  date: "2025년 9월",
}
export const sampleEvidence = (items: EvidenceItem[]) =>
  card("evidence", { stage: "idea", kind: "evidence", title: "찾아본 것", status: "ready", payload: { items } })

// 06: 직접 쓰기 칩이 붙은 하나 고르기
export const sampleChoicesFree: ChoicesData = {
  kind: "single",
  options: [
    { id: "afternoon-work", label: "오후에 일하다가", note: "34%" },
    { id: "with-lunch", label: "점심 식사와 함께", note: "21%" },
    { id: "after-workout", label: "운동하고 나서", note: "매대에 맞는 상품이 적어요" },
  ],
  free: { label: "직접 정할게요" },
}

// 06: 카드 안에서 고르기(아이디어 카드의 항목을 고른다)
export const sampleChoicesOnCard: ChoicesData = {
  kind: "multi",
  options: [
    { id: "a", label: "A 제로 라임 스파클링 캔" },
    { id: "b", label: "B 제로 라임 스파클링 페트" },
    { id: "c", label: "C 제로 자몽 스파클링 페트" },
  ],
  on_card: "ideas",
  free: { label: "내 아이디어 쓰기" },
}

export const sampleIdeasSuggested: WorkCard = { ...sampleIdeas, origin: "suggestion" }

// 15: 매대 테스트 카드와 결과 카드의 견본(GET /api/runs/{id}의 모양). 숫자와 이름, 손님의 말은 모두 견본이다.
export const sampleRunView: RunView = {
  id: "run-sample00000",
  status: "running",
  concept: { id: "a", name: "녹차 견본", pack: "500ml 페트", container: "페트", volume: 500, price: 2200, promo: null },
  who: { label: "20대 손님", occasion: "밖에서 식사할 때 입가심", occasion_share: 23.8 },
  asked: 120,
  total: 300,
  skipped: 0,
  started_at: "2026-11-23T00:00:00+00:00",
  updated_at: "2026-11-23T00:04:00+00:00",
  model: "견본",
  result: {
    n: 120,
    picked: 5,
    low: 1.8,
    high: 9.4,
    rank: 9,
    products: 56,
    neighbors: [
      { name: "견본 제품 가", picked: 7, ours: false, self: false },
      { name: "견본 제품 나", picked: 6, ours: true, self: false },
      { name: "녹차 견본", picked: 5, ours: true, self: true },
      { name: "견본 제품 다", picked: 5, ours: false, self: false },
      { name: "견본 제품 라", picked: 4, ours: true, self: false },
    ],
    from: { rival: [{ name: "견본 제품 가", count: 1 }], own: [{ name: "견본 제품 나", count: 3 }], none: 1 },
    views: [
      { label: "이번에 산다", count: 5 },
      { label: "다음에 살 수도 있다", count: 90 },
      { label: "관심 없다", count: 25 },
    ],
    barriers: [
      { label: "늘 마시는 것이 있음", count: 60 },
      { label: "처음 보는 제품이라 망설여짐", count: 41 },
      { label: "지금 상황에 안 맞음", count: 33 },
      { label: "가격이 비쌈", count: 11 },
    ],
    by_occasion: [{ occasion: "밖에서 식사할 때 입가심", n: 60, picked: 4 }],
    quotes: {
      picked: [{ visitor: "T007", who: "24세 여자, 대학생", occasion: "밖에서 식사할 때 입가심", said: "견본 문장이에요.", chose: "녹차 견본" }],
      passed: [{ visitor: "T012", who: "27세 남자, 사무원", occasion: "집에서 혼자 낮이나 저녁에", said: "견본 문장이에요.", chose: "견본 제품 가" }],
    },
  },
}

// 19: 개선안 테스트 카드의 견본. 기존안(끝남), 기존안보다 분명히 많은 안(강조), 도는 안, 안 돌린 안, 차이 없는 옛 모양의 안.
// 숫자와 이름은 모두 견본이다.
function sampleRun(id: string, status: RunView["status"], asked: number, picked: number, low: number, high: number, rank: number | null): RunView {
  const base = sampleRunView.result!
  return {
    ...sampleRunView,
    id,
    status,
    asked,
    result: { ...base, n: asked, picked, low, high, rank, products: 56 },
  }
}

export const sampleImproveRuns: Record<string, RunView> = {
  "run-improve-base": sampleRun("run-improve-base", "done", 300, 20, 4.4, 10.1, 7),
  "run-improve-a": sampleRun("run-improve-a", "done", 300, 45, 11.4, 19.5, 1),
  "run-improve-b": sampleRun("run-improve-b", "running", 37, 3, 2.8, 21.3, 12),
  "run-improve-d": sampleRun("run-improve-d", "done", 300, 17, 3.6, 8.9, 9),
}

export const sampleImprove: WorkCard = card("improve", {
  stage: "improve",
  kind: "improve",
  title: "개선안 테스트",
  status: "ready",
  payload: {
    base_run: "run-improve-base",
    items: [
      { id: "A", kind: "price", before: "2,200원", after: "1,800원", change: "가격 2,200원 → 1,800원",
        reason: "가격이 걸린 손님이 11명이라 400원 낮춰 봐요.", run_id: "run-improve-a" },
      { id: "B", kind: "promo", before: "행사 없음", after: "1+1", change: "행사 없음 → 1+1",
        reason: "처음 보는 제품이라 망설인 손님이 41명이라 1+1 행사를 붙여 봐요.", run_id: "run-improve-b" },
      { id: "C", kind: "name", before: "녹차 견본", after: "녹차 견본 제로", change: "이름 녹차 견본 → 녹차 견본 제로",
        reason: "맛이 끌리지 않은 손님이 9명이라 이름에 제로를 드러내 봐요." },
      // 옛 대화의 항목(kind, before, after가 없음): 화면이 change를 갈라 쓴다
      { id: "D", change: "가격 2,200원 → 2,000원", reason: "말씀하신 안이에요.", run_id: "run-improve-d" },
    ],
  },
})
