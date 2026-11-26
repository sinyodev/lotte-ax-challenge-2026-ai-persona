import { Suspense, useEffect, useMemo, useRef } from "react"
import { useFrame } from "@react-three/fiber"
import { ContactShadows } from "@react-three/drei"
import * as THREE from "three"
import { clone as cloneSkinned } from "three/addons/utils/SkeletonUtils.js"
import { CONTAINER_MODELS, EMPLOYEE, LIGHT, MODELS, NEW_SLOT, NEW_SLOT_POP, PRODUCT, PROPS, SHELF, STORE, type ContainerModel } from "./config"
import { productScale, shelfUnitPositions, type ShelfLayout } from "./layout"
import { ModelInstances, splitByTexture, useModel, type Transform } from "./models"
import { Products, type HoverInfo } from "./Products"
import { Walkers, type Flow, type SceneSignals, type Thoughts } from "./Walkers"

const W = STORE.width
const D = STORE.depth

/** 바닥 타일, 받침, 벽. 뒤쪽 벽(음료 매대)과 왼쪽 벽(창과 문)만 세운다. */
function Shell() {
  const floor = useMemo<Transform[]>(() => {
    const out: Transform[] = []
    for (let i = 0; i < W; i++) for (let j = 0; j < D; j++) out.push({ position: [-W / 2 + i + 0.5, 0, -D / 2 + j + 0.5] })
    return out
  }, [])
  // 모서리 모형이 뒤쪽 모서리의 반 칸씩을 차지하므로, 벽은 모서리에서 반 칸 떨어진 곳부터 놓는다.
  const back = useMemo<Transform[]>(() => {
    const out: Transform[] = []
    for (let x = -W / 2 + 1; x + 0.5 <= W / 2; x += 1) out.push({ position: [x, 0, -D / 2] })
    out.push({ position: [W / 2 - 0.25, 0, -D / 2], scaleX: 0.5 })
    return out
  }, [])
  const left = useMemo(() => {
    const by: Record<string, Transform[]> = {}
    STORE.leftWall.forEach((kind, j) => {
      ;(by[kind] ??= []).push({ position: [-W / 2, 0, -D / 2 + j + 1], rotate: 90 })
    })
    ;(by.wall ??= []).push({ position: [-W / 2, 0, D / 2 - 0.25], rotate: 90, scaleX: 0.5 })
    return by
  }, [])
  const corner = useMemo<Transform[]>(() => [{ position: [-W / 2, 0, -D / 2], rotate: STORE.cornerRotate }], [])
  const t = STORE.wallThickness / 2
  return (
    <group>
      <ModelInstances url={MODELS.floor} transforms={floor} brightness={STORE.floorBrightness} />
      {/* 받침: 바닥 아래로 조금 두께를 주어 책상 위의 모형처럼 */}
      <mesh position={[-t / 2, -STORE.baseHeight / 2 - 0.001, -t / 2]} receiveShadow>
        <boxGeometry args={[W + t, STORE.baseHeight, D + t]} />
        <meshStandardMaterial color={STORE.baseColor} roughness={0.9} />
      </mesh>
      <ModelInstances url={MODELS.wall} transforms={[...back, ...(left.wall ?? [])]} />
      <ModelInstances url={MODELS.wallWindow} transforms={left.wallWindow ?? []} />
      <ModelInstances url={MODELS.wallDoor} transforms={left.wallDoor ?? []} />
      <ModelInstances url={MODELS.wallCorner} transforms={corner} />
    </group>
  )
}

function Props() {
  const byModel = useMemo(() => {
    const by: Partial<Record<keyof typeof MODELS, Transform[]>> = {}
    for (const p of PROPS) (by[p.model] ??= []).push({ position: [p.at[0], 0, p.at[1]], rotate: p.rotate })
    return by
  }, [])
  return (
    <group>
      {Object.entries(byModel).map(([model, transforms]) => (
        <ModelInstances key={model} url={MODELS[model as keyof typeof MODELS]} transforms={transforms!} />
      ))}
    </group>
  )
}

