/**
 * W7 UX 시안(/proto/w7) 장면 B~E의 견본 자료. 장면 A는 서버의 진단을 읽는다.
 * 시연용 인원, 발언, 범위는 견본으로 만든 값이다.
 */

export type Source = "provided" | "demo"

/* ───────── 장면 B. 테스트 결과 (시연용 응답) ───────── */

/** 과제 컨셉의 사양. 개선안 시연 카드에서 사용한다. */
export const concept = {
  name: "밀키스 화채",
  flavor: "수박화채 맛",
  form: "탄산",
  pack: "500mL PET",
  price: 1800,
  sale: "여름 한정",
}

export const panel = { total: 120, target: "20대" }

export const shelfResult = {
  picked: 39,
  rank: 3,
  shelfSize: 56,
  /** 고른 39명이 컨셉이 없는 매대에서 고르던 것 */
  fromOwn: 11,
  fromRival: 24,
  fromNone: 4,
  /** 가격을 고친 견본의 응답 수 */
  fixPicked: 42,
}

export type QuestionId = "q-fizz" | "q-price" | "q-season" | "q-own"

export const questions: { id: QuestionId; hasScript: boolean }[] = [
  { id: "q-fizz", hasScript: true },
  { id: "q-price", hasScript: false },
  { id: "q-season", hasScript: false },
  { id: "q-own", hasScript: false },
]

export type MethodId = "one" | "fgi" | "fgd"
export const methods: { id: MethodId; isReady: boolean }[] = [
  { id: "one", isReady: false },
  { id: "fgi", isReady: true },
  { id: "fgd", isReady: true },
]

/* ───────── 장면 C, D. 소비자 인터뷰 (시연용 응답) ───────── */

export type PersonId = "p1" | "p2" | "p3" | "p4" | "p5" | "p6"

export type Person = {
  id: PersonId
  age: number
  gender: "여성" | "남성"
  job: string
  /** 매대에서 밀키스 화채를 골랐나 */
  picked: boolean
  /** 컨셉이 없는 매대에서 평소 고르던 제품 */
  usual: string
  usualIsOwn: boolean
}

export const people: Person[] = [
  { id: "p1", age: 24, gender: "여성", job: "대학생", picked: true, usual: "밀키스", usualIsOwn: true },
  { id: "p2", age: 27, gender: "남성", job: "회사원", picked: true, usual: "코카콜라 제로", usualIsOwn: false },
  { id: "p3", age: 22, gender: "여성", job: "대학생", picked: true, usual: "웰치스 포도", usualIsOwn: false },
  { id: "p4", age: 29, gender: "여성", job: "회사원", picked: false, usual: "칠성사이다", usualIsOwn: true },
  { id: "p5", age: 25, gender: "남성", job: "대학원생", picked: false, usual: "포카리스웨트", usualIsOwn: false },
  { id: "p6", age: 28, gender: "남성", job: "회사원", picked: false, usual: "옥수수수염차", usualIsOwn: false },
]

export type Turn = {
  id: string
  /** FGI는 늘 1. FGD는 1차 각자, 2차 서로, 3차 정리 */
  round: 1 | 2 | 3
  person: PersonId | "host"
  text: string
  /** FGD 2차부터: 누구의 말에 답했나 */
  to?: PersonId
  stance?: "agree" | "rebut"
  /** 이 발언에서 생각이 바뀌었다 */
  changed?: boolean
}

export type Finding = {
  id: string
  group: "agreed" | "split" | "changed"
  text: string
  /** 여섯 명 중 몇 명 */
  count: number
  turnIds: string[]
}

export type Session = { turns: Turn[]; findings: Finding[] }

