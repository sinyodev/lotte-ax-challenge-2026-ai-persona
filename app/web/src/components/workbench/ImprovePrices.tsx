import { Heading } from "@astryxdesign/core/Heading"
import { Text } from "@astryxdesign/core/Text"
import { VStack } from "@astryxdesign/core/VStack"
import type { RunStatus } from "../../chat/contract"
import type { ImprovePricePoint, ImproveSales } from "../../chat/contract-improve"
import { improveCardCopy as t } from "../../copy/improve"

function PriceSales({ sales }: { sales: ImproveSales }) {
  const period = sales.monthly?.map((row) => row.month).sort() ?? []
  const amount = sales.season_total?.amount ?? (period.length === 1 ? sales.monthly?.[0].amount : undefined)
  if (!amount?.every(Number.isFinite) || amount.length !== 3) return null
  return (
    <div className="improve-sales">
      <Text weight="semibold">{t.salesTitle} {period.length ? t.salesScope(period[0], period[period.length - 1]) : t.salesSeason}</Text>
      <Text as="p" hasTabularNumbers>{t.salesAmount(...amount)}</Text>
      <Text as="p">{t.salesRange}</Text>
      {sales.assumptions?.length ? (
        <details>
          <summary><Text>{t.salesAssumptions}</Text></summary>
          <ul>
            {sales.assumptions.map((assumption) => <li key={assumption}><Text>{assumption}</Text></li>)}
          </ul>
        </details>
      ) : null}
    </div>
  )
}

export function ImprovePrices({ points, baseId, basePrice, runStatus }: {
  points: ImprovePricePoint[]
  baseId: string
  basePrice?: number
  runStatus: (id: string) => RunStatus | "missing" | undefined
}) {
  const rows = [...points].sort((a, b) => a.price - b.price)
    .map((point) => ({ ...point, status: point.run_id ? runStatus(point.run_id) : undefined }))
  const waiting = rows.some(({ status, rate }) => rate == null && (!status || status === "running"))
  const periods = rows.map(({ sales }) => sales?.monthly?.map(({ month }) => month).sort().join(","))
  const amounts = rows.map(({ sales }) => sales?.season_total?.amount?.[1])
  const maxSales = periods[0] && periods.every(p => p === periods[0]) && amounts.every(v => typeof v === "number")
    ? Math.max(...amounts as number[]) : undefined
  return (
    <figure className="improve-prices">
      <VStack gap={3}>
        <figcaption>
          <Heading level={4}>{t.priceTitle}</Heading>
          <Text as="p">{t.priceCaption}</Text>
        </figcaption>
        <div className="improve-price-scale" aria-hidden="true">
          <Text color="primary" type="supporting" hasTabularNumbers>{t.percent(0)}</Text>
          <Text color="primary" type="supporting" hasTabularNumbers>{t.percent(100)}</Text>
        </div>
        <ul className="improve-price-rows">
          {rows.map(({ price, rate, n, picked, run_id: id, sales, status }) => {
            const original = (id && id === baseId) || price === basePrice
            const available = rate != null && Number.isFinite(rate) && n > 0
            const unavailable = status === "failed" || status === "stopped" || status === "missing" || !waiting
            return (
              <li key={price} className="improve-price-row">
                <div className="improve-inline">
                  <Text weight="semibold" hasTabularNumbers>{t.price(price)}</Text>
                  {original && <Text>{t.originalPrice}</Text>}
                </div>
                <div className="improve-price-track" aria-hidden="true" data-available={available}>
                  {available && <span style={{ width: `${Math.min(100, Math.max(0, rate))}%` }} />}
                </div>
                <div className="improve-inline">
                  {available ? (
                    <>
                      <Text weight="semibold" hasTabularNumbers>{t.percent(rate)}</Text>
                      <Text hasTabularNumbers>{t.tally(picked, n)}</Text>
                      {status === "running" && <Text>{t.provisional}</Text>}
                    </>
                  ) : (
                    <>
                      <Text>{unavailable ? t.priceMissing : t.pricePending}</Text>
                      {n > 0 && <Text hasTabularNumbers>{t.priceResponded(n)}</Text>}
                    </>
                  )}
                </div>
                {available && sales && <>
                  <PriceSales sales={sales} />
                  {maxSales !== undefined && sales.season_total?.amount?.[1] === maxSales &&
                    <Text weight="semibold">{amounts.filter(v => v === maxSales).length > 1 ? t.salesTie : t.salesHighest}</Text>}
                </>}
              </li>
            )
          })}
        </ul>
      </VStack>
    </figure>
  )
}