/** 계산대 뒤의 직원. 뼈대가 있는 모형이라 따로 복제하고 서 있는 동작을 튼다. */
function Employee() {
  const gltf = useModel(MODELS.employee)
  const object = useMemo(() => {
    const o = cloneSkinned(gltf.scene)
    o.traverse((c) => {
      c.castShadow = true
      c.raycast = () => null
    })
    return o
  }, [gltf])
  const mixer = useMemo(() => new THREE.AnimationMixer(object), [object])
  useEffect(() => {
    const clip = gltf.animations.find((a) => a.name === EMPLOYEE.animation)
    if (clip) mixer.clipAction(clip).play()
    return () => {
      mixer.stopAllAction()
    }
  }, [gltf, mixer])
  useFrame((_, dt) => mixer.update(dt))
  return (
    <primitive
      object={object}
      position={[EMPLOYEE.at[0], 0, EMPLOYEE.at[1]]}
      rotation={[0, THREE.MathUtils.degToRad(EMPLOYEE.rotate), 0]}
    />
  )
}

/** 음료 매대의 벽 선반. 선반에 붙은 견본 제품은 숨긴다. */
function WallShelves() {
  const transforms = useMemo<Transform[]>(() => shelfUnitPositions().map(([x, z]) => ({ position: [x, 0, z] })), [])
  return <ModelInstances url={MODELS.shelfWall} transforms={transforms} hide={SHELF.hideNodes} />
}

/** 신제품 자리에 놓인 컨셉: 다른 제품과 같이 칸마다 앞뒤 두 줄. 몸통은 강조색. */
function ConceptProducts({ layout, model, volume, color }: { layout: ShelfLayout; model: ContainerModel; volume: number; color: string }) {
  const gltf = useModel(CONTAINER_MODELS[model])
  const split = useMemo(() => splitByTexture(gltf, PRODUCT.bodyChroma), [gltf])
  const material = useMemo(() => new THREE.MeshStandardMaterial({ color, roughness: 0.55, metalness: 0 }), [color])
  useEffect(() => () => material.dispose(), [material])
  const spots = useMemo(() => {
    const [x, y, z] = layout.newSlot.position
    const slotWidth = SHELF.usableWidth / SHELF.slotsPerUnit
    const facings = Math.max(1, Math.round(layout.newSlot.width / slotWidth))
    const z0 = z - (SHELF.rowZ[0] + SHELF.rowZ[1]) / 2
    const out: [number, number, number][] = []
    for (let f = 0; f < facings; f++) {
      for (const rz of SHELF.rowZ) out.push([x - layout.newSlot.width / 2 + slotWidth * (f + 0.5), y, z0 + rz])
    }
    return out
  }, [layout])
  const scale = productScale(model, volume)
  return (
    <group>
      {spots.map((p, i) => (
        <group key={i} position={p} scale={scale}>
          <mesh geometry={split.body} material={material} castShadow raycast={() => null} />
          <mesh geometry={split.trim} material={split.trimMaterial} castShadow raycast={() => null} />
        </group>
      ))}
    </group>
  )
}

export type ConceptOnShelf = { model: ContainerModel; volume: number } | null

/**
 * 신제품 자리: 단 위의 강조색 테두리와 그 위에 떠 있는 아래 방향 표시. 컨셉이 있으면 그 용기를 놓는다.
 * 손님이 신제품을 집으면(signals.popAt) 떠 있는 표시가 한 번 튄다.
 */
function NewSlot({
  layout,
  color,
  concept,
  signals,
  onHover,
}: {
  layout: ShelfLayout
  color: string
  concept: ConceptOnShelf
  signals: SceneSignals
  onHover: (h: boolean) => void
}) {
  const marker = useRef<THREE.Group>(null)
  const [x, y, z] = layout.newSlot.position
  const w = layout.newSlot.width
  const d = Math.abs(SHELF.rowZ[1] - SHELF.rowZ[0]) + 0.12
  const th = NEW_SLOT.frameThickness
  useFrame(({ clock }) => {
    const m = marker.current
    if (!m) return
    const now = clock.elapsedTime
    const since = now - signals.popAt
    const pop = signals.popAt >= 0 && since >= 0 && since < NEW_SLOT_POP.duration ? Math.sin((since / NEW_SLOT_POP.duration) * Math.PI) : 0
    m.position.y = y + NEW_SLOT.markerHeight + Math.sin(now * NEW_SLOT.bobSpeed) * NEW_SLOT.bob + pop * NEW_SLOT_POP.lift
    m.scale.setScalar(1 + pop * NEW_SLOT_POP.scale)
  })
  const bars: [number, number, number, number, number][] = [
    [0, -d / 2, w, th, th],
    [0, d / 2, w, th, th],
    [-w / 2, 0, th, th, d],
    [w / 2, 0, th, th, d],
  ]
  return (
    <group>
      <group position={[x, y + th / 2, z]}>
        {bars.map(([bx, bz, sx, sy, sz], i) => (
          <mesh key={i} position={[bx, 0, bz]}>
            <boxGeometry args={[sx, sy, sz]} />
            <meshBasicMaterial color={color} />
          </mesh>
        ))}
        {/* 올리면 풍선이 뜨는 보이지 않는 칸 */}
        <mesh
          position={[0, 0.12, 0]}
          onPointerMove={(e) => {
            e.stopPropagation()
            onHover(true)
          }}
          onPointerOut={() => onHover(false)}
        >
          <boxGeometry args={[w, 0.24, d]} />
          <meshBasicMaterial visible={false} />
        </mesh>
      </group>
      {concept && <ConceptProducts layout={layout} model={concept.model} volume={concept.volume} color={color} />}
      <group ref={marker} position={[x, y + NEW_SLOT.markerHeight, z + 0.05]}>
        <mesh rotation={[Math.PI, 0, 0]} castShadow>
          <coneGeometry args={[NEW_SLOT.markerSize, NEW_SLOT.markerSize * 1.6, 4]} />
          <meshStandardMaterial color={color} roughness={0.5} />
        </mesh>
      </group>
    </group>
  )
}

