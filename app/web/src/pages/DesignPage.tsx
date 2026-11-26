import type { ReactNode } from "react"
import { Button } from "@astryxdesign/core/Button"
import { Card } from "@astryxdesign/core/Card"
import { Heading } from "@astryxdesign/core/Heading"
import { HStack } from "@astryxdesign/core/HStack"
import { SideNav, SideNavItem, SideNavSection } from "@astryxdesign/core/SideNav"
import { Text } from "@astryxdesign/core/Text"
import { VStack } from "@astryxdesign/core/VStack"
import { useState } from "react"
import { copy, type ModeValue } from "../copy"
import { recentChatSamples as recentChats } from "../fixtures/recentChatSamples"
import { confirmedConcepts } from "../fixtures/confirmedConcepts"
import { exploreSampleCard, exploreSampleRun } from "../fixtures/exploreSample"
import { waitingExploreCard, waitingExploreEarly, waitingExploreRun, waitingTargetCard, waitingTargetRun } from "../fixtures/runWaitingSample"
import { shelfCopy } from "../copy/shelf"
import { ConfirmedConceptCards } from "../components/ConfirmedConceptCards"
import { NoticeLine } from "../components/NoticeLine"
import { PartSwitch } from "../components/PartSwitch"
import { ChilseongAvatar } from "../components/ChilseongAvatar"
import { Composer } from "../components/Composer"
import { ModeMenu } from "../components/ModeMenu"
import { mainNavItems } from "../components/navItems"
import { MainNavLinks } from "../components/MainNavLinks"
import { OwnerRow } from "../components/AppFrame"
import { Icon } from "@astryxdesign/core/Icon"
import { PlannerBubble } from "../components/PlannerBubble"
import { PreparingState } from "../components/PreparingState"
import { NewTestButton } from "../components/NewTestButton"
import { RecentTestItem } from "../components/RecentTestItem"
import { RecentChatList } from "../components/RecentChatList"
import { StageStepper } from "../components/StageStepper"
import { SuggestionChips } from "../components/SuggestionChips"
import { Greeting } from "../components/Greeting"
import { ChatMessageList } from "@astryxdesign/core/Chat"
import {
  ActionButtons,
  ActivityLine,
  ChilseongTurn,
  ChoiceChips,
  ConfirmCard,
  DisconnectedNotice,
  OnCardPrompt,
  RetryStoppedButton,
  SayText,
  StoppedLine,
  SummaryCard,
  TurnBlock,
} from "../components/chat/ChatParts"
import { WorkbenchCard } from "../components/workbench/WorkbenchCard"
import * as sample from "../fixtures/chatSamples"
import { sampleResultCard, sampleResultOld, sampleResultRunning } from "../fixtures/resultSamples"
import { dashCopy } from "../copy/result-dashboard"
import * as diagnosis from "../fixtures/diagnosisSamples"
import { specSamples } from "../fixtures/specSamples"
import { SpecSheet } from "../components/workbench/SpecSheet"
import { specCopy } from "../copy/spec"
import { conceptImageCopy } from "../copy/concept-image"
import { ConceptImage, ConceptImageView, type ConceptImageState } from "../components/concept/ConceptImage"
import { CONTAINER_ICONS } from "../components/ContainerIcon"
import { conceptImageSample } from "../fixtures/conceptImageSample"

const d = copy.design

/** 테마 토큰 이름만 쓴다. 값은 테마에 있다. */
const SWATCHES = [
  { name: d.colorNames.accent, token: "--color-accent" },
  { name: d.colorNames.text, token: "--color-text-primary" },
  { name: d.colorNames.secondary, token: "--color-text-secondary" },
  { name: d.colorNames.border, token: "--color-border" },
  { name: d.colorNames.surface, token: "--color-background-surface" },
  { name: d.colorNames.wash, token: "--color-background-muted" },
  { name: d.colorNames.neutral, token: "--color-neutral" },
] as const

