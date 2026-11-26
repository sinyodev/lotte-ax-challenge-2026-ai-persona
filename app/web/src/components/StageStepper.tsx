import { SegmentedControl, SegmentedControlItem } from "@astryxdesign/core/SegmentedControl"
import { Step, Stepper } from "@astryxdesign/core/Stepper"
import { Text } from "@astryxdesign/core/Text"
import { copy, PARTS, STAGES } from "../copy"
import { PART_IDS, PART_STAGES, STAGE_IDS, type PartId } from "../chat/contract"

/**
 * 단계 표시줄. 그 부분(1부 컨셉 기획, 2부 매대 테스트)의 단계만 보인다. 왼쪽에 부분의 이름표.
 * activeStep은 그 부분 안의 순서다. 단계 수와 같으면 모두 끝난 상태다.
 * onStepClick을 주면 단계를 눌러 그 단계의 카드를 볼 수 있다(아직 안 온 단계도 막지 않는다).
 * onPartChange를 주면 왼쪽의 이름표가 두 부분을 오가는 전환이 된다. reached에 없는 부분은 아직 누를 수 없다.
 */
export function StageStepper({
  part,
  activeStep,
  onStepClick,
  onPartChange,
  reached = PART_IDS,
}: {
  part: PartId
  activeStep: number
  onStepClick?: (index: number) => void
  onPartChange?: (part: PartId) => void
  reached?: readonly PartId[]
}) {
  const stages = PART_STAGES[part]
  return (
    <div className="flex min-w-0 items-center gap-4">
      {onPartChange ? (
        <div className="shrink-0" data-part-switch>
          <SegmentedControl label={copy.home.partLabel} value={part} onChange={(v) => onPartChange(v as PartId)} size="sm">
            {PART_IDS.map((p) => (
              <SegmentedControlItem key={p} value={p} label={PARTS[p]} isDisabled={!reached.includes(p)} />
            ))}
          </SegmentedControl>
        </div>
      ) : (
        <div className="shrink-0">
          <Text type="supporting" weight="medium">
            {PARTS[part]}
          </Text>
        </div>
      )}
      <div className="min-w-0 flex-1">
        <Stepper activeStep={activeStep} label={copy.test.stepperLabel} density="compact" onStepClick={onStepClick}>
          {stages.map((id, i) => (
            <Step key={id} step={i} label={STAGES[STAGE_IDS.indexOf(id)]} />
          ))}
        </Stepper>
      </div>
    </div>
  )
}

/** 진행 중인 단계가 그 부분 안에서 몇 번째인지. 그 부분을 지났으면 단계 수(모두 끝남), 오기 전이면 0. */
export function stepInPart(part: PartId, stage: (typeof STAGE_IDS)[number]) {
  const stages = PART_STAGES[part]
  const i = stages.indexOf(stage)
  if (i >= 0) return i
  return STAGE_IDS.indexOf(stage) > STAGE_IDS.indexOf(stages[stages.length - 1]) ? stages.length : 0
}
