/**
 * 견본 자료. 실제 기록이 생기기 전까지 첫 화면의 매대 테스트 쪽에 보여 주는 "확정한 컨셉" 견본이다(대본 2판의 첫 화면).
 * 카드 한 장 = 한 대화에서 확정한 컨셉 묶음. 가격은 견본이다.
 */
export type Container = "can" | "pet" | "bottle"

export type ConfirmedConcept = {
  id: string
  /** 묶음의 이름(대화의 제목) */
  name: string
  /** container가 null이면(팩, 컵 등) 아이콘 자리를 비워 둔다 */
  /** name은 확정한 컨셉의 이름(지시서 17의 D: 대화 제목만으로는 카드가 구별되지 않는다) */
  concepts: { id: string; name: string; container: Container | null; pack: string; price: string }[]
}

export const confirmedConcepts: ConfirmedConcept[] = [
  {
    id: "lime-zero",
    name: "라임 제로",
    concepts: [
      { id: "a", name: "라임 제로 스파클링", container: "can", pack: "캔 355ml", price: "1,500원" },
      { id: "b", name: "라임 민트 제로", container: "pet", pack: "페트 500ml", price: "2,000원" },
    ],
  },
  {
    id: "low-sugar-ade",
    name: "저당 과일 에이드",
    concepts: [{ id: "a", name: "저당 자몽 에이드", container: "pet", pack: "페트 350ml", price: "1,800원" }],
  },
]
