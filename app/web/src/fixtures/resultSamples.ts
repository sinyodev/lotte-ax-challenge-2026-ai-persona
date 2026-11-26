/**
 * 견본 자료. 견본 페이지(/design)에서 테스트 결과 화면(ResultDashboard)의 모양을 보이려고 지어낸 값이다.
 * 도는 중의 결과(남은 시간 포함)와 요약 구역(brief)이 없는 옛 결과. 숫자, 제품 이름, 가상 소비자의 말은 모두 견본이다.
 */
import type { RunView } from "../chat/contract"
import type { WorkCard } from "../chat/workbenchStore"
import type { ShelfRunView } from "../chat/contract-shelf"
import { sampleRunView } from "./chatSamples"

const base = sampleRunView.result!

export const sampleResultRunning: ShelfRunView = {
  ...sampleRunView,
  id: "run-sample-result-running",
  status: "running",
  asked: 102,
  total: 300,
  result: {
    ...base,
    n: 102,
    picked: 31,
    low: 22.3,
    high: 39.7,
    rank: 1,
    products: 56,
    neighbors: [
      { name: "녹차 견본", picked: 31, ours: true, self: true },
      { name: "견본 제품 가", picked: 12, ours: false, self: false },
      { name: "견본 제품 나", picked: 9, ours: true, self: false },
    ],
    from: {
      rival: [{ name: "견본 제품 가", count: 11 }, { name: "견본 제품 다", count: 4 }],
      own: [{ name: "견본 제품 나", count: 8 }, { name: "견본 제품 라", count: 3 }],
      none: 2,
      pending: 3,
    },
    barriers: [
      { label: "늘 마시는 것이 있음", count: 30 },
      { label: "처음 보는 제품이라 망설여짐", count: 22 },
      { label: "가격이 비쌈", count: 11 },
      { label: "지금 상황에 안 맞음", count: 7 },
    ],
    by_occasion: [
      { occasion: "밖에서 식사할 때 입가심", n: 48, picked: 19 },
      { occasion: "집에서 혼자 낮이나 저녁에", n: 22, picked: 6 },
      { occasion: "밖에서 쉬거나 사람을 만나며", n: 17, picked: 4 },
      { occasion: "일하다가 혼자 한 잔", n: 11, picked: 2 },
      { occasion: "집에서 가족과 간식 자리", n: 4, picked: 0 },
    ],
  },
  brief: {
    headline: "지금까지는 20대 102명 중 31명이 골랐고, 매대 56개 가운데 1위예요",
    range: "범위 22~41명",
    group: "20대",
    points: [],
    top: [
      { name: "녹차 견본", picked: 31, ours: true, self: true },
      { name: "견본 제품 가", picked: 12, ours: false, self: false },
      { name: "견본 제품 나", picked: 9, ours: true, self: false },
      { name: "견본 제품 다", picked: 7, ours: false, self: false },
      { name: "견본 제품 라", picked: 5, ours: true, self: false },
      { name: "아주 긴 이름의 견본 제품 마 500mL 페트 한정판", picked: 4, ours: false, self: false },
    ],
    eta_s: 236,
    actions: [
      { id: "interview-barrier/T012", reason: "가장 많은 까닭은 '늘 마시는 것이 있음'(30명)이에요. 왜인지 물어볼 수 있어요.", label: "더 물어볼 곳",
        do: { say: "더 물어볼 곳", to: "w7-group", ids: ["open", "run-sample-result-running", "barrier:늘 마시는 것이 있음"] } },
      { id: "report", reason: null, label: "결과 보고서 내려받기", do: { say: "결과 보고서 내려받기", to: "result-brief", ids: ["report"] } },
    ],
  },
}

/** 요약 구역(brief)도, 음용 상황별 집계도 없는 옛 결과. */
export const sampleResultOld: RunView = {
  ...sampleRunView,
  id: "run-sample-result-old",
  status: "done",
  asked: 300,
  result: { ...base, n: 300, picked: 5, low: 0.7, high: 3.8, rank: 9, by_occasion: [] },
}

export const sampleResultCard = (runId: string): WorkCard => ({
  id: `result-${runId}`,
  stage: "result",
  kind: "result",
  title: "테스트 결과",
  status: "ready",
  payload: { run_id: runId },
})
