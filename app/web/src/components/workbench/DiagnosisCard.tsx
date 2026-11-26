/**
 * 컨셉 보드 분석(1부의 세 번째 단계, 옛 이름 "테스트 전 진단").
 * 새 payload는 보고서 한 장(AnalysisReport, 견본 /proto/analysis와 같은 화면)으로 그린다.
 * 어떤 가격으로 테스트할지는 화면이 아니라 칠성이의 말과 대화의 버튼이 맡는다(참가자 11-25).
 * 옛 payload(저장된 대화)도 그린다.
 */
import { Heading } from "@astryxdesign/core/Heading"
import { Text } from "@astryxdesign/core/Text"
import type { DiagnosisPayload, LegacyDiagnosisPayload } from "../../chat/contract-diagnose"
import { diagnoseCopy as c } from "../../copy/diagnose"
import { AnalysisReport } from "./AnalysisReport"
import { plain, sectionOf } from "./analysisModel"
import type { CardSay } from "./ShelfCards"
import "./DiagnosisCard.css"

const signals = ["trend", "history", "price", "competition", "distribution"] as const

function LegacyDiagnosis({ payload }: { payload: LegacyDiagnosisPayload }) {
  return (
    <section className="flex min-w-0 flex-col gap-4">
      <dl className="diagnosis-rows m-0">
        {signals.map(signal => (
          <div key={signal} className="py-3">
            <dt><Text weight="semibold">{c[signal]}</Text></dt>
            <dd className="m-0"><Text>{plain(payload[signal] || c.empty)}</Text></dd>
          </div>
        ))}
      </dl>
      <div className="diagnosis-fix flex flex-col gap-1">
        <Heading level={4}>{c.alternative}</Heading>
        <Text as="p">{plain(payload.alternative || c.empty)}</Text>
      </div>
    </section>
  )
}

/** 카드 머리 오른쪽의 규격과 가격("500mL PET 1,800원"). 작업대 카드의 제목은 제품명이다. */
export function AnalysisSpec({ payload }: { payload: DiagnosisPayload | LegacyDiagnosisPayload }) {
  if (!("sections" in payload)) return null
  const price = sectionOf(payload, "price")
  const text = c.spec(price?.spec || "", price?.current)
  return text ? <Text hasTabularNumbers weight="medium">{text}</Text> : null
}

/** say는 받기만 한다(옛 화면의 버튼 자리). 버튼은 대화에 있다. */
export function DiagnosisCard({ payload }: { payload: DiagnosisPayload | LegacyDiagnosisPayload; say?: CardSay }) {
  if (!("sections" in payload)) return <LegacyDiagnosis payload={payload} />
  return <AnalysisReport payload={payload} />
}
