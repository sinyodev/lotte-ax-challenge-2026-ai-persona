import { useCallback, useEffect, useRef, useState, type DragEvent } from "react"
import { useLocation, useNavigate, useParams } from "react-router"
import { Button } from "@astryxdesign/core/Button"
import { EmptyState } from "@astryxdesign/core/EmptyState"
import { Heading } from "@astryxdesign/core/Heading"
import { Spinner } from "@astryxdesign/core/Spinner"
import { Text } from "@astryxdesign/core/Text"
import { Badge } from "@astryxdesign/core/Badge"
import { copy, type ModeValue } from "../copy"
import { PART_STAGES, type PartId } from "../chat/contract"
import { FOLLOWUP_TO, UPLOAD_SURVEY, uploadSurvey } from "../chat/contract-followup"
import { followupCopy } from "../copy/followup"
import "../components/workbench/followup.css"
import { loadChat, useChatTurn, type ChatSnapshot } from "../chat/useChatTurn"
import { useRecentChats } from "../chat/recentChats"
import { useWorkbench } from "../chat/workbenchStore"
import { ChatPanel } from "../components/chat/ChatPanel"
import { StageStepper, stepInPart } from "../components/StageStepper"
import { Workbench } from "../components/workbench/Workbench"

/**
 * 첫 화면에서 넘어올 때의 상태. text는 첫 메시지로 바로 보낸다.
 * existing이면 저장한 대화를 먼저 받고 그 뒤에 보낸다(첫 화면의 확정한 컨셉 카드 → "매대에 올려 보기", 지시서 15).
 */
type EntryState = { text?: string; mode?: ModeValue; existing?: boolean } | null

/** 확정한 뒤의 버튼 묶음에 오는 "제안서로 내려받기"의 id(지시서 14, 약속 v1.5). */
const DOWNLOAD_ID = "download"

const line = { borderColor: "var(--color-border)" } as const

/**
 * 대화 화면 /concept/:id(1부 컨셉 기획). 위에 그 부분의 단계 표시줄, 아래 왼쪽에 대화(폭 440px, 1024px보다 좁은 창에서는 320px), 오른쪽에 작업대.
 * 대화는 useChat(id는 주소의 대화 id), 단계와 작업대는 Zustand(useWorkbench). 메시지의 파트를 처음부터 읽어 작업대를 만든다.
 * 저장한 대화를 열면 서버가 준 메시지를 처음 메시지로 받아 대화와 작업대를 그대로 되살린다(지시서 11).
 */