const TEXT_TYPES = ["display-1", "display-2", "display-3", "large", "body", "label", "supporting"] as const
const HEADING_LEVELS = [1, 2, 3, 4] as const

const noop = () => {}
/** 견본 페이지의 카드 버튼: 누를 수 있게 보이되 아무 데도 보내지 않는다. */
const designSay = { onSay: noop, isDisabled: false }

/** 컨셉 보드의 그림 자리(지금의 빈 면)를 흉내 낸 것. */
const imagePlaceholder = (
  <div data-concept-image className="flex h-36 w-full items-center justify-center">
    {(() => {
      const Shape = CONTAINER_ICONS.can
      return <Shape aria-hidden className="h-24 w-24" data-concept-shape />
    })()}
  </div>
)

const IMAGE_STATES: ConceptImageState[] = ["none", "working", "ready", "failed"]

/** 주소에 ?imageChat=대화id&imageConcept=컨셉id 를 주면 서버에 붙은 진짜 부품을 하나 더 보인다(확인용). */
function LiveConceptImage() {
  const q = new URLSearchParams(window.location.search)
  const chat = q.get("imageChat")
  const concept = q.get("imageConcept")
  if (!chat || !concept) return null
  return (
    <Labeled label={conceptImageCopy.designStates.live}>
      <Card padding={4}>
        <ConceptImage chatId={chat} conceptId={concept} placeholder={imagePlaceholder} />
      </Card>
    </Labeled>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <VStack gap={4}>
      <Heading level={2}>{title}</Heading>
      {children}
    </VStack>
  )
}

function Labeled({ label, children }: { label: string; children: ReactNode }) {
  return (
    <VStack gap={2}>
      <Text type="supporting">{label}</Text>
      {children}
    </VStack>
  )
}

/** 찾아본 것: 단추를 누르면 항목이 하나 늘고, 새 항목만 잠깐 강조된다. */
function EvidenceDemo() {
  const [items, setItems] = useState(sample.sampleEvidenceItems)
  const n = items.length - sample.sampleEvidenceItems.length
  return (
    <VStack gap={3} hAlign="start">
      <div className="w-full">
        <WorkbenchCard card={sample.sampleEvidence(items)} />
      </div>
      <Button
        label={d.addEvidence}
        variant="secondary"
        size="sm"
        onClick={() => setItems((it) => [...it, { ...sample.sampleEvidenceExtra, id: `extra-${n}` }])}
      />
    </VStack>
  )
}

/** 카드 안에서 고르기: 누를 수 있는 것 하나(대화 쪽 보내기 버튼과 함께)와, 둘 고름, 보낸 뒤. */
function OnCardDemo() {
  const [picked, setPicked] = useState<string[]>([])
  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]))
  return (
    <VStack gap={6}>
      <Labeled label={d.onCardBefore}>
        <div data-demo="on-card-live" className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <Labeled label={d.onCardChat}>
            <OnCardPrompt count={picked.length} onSend={() => setPicked([])} />
          </Labeled>
          <div className="min-w-0 lg:col-span-2">
            <WorkbenchCard card={sample.sampleIdeasSuggested} pick={{ selected: picked, isLocked: false, onToggle: toggle }} />
          </div>
        </div>
      </Labeled>
      <Labeled label={d.onCardTwo}>
        <WorkbenchCard card={sample.sampleIdeasSuggested} pick={{ selected: ["a", "b"], isLocked: false, onToggle: noop }} />
      </Labeled>
      <Labeled label={d.onCardSent}>
        <WorkbenchCard card={sample.sampleIdeasSuggested} />
      </Labeled>
    </VStack>
  )
}

/**
 * 아이디어 보드: 단추로 다음 차례를 불러오면 하나 빠지고, 하나 고쳐지고, 새것이 들어와 순서가 바뀐다.
 * 카드의 남기기, 빼기를 누르면 기획자의 말로 보낼 글이 아래에 나온다.
 */
