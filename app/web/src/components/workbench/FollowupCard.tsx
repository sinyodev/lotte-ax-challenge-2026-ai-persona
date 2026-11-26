import { ProgressBar } from "@astryxdesign/core/ProgressBar"
import { Text } from "@astryxdesign/core/Text"
import { useFollowupPeople, type FollowupPayload, type FollowupPeople } from "../../chat/contract-followup"
import { followupReportCopy as t } from "../../copy/followup-report"
import { FollowupFit, FollowupIdeas, FollowupReport, FollowupRetest } from "./FollowupReport"

/** 다시 테스트가 도는 동안: 진행을 알리는 한 줄과 진행 막대. */
function Running({ people }: { people: FollowupPeople | null }) {
  const asked = people?.asked ?? 0
  const total = people?.total ?? 0
  const label = t.retest.running(asked, total)
  return (
    <div className="flex flex-col gap-2">
      <Text as="p" display="block">{label}</Text>
      <ProgressBar label={label} isLabelHidden value={asked} max={Math.max(1, total)} variant="neutral" />
    </div>
  )
}

/** 후속 개선(약속 v1.20): 조사 확인(보고서 한 장) → 다시 테스트 결과. 다음 행동은 칠성이의 말과 대화의 버튼이 맡는다. */
export function FollowupCard({ payload, samplePeople }: { payload: FollowupPayload; samplePeople?: FollowupPeople | null }) {
  const hasRetest = Boolean(payload.retest_run)
  const people = useFollowupPeople(payload.upload_id, hasRetest, samplePeople)
  const done = people?.status === "done" ? people : null
  if (!hasRetest && payload.step === "ideas") return <FollowupIdeas payload={payload} />
  if (!hasRetest && payload.step !== "diff" && payload.fit) return <FollowupFit payload={payload} />
  if (payload.step === "diff" || payload.step === "applied" || !hasRetest) return <FollowupReport payload={payload} />
  if (done) return <FollowupRetest payload={payload} people={done} />
  if (payload.step === "ideas") return <FollowupReport payload={payload} />
  return <Running people={people} />
}