function ChatScreen({
  id,
  entry,
  initial,
}: {
  id: string
  entry: EntryState
  initial: ChatSnapshot
}) {
  const navigate = useNavigate()
  const location = useLocation()
  // 진행 방식 버튼은 1부에서 뜻이 없어 입력창에서 뺐다(06). 값은 받은 것 그대로 보낸다(약속 4절).
  const [mode] = useState<ModeValue>(entry?.mode ?? copy.mode.defaultValue)
  const { messages, sendMessage, regenerate, stopTurn, status, error } = useChatTurn(id, initial)
  // 견본 대화 표시는 data-session의 sample이 참일 때만 낸다. 진짜 칠성이(source live, sample 거짓)에는 내지 않는다(약속 v1.2).
  const { stage, viewStage, sample: isSample, sync, view, reset } = useWorkbench()
  const hasAnalysis = useWorkbench((s) => s.cards.some((c) => c.stage === "analysis"))
  const refreshRecent = useRecentChats((s) => s.refresh)

  useEffect(() => {
    // 저장한 대화를 처음 펼칠 때(작업대가 비어 있고 흘러오는 중이 아닐 때)는 바뀐 카드로 강조하거나 스크롤하지 않는다
    const isOpening = status !== "streaming" && status !== "submitted" && useWorkbench.getState().cards.length === 0
    sync(messages, isOpening)
  }, [messages, status, sync])

  useEffect(() => reset, [reset])

  // 차례가 시작하고 끝날 때마다 왼쪽의 최근 대화를 다시 받는다(일하는 중, 답을 기다림 표시)
  useEffect(() => {
    void refreshRecent()
  }, [status, refreshRecent])

  const send = useCallback(
    (text: string, reply?: { to: string; ids: string[] }) => {
      sendMessage({ text, metadata: reply ? { reply } : {} }, { body: { mode } })
    },
    [sendMessage, mode],
  )

  // 첫 화면에서 받은 문장을 첫 메시지로 바로 보낸다(한 번만). 보낸 뒤에는 주소의 상태를 지워 새로 고쳐도 다시 보내지 않는다.
  // 한 박자 늦춰 보낸다: 개발 모드(StrictMode)는 효과를 한 번 걷었다 다시 거는데, 그때 useChat이 진행 중인 요청을 멈춘다.
  const sentFirst = useRef(false)
  useEffect(() => {
    const text = entry?.text
    if (sentFirst.current || !text) return
    const t = window.setTimeout(() => {
      sentFirst.current = true
      send(text)
      navigate(location.pathname, { replace: true, state: null })
    }, 0)
    return () => window.clearTimeout(t)
  }, [entry, send, navigate, location.pathname])

  const resend = useCallback(() => {
    regenerate({ body: { mode } })
  }, [regenerate, mode])

  // 단계가 2부(매대 테스트)에 들어서면 2부의 단계 표시줄을 보인다
  const part: PartId = PART_STAGES.test.includes(stage) ? "test" : "concept"
  // 표시줄은 지금 보고 있는 단계의 부분을 따른다: 2부에서도 왼쪽의 전환으로 1부(컨셉 기획)의 카드를 다시 본다
  const shownPart: PartId = PART_STAGES.test.includes(viewStage ?? stage) ? "test" : "concept"
  const activeStep = stepInPart(shownPart, stage)
  const reached: PartId[] = part === "test" ? ["concept", "test"] : ["concept"]
  const switchPart = useCallback(
    (next: PartId) => {
      if (next === shownPart) return
      // 그 부분의 마지막으로 온 단계를 연다: 1부는 컨셉 보드 분석(분석이 없던 옛 대화는 컨셉 보드), 2부는 지금 진행 중인 단계
      const last = next === "concept" && !hasAnalysis ? "concept" : PART_STAGES[next][PART_STAGES[next].length - 1]
      view(next === part ? stage : last)
    },
    [shownPart, part, stage, view, hasAnalysis],
  )

  // 14: 제안서로 내려받기(버튼 id "download")는 말을 보내지 않고 제안서 화면을 새 탭으로 연다
  const openProposal = useCallback(() => {
    window.open(`/proposal/${encodeURIComponent(id)}`, "_blank", "noopener")
  }, [id])

  // 후속 개선(약속 v1.20): 조사 파일을 고르거나 대화창에 끌어다 놓으면 올리고, 올림 번호를 기획자의 말로 보낸다
  const picker = useRef<HTMLInputElement>(null)
  const [upload, setUpload] = useState<{ busy: boolean; error: string | null }>({ busy: false, error: null })
  const [isDragging, setDragging] = useState(false)
  const canUpload = part === "test" && status === "ready" && !upload.busy
  const sendSurvey = useCallback(
    async (file: File | undefined) => {
      if (!file) return
      setUpload({ busy: true, error: null })
      try {
        const uploadId = await uploadSurvey(id, file, { tooBig: followupCopy.tooBig, failed: followupCopy.failed })
        setUpload({ busy: false, error: null })
        send(followupCopy.upload, { to: FOLLOWUP_TO, ids: ["upload", uploadId] })
      } catch (e) {
        setUpload({ busy: false, error: e instanceof Error ? e.message : followupCopy.failed })
      }
    },
    [id, send],
  )
  const hasFile = (e: DragEvent) => Array.from(e.dataTransfer.types).includes("Files")

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-4 border-b px-6 py-3" style={line}>
        <div className="min-w-0 flex-1">
          <StageStepper
            part={shownPart}
            activeStep={activeStep}
            onStepClick={(i) => view(PART_STAGES[shownPart][i])}
            onPartChange={switchPart}
            reached={reached}
          />
        </div>
        {isSample && <Badge label={copy.test.sample} />}
      </div>
      <div data-chat-workspace className="flex min-h-0 flex-1">
        <section
          aria-label={copy.test.chatLabel}
          className="relative flex w-80 shrink-0 flex-col border-r lg:w-110"
          style={line}
          onDragOver={(e) => {
            if (!canUpload || !hasFile(e)) return
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false)
          }}
          onDropCapture={(e) => {
            setDragging(false)
            if (!canUpload || !hasFile(e)) return
            e.preventDefault()
            e.stopPropagation()
            void sendSurvey(e.dataTransfer.files[0])
          }}
        >
          {isDragging && <div className="followup-drop"><Heading level={3}>{followupCopy.dropping}</Heading></div>}
          <input
            ref={picker}
            type="file"
            accept=".xlsx"
            hidden
            onChange={(e) => {
              void sendSurvey(e.target.files?.[0])
              e.target.value = ""
            }}
          />
          <ChatPanel
            messages={messages}
            status={status}
            hasError={Boolean(error)}
            onSend={(text) => send(text)}
            onReply={(to, ids, labels) =>
              ids.length === 1 && ids[0] === DOWNLOAD_ID ? openProposal()
                : ids.length === 1 && ids[0] === UPLOAD_SURVEY ? picker.current?.click()
                : send(labels.join(", "), { to, ids })
            }
            onStop={() => void stopTurn()}
            onResend={resend}
            onRetryStopped={resend}
            onAttach={part === "test" ? () => picker.current?.click() : undefined}
            attachLabel={followupCopy.attach}
          />
          {(upload.busy || upload.error) && (
            <div className="flex items-center gap-2 border-t px-4 py-2" style={line} role="status">
              {upload.busy && <Spinner size="sm" />}
              <Text>{upload.busy ? followupCopy.uploading : upload.error}</Text>
            </div>
          )}
        </section>
        <div className="min-w-0 flex-1" style={{ background: "var(--color-background-muted)" }}>
          <Workbench
            onRetry={resend}
            onSay={(text, reply) => send(text, reply)}
            onDownload={openProposal}
            chatId={id}
            canPick={status === "ready" && !error}
          />
        </div>
      </div>
    </div>
  )
}

