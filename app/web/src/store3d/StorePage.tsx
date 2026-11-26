import { useEffect, useState } from "react"
import { useSearchParams } from "react-router"
import StoreView from "./StoreView"

/**
 * 확인용(?try=1): 테스트가 도는 것처럼 손님을 들여보내 걷는 모습과 말풍선을 본다. 숫자와 말은 견본이고 서버를 부르지 않는다.
 * 앱의 메뉴에서는 이 주소로 가지 않는다.
 */
const TRY_THOUGHTS = {
  picked: ["밥이랑 같이 마실 거니까 달지 않고 깔끔한 녹차가 좋겠네요."],
  passed: ["처음 보는 거라 선뜻 손이 안 가네요. 늘 마시던 걸로 할래요.", "녹차는 쌉쌀해서, 그 돈이면 탄산 마실래요."],
}
const TRY_CONCEPT = { name: "식사엔 녹차 무가당", container: "페트", volume: 500, price: 1800 }
const TRY_TOTAL = 300

/** /store: 앱의 틀 안에서 본문을 가득 채우는 입체 매장. 테스트가 없으니 손님 한두 명이 구경한다. */
export default function StorePage() {
  const [params] = useSearchParams()
  const isTry = params.get("try") === "1"
  const [asked, setAsked] = useState(0)
  useEffect(() => {
    if (!isTry || asked >= TRY_TOTAL) return
    const t = window.setTimeout(() => setAsked(asked + 1), 900)
    return () => window.clearTimeout(t)
  }, [isTry, asked])
  return (
    <div className="h-full min-h-0 w-full">
      {isTry ? (
        <StoreView
          concept={TRY_CONCEPT}
          flow={{ asked, picked: Math.floor(asked / 8), total: TRY_TOTAL, running: asked < TRY_TOTAL }}
          thoughts={TRY_THOUGHTS}
        />
      ) : (
        <StoreView />
      )}
    </div>
  )
}
