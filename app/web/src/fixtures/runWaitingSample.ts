// 견본: 도는 테스트의 기다리는 화면(11-25). 실제 테스트의 답이 아니다. /design 견본 페이지만 쓴다.
import type { ShelfRunView } from "../chat/contract-shelf"
import type { WorkCard } from "../chat/workbenchStore"
import { exploreSampleRun } from "./exploreSample"
import { sampleRunView } from "./chatSamples"

const guests = [
  { visit: "V9", age: "50대", sex: "여자", occasion: null, chose: "견본 제품 가", said: "늘 마시던 걸로 골랐어요.", ours: false },
  { visit: "V8", age: "20대", sex: "남자", occasion: null, chose: "녹차 견본", said: "새로 나와서 한번 마셔 볼래요.", ours: true },
  { visit: "V7", age: "40대", sex: "여자", occasion: null, chose: "사지 않음", said: "오늘은 물 사러 왔어요.", ours: false },
  { visit: "V6", age: "30대", sex: "남자", occasion: null, chose: "견본 제품 나", said: "점심 먹고 개운한 게 당겨서 이걸로 골랐어요. 가격도 괜찮고 양도 넉넉해 보여요.", ours: false },
  { visit: "V5", age: "20대", sex: "여자", occasion: null, chose: "견본 제품 다", said: "", ours: false },
]

export const waitingExploreCard: WorkCard = {
  id: "sample-explore-running", stage: "shelf", kind: "explore", status: "ready",
  title: "전 연령 탐색 테스트", payload: { run_id: "sample-explore-running" },
}

export const waitingExploreRun: ShelfRunView = {
  ...exploreSampleRun, id: "sample-explore-running", status: "running", asked: 148, total: 160,
  waiting: {
    mode: "explore", steps_done: 250, steps_total: 320, visited: 148, complete: 102, eta_s: 190,
    lead: { kind: "group", age: "50대", sex: "여자", picked: 8, n: 18 }, recent: guests,
  },
}

export const waitingExploreEarly: ShelfRunView = {
  ...waitingExploreRun, asked: 4,
  waiting: { mode: "explore", steps_done: 4, steps_total: 320, visited: 4, complete: 0, eta_s: null, lead: null, recent: guests.slice(0, 2) },
}

export const waitingTargetCard: WorkCard = {
  id: "sample-target-running", stage: "shelf", kind: "shelf-run", title: "매대 테스트", status: "ready",
  payload: {
    run_id: "sample-target-running",
    concept: { name: "녹차 견본", pack: "500ml 페트", container: "페트", volume: 500, price: 2200 },
    who: "20대 손님",
  },
}

export const waitingTargetRun: ShelfRunView = {
  ...sampleRunView, id: "sample-target-running", status: "running", asked: 148, total: 300,
  waiting: {
    mode: "target", steps_done: 296, steps_total: 600, visited: 148, complete: 148, eta_s: 45,
    lead: { kind: "target", picked: 31, n: 148, name: "녹차 견본" }, recent: guests,
  },
}