/** 없는 대화: "대화를 찾지 못했어요"와 새 대화 버튼. */
function ChatNotFound() {
  return (
    <div className="flex h-full min-h-0 flex-col items-center justify-center px-8">
      <EmptyState
        title={copy.test.notFound}
        headingLevel={1}
        actions={<Button label={copy.nav.newChat} href="/" variant="secondary" />}
      />
    </div>
  )
}

type Loaded = { state: "loading" } | { state: "ready"; snapshot: ChatSnapshot } | { state: "missing" }

/** 저장한 대화를 서버에서 받는다(GET /api/chats/{id}). 첫 화면에서 막 만든 대화면 받지 않고 빈 대화로 시작한다. */
function SavedChat({ id, entry }: { id: string; entry: EntryState }) {
  const [isFresh] = useState(() => Boolean(entry?.text) && !entry?.existing)
  const [loaded, setLoaded] = useState<Loaded>(() =>
    isFresh ? { state: "ready", snapshot: { messages: [] } } : { state: "loading" },
  )

  useEffect(() => {
    if (isFresh) return
    const controller = new AbortController()
    loadChat(id, controller.signal)
      .then((snapshot) => {
        if (!controller.signal.aborted) setLoaded(snapshot ? { state: "ready", snapshot } : { state: "missing" })
      })
      .catch(() => {
        if (!controller.signal.aborted) setLoaded({ state: "missing" })
      })
    return () => controller.abort()
  }, [id, isFresh])

  if (loaded.state === "loading") return null
  if (loaded.state === "missing") return <ChatNotFound />
  const openingEntry = !loaded.snapshot.working && (isFresh || entry?.existing) ? entry : null
  return <ChatScreen id={id} entry={openingEntry} initial={loaded.snapshot} />
}

/** 1부 컨셉 기획: /concept/:id. 대화마다 화면을 새로 띄운다. */
export function ConceptPage() {
  const { id } = useParams()
  const location = useLocation()
  if (!id) return <ChatNotFound />
  return <SavedChat key={id} id={id} entry={location.state as EntryState} />
}

/**
 * 2부 매대 테스트: /test/:id는 매대 테스트까지 간 대화(1부와 같은 대화 화면, 단계 표시줄만 2부).
 * /test/new는 준비 중 안내(직접 적은 컨셉은 아직 받지 않는다).
 */
export function TestPage() {
  const { id } = useParams()
  const location = useLocation()
  if (id) return <SavedChat key={id} id={id} entry={location.state as EntryState} />
  return (
    <div className="flex h-full min-h-0 flex-col items-center justify-center px-8">
      <EmptyState
        title={copy.pages.testPart.title}
        headingLevel={1}
        actions={<Button label={copy.pages.testPart.toConcept} href="/" variant="secondary" />}
      />
    </div>
  )
}
