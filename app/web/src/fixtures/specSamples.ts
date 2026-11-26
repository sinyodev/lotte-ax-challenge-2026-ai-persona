/**
 * 견본: 제품 사양 묶음(지시서 33). 값은 과제 설명의 컨셉 표(docs/background/05-task-and-data.md)와 같다.
 * 규격 둘(밀키스 화채), 규격 하나(레쓰비 프리즈), 용기와 용량만 있는 것(칠성이가 낸 아이디어).
 */
import type { ProductSpec } from "../chat/contract"

export const specSamples: { name: string; spec: ProductSpec; pack?: string }[] = [
  {
    name: "밀키스 화채",
    spec: {
      variants: [
        { label: "슬림캔 250ml", volume_ml: 250, price: 1200, factory_price: 780, shelf_life_months: 12, kcal: 130 },
        { label: "PET 500ml", volume_ml: 500, price: 1800, factory_price: 1200, shelf_life_months: 9, kcal: 260 },
      ],
      shelf_variant: 0,
      launch: "2027-05",
      season: "5~9월 한정",
      channels: ["편의점", "대형마트·SSM", "온라인"],
      storage: "상온",
    },
  },
  {
    name: "레쓰비 프리즈",
    spec: {
      variants: [
        { label: "스파우트 파우치 170ml", volume_ml: 170, price: 1800, factory_price: 1250, shelf_life_months: 12, kcal: 100 },
      ],
      launch: "2027-05",
      channels: ["편의점(냉동)", "대형마트·SSM"],
      storage: "냉동",
    },
  },
  { name: "밀키스 화채 한 그릇 캔", spec: {}, pack: "캔 250ml" },
]