function IdeaBoardDemo() {
  const [isNext, setIsNext] = useState(false)
  const [said, setSaid] = useState<string | null>(null)
  return (
    <VStack gap={3} hAlign="start">
      <div className="w-full">
        <WorkbenchCard
          card={isNext ? sample.sampleIdeaBoardNext : sample.sampleIdeaBoard}
          actions={{ onSay: setSaid, isDisabled: false }}
        />
      </div>
      <HStack gap={3} vAlign="center" wrap="wrap">
        <Button
          label={isNext ? d.prevTurn : d.nextTurn}
          variant="secondary"
          size="sm"
          onClick={() => setIsNext((n) => !n)}
        />
        {said && (
          <HStack gap={2} vAlign="center">
            <Text type="supporting">{d.sentAs}</Text>
            <PlannerBubble text={said} />
          </HStack>
        )}
      </HStack>
    </VStack>
  )
}

/** 고르는 차례의 아이디어 보드. 네모 칸으로 고른다. */
function IdeaBoardPickDemo() {
  const [picked, setPicked] = useState<string[]>([])
  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]))
  return (
    <WorkbenchCard
      card={sample.sampleIdeaBoardPick}
      pick={{ selected: picked, isLocked: false, onToggle: toggle }}
      actions={{ onSay: noop, isDisabled: false }}
    />
  )
}

