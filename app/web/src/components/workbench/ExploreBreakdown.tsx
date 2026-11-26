import { type CSSProperties, useId, useState } from "react"
import { Button } from "@astryxdesign/core/Button"
import { Heading } from "@astryxdesign/core/Heading"
import { Icon } from "@astryxdesign/core/Icon"
import { InfoTip } from "@astryxdesign/core/InfoTip"
import { ProgressBar } from "@astryxdesign/core/ProgressBar"
import { SegmentedControl, SegmentedControlItem } from "@astryxdesign/core/SegmentedControl"
import { Table, TableBody, TableCell, TableHeader, TableHeaderCell, TableRow } from "@astryxdesign/core/Table"
import { Text } from "@astryxdesign/core/Text"
import { ChartBarIcon, ChevronDownIcon, ChevronUpIcon, ScaleIcon, UserGroupIcon } from "@heroicons/react/24/outline"
import type { ExploreAxis, ExploreCell, ExploreResult } from "../../chat/contract-shelf"
import { shelfCopy } from "../../copy/shelf"
import "./explore.css"

const t = shelfCopy.explore
const groupName = (cell: { age: string; sex: string }) => `${t.ageRange(cell.age)} ${t.sexes[cell.sex] ?? cell.sex}`

function topGroups(cells: ExploreCell[]) {
  // The displayed rates are rounded. Compare the observed counts to preserve true ties.
  const peak = Math.max(0, ...cells.filter(c => c.n > 0).map(c => c.picked / c.n))
  return peak > 0 ? cells.filter(c => c.n > 0 && c.picked / c.n === peak) : []
}

const share = (g: { picked: number; n: number }) => g.n ? g.picked / g.n : -1

function ends(axis: ExploreAxis) {
  const ordered = [...axis.groups].sort((a, b) => share(b) - share(a))
  return { top: ordered[0], hi: ordered[0].label, lo: ordered[ordered.length - 1].label }
}

function AxisBars({ axis, max }: { axis: ExploreAxis; max: number }) {
  const top = axis.clear ? ends(axis).top : null
  return (
    <div className="explore-axis">
      <div className="flex items-center justify-between gap-2">
        <Text type="supporting" color="primary" weight="semibold">{t.axisTitles[axis.axis]}</Text>
        <Text type="label">{axis.clear ? t.axisVerdict.clear : t.axisVerdict.none}</Text>
      </div>
      {axis.groups.map(g => (
        <div key={g.key} className="explore-axis-row">
          <Text weight={g === top ? "bold" : "medium"}>{g.label}</Text>
          <RateBar rate={g.rate ?? 0} max={max} overall={null} highlight={g === top} />
          <div className="explore-axis-value">
            <Text type="large" weight={g === top ? "bold" : "semibold"} hasTabularNumbers>{g.rate == null ? t.noAnswers : t.percent(g.rate)}</Text>
            <Text type="label" hasTabularNumbers>{t.axisCount(g.picked, g.n)}</Text>
          </div>
        </div>
      ))}
    </div>
  )
}

function AxesSummary({ axes }: { axes: NonNullable<ExploreResult["axes"]> }) {
  const all = axes.sex.groups.reduce((acc, g) => ({ n: acc.n + g.n, picked: acc.picked + g.picked }), { n: 0, picked: 0 })
  const overall = all.n ? Math.round(1000 * all.picked / all.n) / 10 : 0
  const headline = t.axesHeadline(axes.sex.clear ? ends(axes.sex) : null, axes.age.clear ? ends(axes.age) : null, overall)
  const highest = Math.max(0, ...[...axes.sex.groups, ...axes.age.groups].map(g => g.rate ?? 0))
  const max = Math.max(25, 25 * Math.ceil(highest / 25))
  return (
    <section className="explore-summary">
      <div className="explore-decision explore-axes-headline">
        <Icon icon={ScaleIcon} size="md" />
        <Text display="block" type="large" weight="semibold">{headline}</Text>
      </div>
      <div className="explore-axes">
        <AxisBars axis={axes.sex} max={max} />
        <AxisBars axis={axes.age} max={max} />
      </div>
    </section>
  )
}

