// 디자인 견본. 실제 대화는 서버에 저장한 탐색 결과를 사용한다.
import type { ShelfRunView } from "../chat/contract-shelf"
import type { WorkCard } from "../chat/workbenchStore"
import { sampleRunView } from "./chatSamples"

export const exploreSampleCard: WorkCard = {
  id: "sample-explore", stage: "shelf", kind: "explore", status: "ready",
  title: "전 연령 탐색 테스트", payload: { run_id: "sample-explore" },
}

// 연령대별 여성·남성 순서. 각 그룹 20명, 선택 인원과 윌슨 95% 구간.
const groups = [
  [2, 2.8, 30.1], [3, 5.2, 36.0], [3, 5.2, 36.0], [4, 8.1, 41.6],
  [5, 11.2, 46.9], [8, 21.9, 61.3], [2, 2.8, 30.1], [5, 11.2, 46.9],
]
const cells = groups.map(([picked, low, high], i) => {
  const age = ["19-29", "30-39", "40-49", "50-59"][Math.floor(i / 2)]
  const sex = i % 2 === 0 ? "여자" : "남자"
  return { age, sex, label: `${age} ${sex}`, n: 20, total: 20, picked, rate: picked * 5, low, high }
})

export const exploreSampleRun: ShelfRunView = {
  ...sampleRunView, id: "sample-explore", status: "done", result: null, asked: 160, total: 160, requested: 160,
  explore: {
    cells, overall_rate: 20, weighting: "equal", overlap: true, suggested: null,
    occasions: [
      { occasion: "식사할 때 입가심", n: 80, picked: 17, rate: 21.2 },
      { occasion: "쉬는 시간에", n: 80, picked: 15, rate: 18.8 },
    ],
  },
}
