import { Text } from "@astryxdesign/core/Text"
import type { ShelfRunView } from "../../chat/contract-shelf"
import { shelfCopy } from "../../copy/shelf"

export function RunUsageLine({ view }: { view?: ShelfRunView | null }) {
  const usage = view?.usage
  // 도는 동안에는 보이지 않는다(기다리는 화면은 남은 시간을 말한다). 끝난 뒤에만
  if (!usage || view?.status === "running") return null
  const { elapsed, calls, costKrw, costUsd } = shelfCopy.usage
  const cost = usage.est_cost_krw != null ? costKrw(usage.est_cost_krw)
    : usage.est_cost_usd != null ? costUsd(usage.est_cost_usd) : null
  return (
    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
      <Text type="label" hasTabularNumbers>{elapsed(usage.elapsed_s)}</Text>
      <Text type="label" hasTabularNumbers>{calls(usage.calls)}</Text>
      {cost && <Text type="label" hasTabularNumbers>{cost}</Text>}
    </div>
  )
}