function Summary({ result, leaders }: { result: ExploreResult; leaders: ExploreCell[] }) {
  const axes = result.axes
  if (axes && axes.sex.clear != null && axes.age.clear != null) return <AxesSummary axes={axes} />
  const first = leaders[0]
  const only = leaders.length === 1 ? first : null
  const missing = result.cells.some(c => !c.n)
  const weighted = result.weighting === "population"
  if (result.cells.every(c => !c.n)) return <Text>{t.noResult}</Text>
  const reason = missing ? t.missingReason : result.suggested ? t.clear : !first ? t.zeroReason
    : only ? t.overlap : t.tiedReason

  return (
    <section className="explore-summary">
      <div className="explore-metrics">
        <div className="explore-metric">
          <div className="flex items-center gap-2">
            <Icon icon={UserGroupIcon} size="sm" />
            <Text type="supporting" color="primary" weight="semibold">{missing ? t.observedGroup : t.topGroup}</Text>
          </div>
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            {first?.rate != null && <Text type="display-1" weight="bold" hasTabularNumbers className="explore-peak">{t.percent(first.rate)}</Text>}
            <Text type="large" weight="semibold" className="explore-leader">{only ? groupName(only) : first ? t.tied(leaders.length) : t.nonePicked}</Text>
          </div>
          {only && (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
              {only.n <= 50 && (
                <div aria-hidden="true" className="explore-people" style={{ gridTemplateColumns: `repeat(${Math.min(only.n, 10)}, auto)` }}>
                  {Array.from({ length: only.n }, (_, i) => <i key={i} data-picked={i < only.picked || undefined} />)}
                </div>
              )}
              <Text type="supporting" color="primary" hasTabularNumbers>{t.occurrenceCount(only.picked, only.n)}</Text>
            </div>
          )}
        </div>
        <div className="explore-metric">
          <div className="flex items-center gap-2">
            <Icon icon={ChartBarIcon} size="sm" />
            <Text type="supporting" color="primary" weight="semibold">{t.overall}</Text>
            <InfoTip label={t.overallHelp} content={weighted ? t.populationHelp : t.equalHelp} />
          </div>
          <Text type="display-3" weight="medium" className="explore-mean" hasTabularNumbers>
            {result.overall_rate == null ? t.noAnswers : t.percent(result.overall_rate)}
          </Text>
          {missing && <Text type="label">{t.partial}</Text>}
        </div>
      </div>
      <div className="explore-decision">
        <Icon icon={ScaleIcon} size="md" />
        <div>
          <Text display="block" type="large" weight="semibold">{result.suggested ? t.confirmTarget(groupName(result.suggested)) : t.keepTarget}</Text>
          <Text>{reason}</Text>
        </div>
      </div>
    </section>
  )
}

function RateBar({ rate, max, overall, highlight }: { rate: number; max: number; overall: number | null; highlight?: boolean }) {
  return (
    <div className="explore-bar" aria-hidden="true">
      <span className="explore-fill" data-highlight={highlight || undefined} style={{ width: `${100 * rate / max}%` }} />
      {overall != null && <i className="explore-reference" style={{ left: `${100 * overall / max}%` }} />}
    </div>
  )
}

function AverageGuide({ overall, max }: { overall: number; max: number }) {
  return (
    <div aria-hidden="true" className="explore-average-guide" style={{ "--average-position": `${100 * overall / max}%` } as CSSProperties}>
      <Text type="supporting" color="primary" weight="medium" hasTabularNumbers>{t.reference(overall)}</Text>
      <i className="explore-reference" />
    </div>
  )
}