export const sessions: Record<"fgi" | "fgd", Session> = {
  fgi: {
    turns: [
      { id: "i1", round: 1, person: "p1", text: "여름 한정이라 눈에 띄었어요. 그런데 화채라는 이름이면 탄산이 약하거나 없을 거라고 생각했어요." },
      { id: "i2", round: 1, person: "p2", text: "밀키스니까 탄산이 있어야죠. 화채라는 이름은 크게 신경 쓰지 않았어요." },
      { id: "i3", round: 1, person: "p3", text: "화채라고 하면 떠먹는 시원한 그릇이 먼저 떠올라요. 탄산이라고 하니 조금 헷갈렸어요." },
      { id: "i4", round: 1, person: "p4", text: "화채에 탄산이 들어간다니 어떤 맛일지 그림이 안 그려져서 지나쳤어요." },
      { id: "i5", round: 1, person: "p5", text: "운동하고 마실 걸 찾고 있어서 탄산이라 뺐어요. 탄산이 없었다면 집어 봤을 것 같아요." },
      { id: "i6", round: 1, person: "p6", text: "수박 맛 탄산은 예전에도 본 것 같아서 새롭게 느껴지지 않았어요." },
    ],
    findings: [
      { id: "f-name", group: "agreed", text: "‘화채’라는 이름에서 탄산이 없는 음료를 떠올렸어요", count: 4, turnIds: ["i1", "i3", "i4", "i5"] },
      { id: "f-milkis", group: "split", text: "탄산이 있어야 밀키스답다는 의견도 있어요", count: 1, turnIds: ["i2"] },
      { id: "f-old", group: "split", text: "수박 맛 탄산은 전에도 봤다는 의견이 있어요", count: 1, turnIds: ["i6"] },
    ],
  },
  fgd: {
    turns: [
      { id: "d1", round: 1, person: "p1", text: "밀키스에 수박 그림이 있으면 일단 눈에 띄어요. 여름 한정이라 한 번은 사 볼 것 같아요." },
      { id: "d2", round: 1, person: "p2", text: "탄산이라서 고른 거예요. 화채라는 말은 크게 신경 쓰지 않았어요." },
      { id: "d3", round: 1, person: "p3", text: "이름이 귀여워서 집었는데, 화채면 탄산이 없을 줄 알았어요." },
      { id: "d4", round: 1, person: "p4", text: "화채는 떠먹는 거라, 탄산이 들어간다니 어떤 맛일지 그림이 안 그려져요." },
      { id: "d5", round: 1, person: "p5", text: "운동하고 마실 거라 탄산은 부담돼요. 화채라는 이름은 좋은데요." },
      { id: "d6", round: 1, person: "p6", text: "수박 맛 탄산은 예전에도 본 것 같아서 굳이 싶었어요." },
      { id: "d7", round: 2, person: "p4", to: "p2", stance: "rebut", text: "탄산이 좋아서 고른 거면 그냥 밀키스를 사지 않을까요? 화채라는 이름을 붙인 까닭이 흐려져요." },
      { id: "d8", round: 2, person: "p3", to: "p4", stance: "agree", text: "저도 그 말에 공감해요. 화채라고 하면 시원하고 부드러운 걸 기대하게 돼요." },
      { id: "d9", round: 2, person: "p2", to: "p4", stance: "rebut", text: "그래도 탄산이 빠지면 밀키스라는 이름을 쓸 까닭이 없어 보여요." },
      { id: "d10", round: 2, person: "p1", to: "p3", stance: "agree", changed: true, text: "듣고 보니 화채라는 말에는 탄산이 안 어울리는 것 같아요. 탄산이 없으면 더 자주 살 것 같아요." },
      { id: "d11", round: 2, person: "p5", to: "p4", stance: "agree", text: "탄산이 없다면 운동하고 나서도 마셔 볼 만해요." },
      { id: "d12", round: 3, person: "host", text: "‘화채’와 탄산이 어울리느냐에서 의견이 갈렸어요. 여섯 분 중 네 분이 탄산이 없는 쪽을 더 기대하셨어요." },
      { id: "d13", round: 3, person: "p2", text: "저는 그래도 탄산이 있어야 밀키스 같아요." },
    ],
    findings: [
      { id: "f-name", group: "agreed", text: "‘화채’라는 이름에서 탄산이 없는 음료를 떠올렸어요", count: 4, turnIds: ["d3", "d4", "d8", "d10", "d11"] },
      { id: "f-milkis", group: "split", text: "탄산을 빼면 밀키스다움이 흐려진다는 의견도 있어요", count: 1, turnIds: ["d9", "d13"] },
      { id: "f-old", group: "split", text: "수박 맛 탄산은 전에도 봤다는 의견이 있어요", count: 1, turnIds: ["d6"] },
      { id: "f-changed", group: "changed", text: "2차에서 탄산이 없는 쪽으로 생각을 바꿨어요", count: 1, turnIds: ["d10"] },
    ],
  },
}

/** 장면 B에서 질문을 고르지 않고 건너뛰었을 때 쓰는 값 */
export const defaults = { question: "q-fizz" as QuestionId, method: "fgd" as const }

/* ───────── 장면 E. 개선안 테스트 (시연용 응답) ───────── */

export const variant = { id: "no-fizz", change: { field: "form", from: "탄산", to: "무탄산" } }

export const compare = {
  total: 120,
  original: { picked: 39, range: [31, 47] as const },
  changed: { picked: 49, range: [40, 58] as const },
  both: 34,
  gained: 15,
  lost: 5,
  neither: 66,
  net: { value: 10, range: [4, 16] as const },
  verdict: "better" as "better" | "unclear" | "worse",
  /** 지나친 81명 중 같은 이유를 댄 사람(장면 B의 근거 숫자와 같다) */
  reasonCount: 29,
  reasonOf: 81,
  /** 새로 고른 15명 */
  gainedWho: {
    groups: [
      { label: "20대 초반 여성", count: 6 },
      { label: "20대 후반 여성", count: 4 },
      { label: "20대 초반 남성", count: 3 },
      { label: "20대 후반 남성", count: 2 },
    ],
    usualOwn: 4,
    usualRival: 11,
  },
  /** 고르다 지나친 5명 */
  lostWho: { usualOwn: 3, usualRival: 2 },
}
