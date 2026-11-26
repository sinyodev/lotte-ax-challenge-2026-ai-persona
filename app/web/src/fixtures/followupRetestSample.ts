// 견본: 후속 개선의 다시 테스트 결과(11-25). 실제 테스트의 답이 아니다. /proto/followup?sample=retest 견본 페이지만 쓴다.
import type { FollowupPayload, FollowupPeople, FollowupPerson } from "../chat/contract-followup"

const person = (i: number, before: boolean, after: boolean, who = "", lines: string[] = [], said = ""): FollowupPerson =>
  ({ id: `S${i}`, who, lines, before, after, said })

const lost = [
  person(1, true, false, "24세 여자, 사무직", ["낼 수 있는 가격 1,500원"], "1,800원이면 늘 마시던 걸 살래요."),
  person(2, true, false, "27세 남자, 대학원생", ["낼 수 있는 가격 1,600원", "단맛이 강할까 걱정"], "달 것 같아서 이번엔 넘어갈게요."),
  person(3, true, false, "22세 여자, 대학생", ["낼 수 있는 가격 1,500원"], "값이 조금만 낮으면 골랐을 거예요."),
  person(4, true, false, "29세 남자, 영업직", ["낼 수 있는 가격 1,400원"], "이 값이면 익숙한 탄산을 고를래요."),
]
const gain = [
  person(5, false, true, "21세 여자, 대학생", ["수박화채의 추억이 떠오름"], "어릴 때 먹던 화채가 생각나서 골랐어요."),
  person(6, false, true, "25세 남자, 개발자", ["맛이 궁금함"], "새로운 맛이라 한번 마셔 보고 싶어요."),
]
const stay = Array.from({ length: 8 }, (_, i) => person(10 + i, true, true))
const rest = Array.from({ length: 286 }, (_, i) => person(100 + i, false, false))

export const followupRetestPeople: FollowupPeople = {
  status: "done", total: 300, asked: 300,
  before: { n: 300, picked: 12 }, after: { n: 300, picked: 10 },
  people: [...lost, ...gain, ...stay, ...rest],
}

export const followupRetestPayload = (base: Partial<FollowupPayload> = {}): FollowupPayload => ({
  upload_id: "sample", step: "retest", concept: { id: "b", name: "밀키스 화채", price: 1800 }, target: "20대",
  n: { raw: 304, clean: 276, target: 134 }, removed: [], diffs: [], note: "", curve: [], best_price: null,
  opinions: { good: [], bad: [] }, track: { total: 300, original: 12, retest: 10, improved: null },
  base_run: "sample", retest_run: "sample", can_retest: true, ...base,
})