function GroupChart({ cells, leader, max, overall, progress, details }: {
  cells: ExploreCell[]; leader?: ExploreCell; max: number; overall: number | null; progress: boolean; details: boolean
}) {
  const ages = [...new Set(cells.map(c => c.age))]
  const sexes = [...new Set(cells.map(c => c.sex))]
  return (
    <Table aria-label={t.byGroup} aria-description={!progress && overall != null ? t.reference(overall) : undefined}
      density="compact" verticalAlign="middle" className="explore-matrix w-full table-fixed text-left">
      <TableHeader>
        <TableRow>
          <TableHeaderCell scope="col" className="explore-age">{t.age}</TableHeaderCell>
          {sexes.map((sex, index) => (
            <TableHeaderCell key={sex} scope="col">
              {t.sexes[sex] ?? sex}
              {index === 0 && !progress && overall != null && <AverageGuide overall={overall} max={max} />}
            </TableHeaderCell>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {ages.map(age => (
          <TableRow key={age}>
            <TableHeaderCell scope="row"><Text weight="medium">{t.ageRange(age)}</Text></TableHeaderCell>
            {sexes.map(sex => {
              const c = cells.find(cell => cell.age === age && cell.sex === sex)
              const highlight = !!c && c === leader
              return (
                <TableCell key={sex}>
                  {progress && c ? (
                    <div className="flex flex-col gap-1 py-1">
                      <Text type="label" hasTabularNumbers>{t.cellCountLabel(c.n, c.total)}</Text>
                      <ProgressBar label={groupName(c)} isLabelHidden value={c.n} max={Math.max(1, c.total)} variant="neutral" />
                      {c.rate != null && <Text type="label" hasTabularNumbers>{t.liveRate(c.rate)}</Text>}
                    </div>
                  ) : c?.rate == null ? <Text>{t.noAnswers}</Text> : (
                    <>
                      <div className="explore-value">
                        <RateBar rate={c.rate} max={max} overall={overall} highlight={highlight} />
                        <Text type="large" weight={highlight ? "bold" : "semibold"} hasTabularNumbers>{t.percent(c.rate)}</Text>
                      </div>
                      {details && (
                        <div className="explore-detail flex flex-col gap-1">
                          <Text type="label">{t.occurrenceCount(c.picked, c.n)}</Text>
                          {c.low != null && c.high != null && <Text type="label">{t.intervalLabel} {t.interval(c.low, c.high)}</Text>}
                        </div>
                      )}
                    </>
                  )}
                </TableCell>
              )
            })}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function Occasions({ rows, max, overall }: { rows: ExploreResult["occasions"]; max: number; overall: number | null }) {
  if (!rows.length) return <Text>{t.noResult}</Text>
  const ranked = [...rows].sort((a, b) => (b.n ? b.picked / b.n : -1) - (a.n ? a.picked / a.n : -1))
  const [top, next] = ranked
  const leader = top.picked > 0 && (!next?.n || top.picked * next.n > next.picked * top.n) ? top : null
  return (
    <Table aria-label={t.byOccasion} aria-description={overall != null ? t.reference(overall) : undefined}
      density="compact" verticalAlign="middle" className="explore-occasions w-full table-fixed text-left">
      <TableHeader>
        <TableRow>
          <TableHeaderCell scope="col" className="explore-occasion-name">{t.occasionTab}</TableHeaderCell>
          <TableHeaderCell scope="col" className="explore-rate-heading">
            {overall == null ? t.selectionRate : (
              <div className="explore-value explore-rate-axis">
                <AverageGuide overall={overall} max={max} />
                <span>{t.selectionRate}</span>
              </div>
            )}
          </TableHeaderCell>
          <TableHeaderCell scope="col" className="explore-count">{t.pickedPeople}</TableHeaderCell>
          <TableHeaderCell scope="col" className="explore-count">{t.respondents}</TableHeaderCell>
        </TableRow>
      </TableHeader>
      <TableBody>
        {ranked.map(row => (
          <TableRow key={row.occasion}>
            <TableHeaderCell scope="row"><Text weight={row === leader ? "bold" : "medium"}>{row.occasion}</Text></TableHeaderCell>
            <TableCell>
              {row.rate == null ? <Text>{t.noAnswers}</Text> : (
                <div className="explore-value">
                  <RateBar rate={row.rate} max={max} overall={overall} highlight={row === leader} />
                  <Text type="large" weight={row === leader ? "bold" : "semibold"} hasTabularNumbers>{t.percent(row.rate)}</Text>
                </div>
              )}
            </TableCell>
            <TableCell className="explore-count"><Text type="supporting" color="primary" hasTabularNumbers>{t.people(row.picked)}</Text></TableCell>
            <TableCell className="explore-count"><Text type="supporting" color="primary" hasTabularNumbers>{t.people(row.n)}</Text></TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

export function ExploreBreakdown({ result, done, running, requested }: {
  result: ExploreResult; done: boolean; running: boolean; requested?: number
}) {
  const [panel, setPanel] = useState("group")
  const [details, setDetails] = useState(false)
  const regionId = useId()
  const leaders = topGroups(result.cells)
  const group = !done || panel === "group"
  const rows = group ? result.cells : result.occasions
  const overall = result.overall_rate
  const highest = Math.max(overall ?? 0, ...rows.map(row => row.rate ?? 0))
  const max = Math.max(25, 25 * Math.ceil(highest / 25))
  // 축으로 판정한 요약이 있으면 여덟 칸 표에서 한 칸만 강조하지 않는다(결론은 칸 하나의 1등이 아니다).
  const byAxes = result.axes?.sex.clear != null && result.axes?.age.clear != null

  return (
    <>
      {done && <Summary result={result} leaders={leaders} />}
      <section className="explore-chart">
        {/* 도는 동안에는 접는 단추("연령·성별로 보기")가 이 표의 이름이다 */}
        {!running && <div className="flex flex-wrap items-center justify-between gap-3">
          <Heading level={4} className="explore-chart-title">{t.comparison}</Heading>
          {done && <SegmentedControl label={t.comparison} value={panel} onChange={setPanel} size="md">
            <SegmentedControlItem value="group" label={t.groupTab} />
            <SegmentedControlItem value="occasion" label={t.occasionTab} />
          </SegmentedControl>}
        </div>}
        {running && requested != null && result.cells.length > 0 && <Text type="label">{t.goal(requested / result.cells.length)}</Text>}
        <div id={regionId} className="explore-table-frame">
          {group ? <GroupChart cells={result.cells} leader={done && !byAxes && leaders.length === 1 ? leaders[0] : undefined}
            max={max} overall={overall} progress={running} details={details} /> :
            <Occasions rows={result.occasions} max={max} overall={overall} />}
        </div>
        {group && !running && result.cells.some(c => c.n) && (
          <div className="flex flex-wrap items-center gap-2">
            <Button label={t.details} variant="ghost" size="sm" aria-expanded={details} aria-controls={regionId}
              onClick={() => setDetails(!details)} endContent={<Icon icon={details ? ChevronUpIcon : ChevronDownIcon} size="sm" />} />
            {details && <>
              <InfoTip label={t.intervalHelp} content={t.intervalNote} />
              {requested != null && <Text type="label">{t.goal(requested / result.cells.length)}</Text>}
            </>}
          </div>
        )}
      </section>
    </>
  )
}