export function Lights() {
  return (
    <>
      <hemisphereLight args={[LIGHT.hemisphereSky, LIGHT.hemisphereGround, LIGHT.hemisphere]} />
      <directionalLight
        position={[...LIGHT.directionalPosition]}
        intensity={LIGHT.directional}
        castShadow
        shadow-mapSize={[LIGHT.shadowMapSize, LIGHT.shadowMapSize]}
        shadow-radius={LIGHT.shadowRadius}
        shadow-bias={LIGHT.shadowBias}
        shadow-camera-left={-7}
        shadow-camera-right={7}
        shadow-camera-top={7}
        shadow-camera-bottom={-7}
        shadow-camera-near={1}
        shadow-camera-far={40}
      />
    </>
  )
}

export type StoreSceneProps = {
  layout: ShelfLayout
  accent: string
  hovered: number | null
  onHoverProduct: (info: HoverInfo) => void
  onHoverNewSlot: (h: boolean) => void
  concept: ConceptOnShelf
  flow: Flow | null | undefined
  thoughts?: Thoughts | null
  bubbleHost?: HTMLElement | null
}

export function StoreScene({ layout, accent, hovered, onHoverProduct, onHoverNewSlot, concept, flow, thoughts, bubbleHost }: StoreSceneProps) {
  const signals = useMemo<SceneSignals>(() => ({ popAt: -1 }), [])
  return (
    <group>
      <Lights />
      <Shell />
      <WallShelves />
      <Products layout={layout} hovered={hovered} onHover={onHoverProduct} />
      <NewSlot layout={layout} color={accent} concept={concept} signals={signals} onHover={onHoverNewSlot} />
      <Props />
      <Employee />
      {/* 손님은 따로 불러온다: 손님 모형이 늦어도 매장은 먼저 뜬다 */}
      <Suspense fallback={null}>
        <Walkers flow={flow} layout={layout} accent={accent} dotModel={concept?.model ?? "can"} signals={signals} thoughts={thoughts} bubbleHost={bubbleHost} />
      </Suspense>
      <ContactShadows
        position={[0, -STORE.baseHeight - 0.01, 0]}
        scale={[W + 3, D + 3]}
        opacity={LIGHT.contactOpacity}
        blur={LIGHT.contactBlur}
        far={2}
        resolution={512}
      />
    </group>
  )
}

/**
 * 처음 시점을 맞출 때 창에 들어와야 하는 점들: 받침의 네 모서리(위아래)와 벽 꼭대기(뒤쪽 벽, 왼쪽 벽).
 * 앞쪽과 오른쪽에는 벽이 없어 바닥 높이까지만 본다.
 */
export const FIT_POINTS: THREE.Vector3[] = (() => {
  const t = STORE.wallThickness / 2
  const x0 = -W / 2 - t
  const x1 = W / 2
  const z0 = -D / 2 - t
  const z1 = D / 2
  const top = 1
  const pts: [number, number, number][] = []
  for (const x of [x0, x1]) for (const z of [z0, z1]) pts.push([x, 0, z], [x, -STORE.baseHeight, z])
  pts.push([x0, top, z0], [x1, top, z0], [x0, top, z1])
  return pts.map((p) => new THREE.Vector3(...p))
})()