export function DesignPage() {
  const [mode, setMode] = useState<ModeValue>(copy.mode.defaultValue)
  const [openMode, setOpenMode] = useState<ModeValue>(copy.mode.defaultValue)

  return (
    <div className="mx-auto max-w-280 px-10 py-12">
      <VStack gap={10}>
        <Heading level={1}>{d.title}</Heading>

        <Section title={d.colors}>
          <div className="grid grid-cols-4 gap-4 md:grid-cols-7">
            {SWATCHES.map((s) => (
              <VStack key={s.token} gap={2}>
                <div
                  className="h-16 w-full"
                  style={{
                    background: `var(${s.token})`,
                    borderRadius: "var(--radius-container)",
                    border: "1px solid var(--color-border)",
                  }}
                />
                <Text weight="medium">{s.name}</Text>
                <Text type="supporting">{s.token}</Text>
              </VStack>
            ))}
          </div>
        </Section>

        <Section title={d.typeScale}>
          <VStack gap={3}>
            {TEXT_TYPES.map((t) => (
              <HStack key={t} gap={4} vAlign="center">
                <div className="w-28 shrink-0">
                  <Text type="supporting">{t}</Text>
                </div>
                <Text type={t}>{d.typeSample}</Text>
              </HStack>
            ))}
            {HEADING_LEVELS.map((l) => (
              <HStack key={l} gap={4} vAlign="center">
                <div className="w-28 shrink-0">
                  <Text type="supporting">{`heading ${l}`}</Text>
                </div>
                <Heading level={l}>{d.typeSample}</Heading>
              </HStack>
            ))}
          </VStack>
        </Section>

        <Section title={d.buttons}>
          <VStack gap={4}>
            {(["primary", "secondary", "ghost"] as const).map((v) => (
              <HStack key={v} gap={4} vAlign="center" wrap="wrap">
                <div className="w-28 shrink-0">
                  <Text type="supporting">{d.buttonVariants[v]}</Text>
                </div>
                <Button label={d.buttonSample} variant={v} tooltip={d.buttonStates.hover} />
                <Button label={d.buttonSample} variant={v} isDisabled />
              </HStack>
            ))}
            <Text type="supporting">
              {d.buttonStates.normal} · {d.buttonStates.hover} · {d.buttonStates.disabled}
            </Text>
            <Labeled label={d.buttonSizes}>
              <HStack gap={3} vAlign="center">
                <Button label={d.buttonSample} variant="primary" size="sm" />
                <Button label={d.buttonSample} variant="primary" size="md" />
                <Button label={d.buttonSample} variant="primary" size="lg" />
              </HStack>
            </Labeled>
          </VStack>
        </Section>

        <Section title={d.partSwitch}>
          <HStack gap={10} vAlign="start" wrap="wrap">
            <Labeled label={d.partConcept}>
              <PartSwitch value="concept" onChange={noop} />
            </Labeled>
            <Labeled label={d.partTest}>
              <PartSwitch value="test" onChange={noop} />
            </Labeled>
          </HStack>
        </Section>

        <Section title={d.chips}>
          <SuggestionChips />
        </Section>

        <Section title={specCopy.designTitle}>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {specSamples.map((x) => (
              <Card key={x.name} padding={4}>
                <VStack gap={3}>
                  <Heading level={4}>{x.name}</Heading>
                  <SpecSheet spec={x.spec} pack={x.pack} />
                </VStack>
              </Card>
            ))}
          </div>
        </Section>

        <Section title={conceptImageCopy.designTitle}>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
            {IMAGE_STATES.map((st) => (
              <Labeled key={st} label={conceptImageCopy.designStates[st as keyof typeof conceptImageCopy.designStates]}>
                <Card padding={4}>
                  <ConceptImageView
                    state={st}
                    url={st === "ready" ? conceptImageSample : undefined}
                    placeholder={imagePlaceholder}
                    onMake={noop}
                    onAgain={noop}
                  />
                </Card>
              </Labeled>
            ))}
          </div>
          <LiveConceptImage />
        </Section>

        <Section title={d.confirmedBundle}>
          <div className="max-w-190">
            <VStack gap={6}>
              <Labeled label={d.confirmedSome}>
                <ConfirmedConceptCards concepts={confirmedConcepts} onPick={noop} />
              </Labeled>
              <Labeled label={d.confirmedNone}>
                <ConfirmedConceptCards concepts={[]} />
              </Labeled>
              <Labeled label={d.testNotice}>
                <NoticeLine text={copy.home.test.preparing} />
              </Labeled>
            </VStack>
          </div>
        </Section>

        <Section title={d.modeButton}>
          <HStack gap={10} vAlign="start" wrap="wrap">
            <ModeMenu value={mode} onChange={setMode} />
            <Labeled label={d.modeButtonOpen}>
              <div className="h-64">
                <ModeMenu
                  value={openMode}
                  onChange={setOpenMode}
                  placement="below"
                  isMenuOpen
                  onOpenChange={() => {}}
                />
              </div>
            </Labeled>
          </HStack>
        </Section>

        <Section title={d.composer}>
          <div className="max-w-190">
            <VStack gap={6}>
              <Labeled label={d.composerEmpty}>
                <Composer onSubmit={() => {}} />
              </Labeled>
              <Labeled label={d.composerFilled}>
                <Composer onSubmit={() => {}} defaultValue={d.composerSample} />
              </Labeled>
            </VStack>
          </div>
        </Section>

        <Section title={d.navItems}>
          <div className="w-65">
            <SideNav aria-label={d.navItems} topContent={<NewTestButton />}>
                <SideNavSection title={d.navDefault}>
                  <SideNavItem
                    label={mainNavItems[0].label}
                    icon={<Icon icon={mainNavItems[0].icon} size="md" color="secondary" />}
                  />
                </SideNavSection>
                <SideNavSection title={d.navSelected}>
                  <SideNavItem
                    label={mainNavItems[0].label}
                    icon={<Icon icon={mainNavItems[0].icon} size="md" color="secondary" />}
                    selectedIcon={<Icon icon={mainNavItems[0].icon} size="md" color="accent" />}
                    isSelected
                  />
                </SideNavSection>
                <SideNavSection title={d.navRecent}>
                  <RecentTestItem test={recentChats[0]} />
                </SideNavSection>
            </SideNav>
          </div>
        </Section>

        <Section title={d.stepper}>
          <VStack gap={6}>
            <Labeled label={d.stepperFirst}>
              <StageStepper part="concept" activeStep={0} />
            </Labeled>
            <Labeled label={d.stepperSecond}>
              <StageStepper part="concept" activeStep={1} />
            </Labeled>
            <Labeled label={d.stepperThird}>
              <StageStepper part="concept" activeStep={2} />
            </Labeled>
            <Labeled label={d.stepperDone}>
              <StageStepper part="concept" activeStep={3} />
            </Labeled>
            <Labeled label={d.stepperTest}>
              <StageStepper part="test" activeStep={1} />
            </Labeled>
          </VStack>
        </Section>

        <Section title={d.avatar}>
          <HStack gap={10} vAlign="center" wrap="wrap">
            <ChilseongAvatar />
            <Greeting />
          </HStack>
        </Section>

        <Section title={d.bubble}>
          <div className="max-w-190">
            <PlannerBubble text={d.composerSample} />
          </div>
        </Section>

        <Section title={d.chatParts}>
          <div className="max-w-110">
            <VStack gap={8}>
              <Labeled label={d.bubble}>
                <ChatMessageList align="top">
                  <PlannerBubble text={sample.samplePlanner} />
                </ChatMessageList>
              </Labeled>
              <Labeled label={d.activityDone}>
                <ChatMessageList align="top">
                  <ChilseongTurn>
                    <TurnBlock>
                      <ActivityLine data={sample.sampleActivityDone} startedAgoMs={12_000} />
                    </TurnBlock>
                    <TurnBlock>
                      <SayText text={sample.sampleSay} />
                    </TurnBlock>
                  </ChilseongTurn>
                </ChatMessageList>
              </Labeled>
              <Labeled label={d.activityRunning}>
                <ChatMessageList align="top">
                  <ChilseongTurn isThinking>
                    <TurnBlock>
                      <ActivityLine data={sample.sampleActivityRunning} />
                    </TurnBlock>
                  </ChilseongTurn>
                </ChatMessageList>
              </Labeled>
              <Labeled label={d.activitySlow}>
                <ChatMessageList align="top">
                  <ChilseongTurn isThinking>
                    <TurnBlock>
                      <ActivityLine data={sample.sampleActivityRunning} startedAgoMs={12_000} />
                    </TurnBlock>
                  </ChilseongTurn>
                </ChatMessageList>
              </Labeled>
              <Labeled label={d.activityStopped}>
                <ChatMessageList align="top">
                  <ChilseongTurn>
                    <TurnBlock>
                      <ActivityLine data={sample.sampleActivityRunning} isLive={false} isStopped />
                    </TurnBlock>
                    <TurnBlock>
                      <RetryStoppedButton onRetry={noop} />
                    </TurnBlock>
                  </ChilseongTurn>
                  <ChilseongTurn>
                    <TurnBlock>
                      <StoppedLine />
                    </TurnBlock>
                  </ChilseongTurn>
                </ChatMessageList>
              </Labeled>
              <Labeled label={d.activityHalted}>
                <ChatMessageList align="top">
                  <ChilseongTurn>
                    <TurnBlock>
                      <ActivityLine data={sample.sampleActivityRunning} isLive={false} />
                    </TurnBlock>
                  </ChilseongTurn>
                </ChatMessageList>
              </Labeled>
              <Labeled label={`${d.choices} · ${d.active}`}>
                <ChoiceChips id="c1" data={sample.sampleChoices} state={{ isActive: true, chosen: [] }} onReply={noop} />
              </Labeled>
              <Labeled label={`${d.choices} · ${d.past}`}>
                <ChoiceChips id="c2" data={sample.sampleChoices} state={{ isActive: false, chosen: ["a"] }} onReply={noop} />
              </Labeled>
              <Labeled label={`${d.choicesMulti} · ${d.active}`}>
                <ChoiceChips id="c3" data={sample.sampleChoicesMulti} state={{ isActive: true, chosen: [] }} onReply={noop} />
              </Labeled>
              <Labeled label={`${d.actions} · ${d.active}`}>
                <ActionButtons id="a1" data={sample.sampleActions} state={{ isActive: true, chosen: [] }} onReply={noop} />
              </Labeled>
              <Labeled label={`${d.actions} · ${d.past}`}>
                <ActionButtons id="a2" data={sample.sampleActions} state={{ isActive: false, chosen: ["go"] }} onReply={noop} />
              </Labeled>
              <Labeled label={`${d.actionsNoted} · ${d.actionsNotedTwo}`}>
                <ActionButtons id="a3" data={sample.sampleActionsNotedTwo} state={{ isActive: true, chosen: [] }} onReply={noop} />
              </Labeled>
              <Labeled label={`${d.actionsNoted} · ${d.actionsNotedThree}`}>
                <ActionButtons id="a4" data={sample.sampleActionsNotedThree} state={{ isActive: true, chosen: [] }} onReply={noop} />
              </Labeled>
              <Labeled label={`${d.actionsNoted} · ${d.actionsNotedThree} · ${d.past}`}>
                <ActionButtons id="a5" data={sample.sampleActionsNotedThree} state={{ isActive: false, chosen: ["confirm"] }} onReply={noop} />
              </Labeled>
              <Labeled label={`${d.confirm} · ${d.active}`}>
                <ConfirmCard id="f1" data={sample.sampleConfirm} state={{ isActive: true, chosen: [] }} onReply={noop} />
              </Labeled>
              <Labeled label={`${d.confirm} · ${d.past}`}>
                <ConfirmCard id="f2" data={sample.sampleConfirm} state={{ isActive: false, chosen: ["start"] }} onReply={noop} />
              </Labeled>
              <Labeled label={d.confirmNoted}>
                <ConfirmCard id="f3" data={sample.sampleConfirmNoted} state={{ isActive: true, chosen: [] }} onReply={noop} />
              </Labeled>
              <Labeled label={d.summary}>
                <SummaryCard data={sample.sampleSummary} />
              </Labeled>
              <Labeled label={d.disconnected}>
                <DisconnectedNotice onResend={noop} />
              </Labeled>
            </VStack>
          </div>
        </Section>

        <Section title={d.multiChips}>
          <div className="max-w-110">
            <VStack gap={6}>
              <Labeled label={d.active}>
                <ChoiceChips id="m1" data={sample.sampleChoicesMulti} state={{ isActive: true, chosen: [] }} onReply={noop} />
              </Labeled>
              <Labeled label={d.past}>
                <ChoiceChips id="m2" data={sample.sampleChoicesMulti} state={{ isActive: false, chosen: ["price", "promo"] }} onReply={noop} />
              </Labeled>
            </VStack>
          </div>
        </Section>

        <Section title={d.chipsAndButtons}>
          <div className="max-w-110">
            <VStack gap={6}>
              <Labeled label={d.choices}>
                <ChoiceChips id="h1" data={sample.sampleChoicesFree} state={{ isActive: true, chosen: [] }} onReply={noop} />
              </Labeled>
              <Labeled label={d.freeChip}>
                <ChoiceChips id="h2" data={sample.sampleChoicesFree} state={{ isActive: false, chosen: ["with-lunch"] }} onReply={noop} />
              </Labeled>
              <Labeled label={d.actions}>
                <ActionButtons id="h3" data={sample.sampleActionsNotedThree} state={{ isActive: true, chosen: [] }} onReply={noop} />
              </Labeled>
              <Labeled label={d.chipsLong}>
                <ActionButtons id="h4" data={sample.sampleActionsLong} state={{ isActive: true, chosen: [] }} onReply={noop} />
              </Labeled>
              <Labeled label={d.onCardChat}>
                <OnCardPrompt count={2} onSend={noop} />
              </Labeled>
            </VStack>
          </div>
        </Section>

        <Section title={d.navCollapsed}>
          <HStack gap={10} vAlign="start" wrap="wrap">
            <Labeled label={d.navCollapsed}>
              <div className="h-110">
                <SideNav
                  aria-label={d.navCollapsed}
                  collapsible={{ isCollapsed: true, hasButton: false }}
                  topContent={<NewTestButton isIconOnly />}
                  footer={
                    <VStack gap={3}>
                      <MainNavLinks isCollapsed pathname="/panel" />
                      <OwnerRow isCollapsed />
                    </VStack>
                  }
                >
                  {null}
                </SideNav>
              </div>
            </Labeled>
            <Labeled label={d.navExpanded}>
              <div className="h-110 w-65">
                <SideNav
                  aria-label={d.navExpanded}
                  topContent={<NewTestButton />}
                  footer={
                    <VStack gap={3}>
                      <MainNavLinks isCollapsed={false} pathname="/panel" />
                      <OwnerRow isCollapsed={false} />
                    </VStack>
                  }
                >
                  <SideNavSection title={copy.nav.recentChats}>
                    <RecentChatList chats={recentChats} />
                  </SideNavSection>
                </SideNav>
              </div>
            </Labeled>
          </HStack>
        </Section>

        <Section title={d.evidence}>
          <div className="max-w-230 p-6" style={{ background: "var(--color-background-muted)" }}>
            <VStack gap={6}>
              <Labeled label={d.evidenceAdded}>
                <EvidenceDemo />
              </Labeled>
              <Labeled label={d.evidenceLong}>
                <WorkbenchCard card={sample.sampleEvidence([sample.sampleEvidenceLong, ...sample.sampleEvidenceItems.slice(0, 1)])} />
              </Labeled>
              <Labeled label={d.narrow}>
                <div className="max-w-110">
                  <WorkbenchCard card={sample.sampleEvidence(sample.sampleEvidenceItems)} />
                </div>
              </Labeled>
            </VStack>
          </div>
        </Section>

        <Section title={d.onCard}>
          <div className="max-w-230 p-6" style={{ background: "var(--color-background-muted)" }}>
            <OnCardDemo />
          </div>
        </Section>

        <Section title={d.recentMarks}>
          <div className="w-65">
            <SideNav aria-label={d.recentMarks}>
              <SideNavSection title={copy.nav.recentChats}>
                <RecentChatList chats={recentChats} onDelete={noop} />
              </SideNavSection>
            </SideNav>
          </div>
        </Section>

        <Section title={d.workbenchCards}>
          <div className="max-w-230 p-6" style={{ background: "var(--color-background-muted)" }}>
            <VStack gap={6}>
              {sample.sampleBriefs.map((c, i) => (
                <Labeled key={c.id} label={d.briefStates[i]}>
                  <WorkbenchCard card={c} />
                </Labeled>
              ))}
              <Labeled label={d.ideaBoard}>
                <IdeaBoardDemo />
              </Labeled>
              <Labeled label={d.ideaBoardPick}>
                <IdeaBoardPickDemo />
              </Labeled>
              <Labeled label={d.ideaBoardBusy}>
                <WorkbenchCard card={sample.sampleIdeaBoard} actions={{ onSay: noop, isDisabled: true }} />
              </Labeled>
              <Labeled label={d.ideaCards}>
                <WorkbenchCard card={sample.sampleIdeasSuggested} />
              </Labeled>
              <Labeled label={d.conceptTwo}>
                <WorkbenchCard card={sample.sampleConcepts} />
              </Labeled>
              <Labeled label={d.conceptOne}>
                <div className="max-w-130">
                  <WorkbenchCard card={sample.sampleConceptOne} />
                </div>
              </Labeled>
              <Labeled label={d.conceptChanged}>
                <WorkbenchCard card={sample.sampleConceptsChanged} />
              </Labeled>
              <Labeled label={d.conceptNoRivals}>
                <div className="max-w-130">
                  <WorkbenchCard card={sample.sampleConceptNoRivals} />
                </div>
              </Labeled>
              <Labeled label={d.conceptOld}>
                <div className="max-w-130">
                  <WorkbenchCard card={sample.sampleConceptOld} />
                </div>
              </Labeled>
              <Labeled label={`${d.ideasTable} · ${d.narrow}`}>
                <div className="max-w-110">
                  <WorkbenchCard card={sample.sampleIdeas} />
                </div>
              </Labeled>
              <Labeled label={`${d.conceptBoard} · ${d.narrow}`}>
                <div className="max-w-110">
                  <WorkbenchCard card={sample.sampleConcepts} />
                </div>
              </Labeled>
              <Labeled label={d.improveCard}>
                <WorkbenchCard card={sample.sampleImprove} runSamples={sample.sampleImproveRuns} say={designSay} />
              </Labeled>
              <Labeled label={`${d.improveCard} · ${d.narrow}`}>
                <div className="max-w-110">
                  <WorkbenchCard card={sample.sampleImprove} runSamples={sample.sampleImproveRuns} say={designSay} />
                </div>
              </Labeled>
              {([[d.diagnosisFlags, diagnosis.diagnosisFlags], [d.diagnosisClear, diagnosis.diagnosisClear],
                [d.diagnosisNoFix, diagnosis.diagnosisNoFix]] as const).map(([label, c]) => (
                <Labeled key={c.id} label={label}>
                  <div className="max-w-180" data-sample={c.id}>
                    <WorkbenchCard card={c} say={designSay} />
                  </div>
                </Labeled>
              ))}
              <Labeled label={dashCopy.designRunning}>
                <div className="max-w-220" data-sample="result-running">
                  <WorkbenchCard card={sampleResultCard(sampleResultRunning.id)} runSample={sampleResultRunning} say={designSay} />
                </div>
              </Labeled>
              <Labeled label={dashCopy.designOld}>
                <div className="max-w-220" data-sample="result-old">
                  <WorkbenchCard card={sampleResultCard(sampleResultOld.id)} runSample={sampleResultOld} say={designSay} />
                </div>
              </Labeled>
              <Labeled label={d.otherCards}>
                <VStack gap={4}>
                  <WorkbenchCard card={exploreSampleCard} runSample={exploreSampleRun} />
                  {sample.sampleOtherCards.map((c) => (
                    <WorkbenchCard key={c.id} card={c} runSample={sample.sampleRunView} />
                  ))}
                </VStack>
              </Labeled>
              <Labeled label={d.loadingCard}>
                <WorkbenchCard card={sample.sampleLoading} />
              </Labeled>
              <Labeled label={d.errorCard}>
                <WorkbenchCard card={sample.sampleError} onRetry={noop} />
              </Labeled>
            </VStack>
          </div>
        </Section>

        <Section title={shelfCopy.waiting.designTitle}>
          <VStack gap={4}>
            <WorkbenchCard card={waitingExploreCard} runSample={waitingExploreEarly} />
            <WorkbenchCard card={waitingExploreCard} runSample={waitingExploreRun} />
            <WorkbenchCard card={waitingTargetCard} runSample={waitingTargetRun} />
            <div className="max-w-110">
              <WorkbenchCard card={waitingExploreCard} runSample={waitingExploreRun} />
            </div>
          </VStack>
        </Section>
        <Section title={d.card}>
          <div className="max-w-90">
            <Card>
              <VStack gap={2}>
                <Heading level={4}>{d.cardTitle}</Heading>
                <Text color="secondary">{d.cardBody}</Text>
              </VStack>
            </Card>
          </div>
        </Section>

        <Section title={d.emptyState}>
          <Card>
            <PreparingState />
          </Card>
        </Section>
      </VStack>
    </div>
  )
}
