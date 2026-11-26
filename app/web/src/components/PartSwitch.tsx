import { SegmentedControl, SegmentedControlItem } from "@astryxdesign/core/SegmentedControl"
import { copy, PARTS } from "../copy"
import { PART_IDS, type PartId } from "../chat/contract"

/**
 * 첫 화면 위쪽 가운데의 전환: 컨셉 기획 | 매대 테스트.
 * 옅은 회색 알약 판 위에 고른 쪽만 흰 알약. 모양은 테마(themes/lotte/overrides.css의 data-part-switch)에 있다.
 */
export function PartSwitch({ value, onChange }: { value: PartId; onChange: (part: PartId) => void }) {
  return (
    <div data-part-switch>
      <SegmentedControl label={copy.home.partLabel} value={value} onChange={(v) => onChange(v as PartId)} size="lg">
        {PART_IDS.map((p) => (
          <SegmentedControlItem key={p} value={p} label={PARTS[p]} />
        ))}
      </SegmentedControl>
    </div>
  )
}
