import { Component, Suspense, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { Canvas, useLoader } from "@react-three/fiber"
import { ArrowPathIcon } from "@heroicons/react/20/solid"
import { Badge } from "@astryxdesign/core/Badge"
import { Button } from "@astryxdesign/core/Button"
import { Card } from "@astryxdesign/core/Card"
import { EmptyState } from "@astryxdesign/core/EmptyState"
import { HStack } from "@astryxdesign/core/HStack"
import { Icon } from "@astryxdesign/core/Icon"
import { Skeleton } from "@astryxdesign/core/Skeleton"
import { Text } from "@astryxdesign/core/Text"
import { VStack } from "@astryxdesign/core/VStack"
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js"
import { copy } from "../copy"
import { CameraRig, type CameraRigHandle } from "./CameraRig"
import { CONTAINER_MODELS, CUSTOMER_MODELS, MODELS, NEW_SLOT, VIEW, containerModel } from "./config"
import { layoutShelf, type ShelfItem } from "./layout"
import type { HoverInfo } from "./Products"
import { StoreScene, type ConceptOnShelf } from "./Scene"

const SHELF_NAME = "음료"

function hasWebGL() {
  try {
    const c = document.createElement("canvas")
    return Boolean(c.getContext("webgl2") ?? c.getContext("webgl"))
  } catch {
    return false
  }
}

/** 매대의 제품. 서버가 꺼져 있거나 답이 이상하면 빈 목록(매장은 뜨고 선반만 빈다). */
function useShelfItems() {
  const [items, setItems] = useState<ShelfItem[]>([])
  useEffect(() => {
    const ctrl = new AbortController()
    fetch(`/api/shelf?shelf=${encodeURIComponent(SHELF_NAME)}`, { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((body) => {
        if (body && Array.isArray(body.items)) setItems(body.items as ShelfItem[])
      })
      .catch(() => {})
    return () => ctrl.abort()
  }, [])
  return items
}

/**
 * 테마의 강조색(--color-accent)을 읽는다. 입체 장면의 재질은 CSS 변수를 읽지 못하고, 테마의 값은 light-dark(...)로
 * 적혀 있어 그대로 넘길 수 없다. 보이지 않는 요소의 글씨 색으로 풀어 rgb(...)로 받는다.
 */
function useAccent(el: HTMLElement | null) {
  return useMemo(() => {
    if (!el) return NEW_SLOT.fallbackColor
    const probe = document.createElement("span")
    probe.style.color = "var(--color-accent)"
    probe.style.display = "none"
    el.appendChild(probe)
    const color = getComputedStyle(probe).color
    probe.remove()
    return color.startsWith("rgb") ? color : NEW_SLOT.fallbackColor
  }, [el])
}

class SceneBoundary extends Component<{ onError: () => void; children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  componentDidCatch() {
    this.props.onError()
  }
  render() {
    return this.state.failed ? null : this.props.children
  }
}

/** 모든 모형을 불러온 뒤에야 놓이는 부품. 놓이면 뼈대를 걷는다. */
function Ready({ onReady }: { onReady: () => void }) {
  useEffect(() => onReady(), [onReady])
  return null
}

const ALL_MODEL_URLS = [...Object.values(MODELS), ...Object.values(CONTAINER_MODELS), ...CUSTOMER_MODELS]

function LoadingSkeleton({ compact }: { compact: boolean }) {
  return (
    <div className={compact ? "absolute inset-0 p-3" : "absolute inset-0 p-10"} aria-label={copy.store.loading} role="status">
      <Skeleton radius={4} />
    </div>
  )
}

function Failed({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex h-full items-center justify-center">
      <EmptyState
        title={copy.store.failed}
        headingLevel={2}
        actions={<Button label={copy.store.retry} variant="secondary" onClick={onRetry} />}
      />
    </div>
  )
}

/** 제품에 올리면 뜨는 작은 풍선: 이름, 그 아래 용량과 가격, 행사가 있으면 표시. */
function ProductTip({ item }: { item: ShelfItem }) {
  const s = copy.store
  return (
    <Card elevation="med" padding={3}>
      <VStack gap={1.5}>
        <Text weight="semibold">{item.name}</Text>
        <HStack gap={3} vAlign="center" justify="between">
          <HStack gap={2} vAlign="center">
            {item.volume > 0 && <Text hasTabularNumbers>{s.volume(item.volume)}</Text>}
            {item.pack > 1 && <Text hasTabularNumbers>{s.pack(item.pack)}</Text>}
            {item.promo && <Badge label={item.promo} variant="neutral" />}
          </HStack>
          <Text weight="semibold" hasTabularNumbers>
            {s.price(item.price)}
          </Text>
        </HStack>
      </VStack>
    </Card>
  )
}

const TIP_OFFSET = 16

/**
 * 입체 매장 부품(지시서 13, 16). 부모의 크기를 가득 채운다. /store는 이것을 본문 가득 그리고,
 * 매대 테스트 카드는 compact로 넣는다(높이 280~360px쯤).
 */
export type StoreViewProps = {
  /** 신제품 자리에 놓을 컨셉. 없으면 빈자리 표시만. */
  concept?: { name: string; container: string; volume: number; price: number } | null
  /** 테스트의 진행. asked가 늘 때마다 손님이 다녀가고, picked가 늘면 그 손님은 신제품을 집는다. */
  flow?: { asked: number; picked: number; total: number; running: boolean } | null
  /** 매대 앞에 선 손님 머리 위에 띄울 말(테스트에서 실제로 온 답). 없으면 띄우지 않는다. */
  thoughts?: { picked: string[]; passed: string[] } | null
  /** 카드 안에 넣을 때: 시점 되돌리기 버튼과 풍선을 숨긴다. */
  compact?: boolean
}

const noop = () => {}

export default function StoreView({ concept, flow, thoughts, compact = false }: StoreViewProps) {
  const [webgl] = useState(hasWebGL)
  const [attempt, setAttempt] = useState(0)
  const [failed, setFailed] = useState(false)
  const [ready, setReady] = useState(false)
  const [box, setBox] = useState<HTMLDivElement | null>(null)
  const [hover, setHover] = useState<HoverInfo>(null)
  const [hoverSlot, setHoverSlot] = useState<{ clientX: number; clientY: number } | null>(null)
  const lastPointer = useRef({ clientX: 0, clientY: 0 })
  const rig = useRef<CameraRigHandle>(null)
  const started = useRef(performance.now())
  const items = useShelfItems()
  const layout = useMemo(() => layoutShelf(items), [items])
  const accent = useAccent(box)
  const conceptContainer = concept?.container
  const conceptVolume = concept?.volume ?? 0
  const onShelf = useMemo<ConceptOnShelf>(
    () => (conceptContainer !== undefined ? { model: containerModel(conceptContainer, conceptVolume), volume: conceptVolume } : null),
    [conceptContainer, conceptVolume],
  )

  const onReady = useCallback(() => {
    setReady(true)
    // 처음 뜨는 데 걸린 시간(ms). 측정용으로 바깥 틀에 남긴다.
    box?.setAttribute("data-ready-ms", String(Math.round(performance.now() - started.current)))
  }, [box])

  const retry = () => {
    for (const url of ALL_MODEL_URLS) useLoader.clear(GLTFLoader, url)
    started.current = performance.now()
    setFailed(false)
    setReady(false)
    setAttempt((a) => a + 1)
  }

  const tipAt = (clientX: number, clientY: number) => {
    const r = box?.getBoundingClientRect()
    return r ? { left: clientX - r.left + TIP_OFFSET, top: clientY - r.top + TIP_OFFSET } : { left: 0, top: 0 }
  }
  const hoveredItem = !compact && hover ? items[hover.item] : undefined

  if (!webgl || failed) {
    return (
      <div className="h-full w-full">
        <Failed onRetry={webgl ? retry : () => window.location.reload()} />
      </div>
    )
  }

  return (
    <div
      ref={setBox}
      className={compact ? "relative h-full min-h-0 w-full" : "relative h-full min-h-0 w-full overflow-hidden"}
      onPointerMove={compact ? undefined : (e) => (lastPointer.current = { clientX: e.clientX, clientY: e.clientY })}
      style={{ cursor: !compact && (hover || hoverSlot) ? "pointer" : undefined }}
    >
      {box && (
        <SceneBoundary key={attempt} onError={() => setFailed(true)}>
          <Canvas
            orthographic
            shadows="percentage"
            flat
            dpr={[1, 2]}
            gl={{ antialias: true, alpha: true }}
            camera={{ position: [10, 10, 10], zoom: 40, near: 0.1, far: VIEW.distance * 4 }}
            aria-label={copy.store.label}
            onPointerMissed={() => setHover(null)}
          >
            <Suspense fallback={null}>
              <StoreScene
                layout={layout}
                accent={accent}
                hovered={compact ? null : (hover?.item ?? null)}
                onHoverProduct={compact ? noop : setHover}
                onHoverNewSlot={compact ? noop : (h) => setHoverSlot(h ? { ...lastPointer.current } : null)}
                concept={onShelf}
                flow={flow}
                thoughts={thoughts}
                bubbleHost={box}
              />
              <CameraRig
                ref={rig}
                zoomable={!compact}
                onInteract={() => {
                  setHover(null)
                  setHoverSlot(null)
                }}
              />
              <Ready onReady={onReady} />
            </Suspense>
          </Canvas>
        </SceneBoundary>
      )}
      {!ready && <LoadingSkeleton compact={compact} />}
      {ready && !compact && (
        <div className="absolute top-4 right-4">
          <Button
            label={copy.store.resetView}
            variant="secondary"
            icon={<Icon icon={ArrowPathIcon} />}
            onClick={() => {
              setHover(null)
              setHoverSlot(null)
              rig.current?.reset()
            }}
          />
        </div>
      )}
      {hoveredItem && hover && (
        <div className="pointer-events-none absolute" style={tipAt(hover.clientX, hover.clientY)}>
          <ProductTip item={hoveredItem} />
        </div>
      )}
      {!compact && !hover && hoverSlot && (
        <div className="pointer-events-none absolute" style={tipAt(hoverSlot.clientX, hoverSlot.clientY)}>
          <Card elevation="med" padding={3}>
            <Text weight="semibold">{copy.store.newSlot}</Text>
          </Card>
        </div>
      )}
    </div>
  )
}
