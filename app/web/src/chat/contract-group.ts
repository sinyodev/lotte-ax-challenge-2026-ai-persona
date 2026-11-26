import type { ComparisonPayload, LegacyDiagnosisPayload } from "./contract-diagnose"

export type GroupMode = "fgi" | "fgd"

export type GroupParticipant = {
  id: string
  label: string
  choice: string
  picked: boolean
}

export type GroupTurn = {
  id: string
  person: string
  round: number
  text: string
  replyTo?: string
  topic?: "form" | "price" | "flavor"
}

export type GroupSession = {
  question: string
  turns: GroupTurn[]
  summary: { title: string; text: string; turnIds: string[] }[]
}

export type GroupPayload = {
  demo: true
  concept: string
  participants: GroupParticipant[]
  modes: Record<GroupMode, GroupSession>
  diagnosis: LegacyDiagnosisPayload
  comparison: ComparisonPayload
}

export type LiveGroupParticipant = {
  id: string
  who: string
  picked: boolean
  choice: string
  reason: string
  usual?: string
}

export type LiveGroupQuestion = {
  id: string
  text: string
  basis: string
}

export type LiveGroupTurn = {
  id: string
  person: string
  round: number
  text: string
  reply_to?: string | null
  stance?: "agree" | "disagree" | null
  changed?: boolean
}

export type LiveGroupFinding = {
  text: string
  turn_ids: string[]
  count: number
}

export type LiveGroupSession = {
  id: string
  mode: GroupMode
  question_id: string
  question: string
  participants: LiveGroupParticipant[]
  rounds: number
  status: "running" | "done" | "error"
  turns: LiveGroupTurn[]
  findings: { agreed: LiveGroupFinding[]; split: LiveGroupFinding[]; changed: LiveGroupFinding[]; independent?: LiveGroupFinding[] }
  calls: number
}

export type LiveGroupPayload = {
  demo: false
  view: "setup" | "room" | "conclusion" | "individual"
  individual?: { question: string; qa: [string, string][] }
  run_id: string
  concept: string
  questions: LiveGroupQuestion[]
  candidates: LiveGroupParticipant[]
  suggested: string[]
  selected_question_id?: string
  session?: LiveGroupSession
}
