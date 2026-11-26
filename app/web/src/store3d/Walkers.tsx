import { useEffect, useMemo, useRef, useState } from "react"
import { Html } from "@react-three/drei"
import { useFrame } from "@react-three/fiber"
import * as THREE from "three"
import { clone as cloneSkinned } from "three/addons/utils/SkeletonUtils.js"
import { CONTAINER_MODELS, CUSTOMER, CUSTOMER_MODELS, PATH, PRODUCT, SHELF, type ContainerModel } from "./config"
import { backWallInner, type ShelfLayout } from "./layout"
import { splitByTexture, useModel } from "./models"

/** 테스트의 진행(StoreViewProps.flow와 같은 모양). */
export type Flow = { asked: number; picked: number; total: number; running: boolean }
/** 손님의 머리 위에 띄울 말(테스트에서 실제로 온 답). picked는 신제품을 집은 손님의 말, passed는 안 집은 손님의 말. */
export type Thoughts = { picked: string[]; passed: string[] }

/** 장면의 부품끼리 나누는 신호. popAt: 손님이 신제품을 집은 시각(장면의 시계, 초). */
export type SceneSignals = { popAt: number }

type XZ = [number, number]
type Visit = { picksNew: boolean }

type Step =
  | { kind: "appear" }
  | { kind: "vanish" }
  | { kind: "walk"; to: XZ }
  /** 서서 face(라디안) 쪽을 본다. pickAt이 있으면 그때 집는다. */
  | { kind: "stand"; time: number; face: number; pickAt?: number; atShelf?: boolean }

type Anim = "walk" | "idle" | "pick"

type Slot = {
  root: THREE.Group
  body: THREE.Object3D
  dot: THREE.Group
  mixer: THREE.AnimationMixer
  actions: Record<Anim, THREE.AnimationAction | null>
  anim: Anim | null
  active: boolean
  lastUsed: number
  steps: Step[]
  i: number
  t: number
  speed: number
  heading: number
  visit: Visit
  picked: boolean
  dotAt: number
  /** 매대 앞에 서는 x(다른 손님과 겹치지 않게 고를 때 본다) */
  standX: number
  bubbleAsked: boolean
}

const FACE_SHELF = Math.PI // -z 쪽(뒤쪽 벽의 매대)
const FACE_REGISTER = Math.PI // 계산대 너머의 직원
const SHELF_FRONT_Z = backWallInner + SHELF.backOffset
const STAND_Z = SHELF_FRONT_Z + PATH.standGap

const rand = (a: number, b: number) => a + Math.random() * (b - a)
const clampX = (x: number) => THREE.MathUtils.clamp(x, PATH.standXRange[0], PATH.standXRange[1])

/** 들어와서 매대 앞에 서고, 집었으면 계산대를 거쳐, 아니면 바로 문으로 나가는 길. */
function route(visit: Visit, standX: number, ambient: boolean, standTime: number): Step[] {
  const o = rand(-CUSTOMER.laneJitter, CUSTOMER.laneJitter)
  const aisle = PATH.backAisleZ + o
  const front = PATH.frontAisleZ + o
  const mid = PATH.midAisleX + o
  const steps: Step[] = [
    { kind: "appear" },
    { kind: "walk", to: [PATH.inLane[0] + o, PATH.inLane[1]] },
    { kind: "walk", to: [PATH.backInX + o, aisle] },
    { kind: "walk", to: [standX, aisle] },
    { kind: "walk", to: [standX, STAND_Z] },
  ]
  if (visit.picksNew) {
    const pickAt = CUSTOMER.lookBeforePick
    steps.push({ kind: "stand", time: pickAt + CUSTOMER.pickHold, face: FACE_SHELF, pickAt, atShelf: true })
  } else {
    steps.push({ kind: "stand", time: standTime, face: FACE_SHELF, atShelf: true })
  }
  steps.push({ kind: "walk", to: [standX, aisle] })
  if (visit.picksNew) {
    steps.push(
      { kind: "walk", to: [mid, aisle] },
      { kind: "walk", to: [mid, front] },
      { kind: "walk", to: [PATH.register[0] + o, front] },
      { kind: "walk", to: [PATH.register[0] + o, PATH.register[1]] },
      { kind: "stand", time: CUSTOMER.pay, face: FACE_REGISTER },
      { kind: "walk", to: [PATH.frontOutX + o, front] },
    )
  } else if (ambient) {
    // 구경하는 손님은 가운데 통로로 내려와 앞쪽을 한 바퀴 돌아 나간다
    steps.push({ kind: "walk", to: [mid, aisle] }, { kind: "walk", to: [mid, front] }, { kind: "walk", to: [PATH.frontOutX + o, front] })
  } else {
    steps.push({ kind: "walk", to: [PATH.backOutX + o, aisle] })
  }
  steps.push(
    { kind: "walk", to: [PATH.outLane[0] + o, PATH.outLane[1]] },
    { kind: "walk", to: [PATH.door[0], PATH.door[1] + o] },
    { kind: "vanish" },
  )
  return steps
}

function play(slot: Slot, anim: Anim) {
  if (slot.anim === anim) return
  const next = slot.actions[anim]
  const prev = slot.anim ? slot.actions[slot.anim] : null
  slot.anim = anim
  if (!next) return
  next.reset()
  next.play()
  if (prev && prev !== next) prev.crossFadeTo(next, CUSTOMER.crossFade, false)
}

function angleTo(from: number, to: number) {
  let d = (to - from) % (Math.PI * 2)
  if (d > Math.PI) d -= Math.PI * 2
  if (d < -Math.PI) d += Math.PI * 2
  return d
}

type Props = {
  flow: Flow | null | undefined
  layout: ShelfLayout
  accent: string
  /** 집은 표시의 모양(신제품의 용기). 컨셉이 없으면 캔. */
  dotModel: ContainerModel
  signals: SceneSignals
  thoughts?: Thoughts | null
  /** 말풍선을 그릴 곳(캔버스의 틀은 넘치는 것을 자르므로 바깥 틀에 그린다) */
  bubbleHost?: HTMLElement | null
}

/**
 * 걸어 다니는 손님(지시서 16). 손님 자리 8개를 미리 만들어 두고 돌려 쓴다.
 * flow.asked가 늘면 그만큼 줄을 세워 0.4초 간격으로 들여보내고, flow.picked가 는 만큼은 신제품을 집는다.
 * 테스트가 없으면(flow가 없거나 시작 전) 손님 한두 명이 천천히 구경한다. 테스트가 끝나면 새 손님은 오지 않는다.
 */
export function Walkers({ flow, layout, accent, dotModel, signals, thoughts, bubbleHost }: Props) {
  // 좁은 곳(카드 안)에서는 풍선이 서로 겹치므로 하나만 띄운다
  const bubbleMax = (bubbleHost?.clientWidth ?? Infinity) < CUSTOMER.bubbleNarrow ? 1 : CUSTOMER.bubbleMax
  const portal = useMemo(() => ({ current: bubbleHost ?? null }) as React.RefObject<HTMLElement>, [bubbleHost])
  // 말풍선: 손님 자리마다 지금 띄운 말(없으면 null). 한 번에 CUSTOMER.bubbleMax개까지.
  const [bubbles, setBubbles] = useState<(string | null)[]>(() => Array(CUSTOMER.maxInside).fill(null))
  const bubbleRef = useRef({ shown: Array(CUSTOMER.maxInside).fill(false) as boolean[], next: 0, turn: { picked: 0, passed: 0 } })
  const thoughtsRef = useRef(thoughts)
  thoughtsRef.current = thoughts
  const gltfs = CUSTOMER_MODELS.map((url) => useModel(url)) // eslint-disable-line react-hooks/rules-of-hooks -- 길이가 고정된 목록
  const dotGltf = useModel(CONTAINER_MODELS[dotModel])

  const slots = useMemo<Slot[]>(
    () =>
      Array.from({ length: CUSTOMER.maxInside }, (_, k) => {
        const gltf = gltfs[k % gltfs.length]
        const body = cloneSkinned(gltf.scene)
        body.traverse((c) => {
          c.castShadow = true
          c.raycast = () => null
          c.frustumCulled = false
        })
        const root = new THREE.Group()
        root.visible = false
        root.add(body)
        const dot = new THREE.Group()
        dot.visible = false
        dot.position.y = CUSTOMER.dotHeight
        root.add(dot)
        const mixer = new THREE.AnimationMixer(body)
        const clip = (name: string) => {
          const c = gltf.animations.find((a) => a.name === name)
          return c ? mixer.clipAction(c) : null
        }
        const pick = clip("pick-up")
        if (pick) {
          pick.setLoop(THREE.LoopOnce, 1)
          pick.clampWhenFinished = true
        }
        return {
          root,
          body,
          dot,
          mixer,
          actions: { walk: clip("walk"), idle: clip("idle"), pick },
          anim: null,
          active: false,
          lastUsed: -k,
          steps: [],
          i: 0,
          t: 0,
          speed: CUSTOMER.speed,
          heading: 0,
          visit: { picksNew: false },
          picked: false,
          dotAt: -1,
          standX: Number.NaN,
          bubbleAsked: false,
        }
      }),
    // gltfs는 주소가 같으면 같은 객체다
    // eslint-disable-next-line react-hooks/exhaustive-deps
    gltfs,
  )

  useEffect(
    () => () => {
      for (const s of slots) s.mixer.stopAllAction()
    },
    [slots],
  )

  // 머리 위의 표시: 신제품 용기 모양을 강조색으로
  const dotMaterial = useMemo(() => new THREE.MeshStandardMaterial({ color: accent, roughness: 0.5 }), [accent])
  const split = useMemo(() => splitByTexture(dotGltf, PRODUCT.bodyChroma), [dotGltf])
  useEffect(() => {
    for (const s of slots) {
      s.dot.clear()
      const b = new THREE.Mesh(split.body, dotMaterial)
      const t = new THREE.Mesh(split.trim, split.trimMaterial)
      for (const m of [b, t]) {
        m.castShadow = false
        m.raycast = () => null
        s.dot.add(m)
      }
    }
  }, [slots, split, dotMaterial])
  useEffect(() => () => dotMaterial.dispose(), [dotMaterial])

  // 줄과 상태. 렌더와 상관없이 매 장면에서 읽고 쓴다.
  const st = useRef({
    queue: [] as Visit[],
    pending: 0,
    prev: { asked: 0, picked: 0 },
    nextSpawn: 0,
    nextAmbient: 0,
    mode: "ambient" as "ambient" | "flow" | "none",
  })
  const layoutRef = useRef(layout)
  layoutRef.current = layout

  const hasFlow = flow != null
  const asked = flow?.asked ?? 0
  const picked = flow?.picked ?? 0
  const running = flow?.running ?? false

  useEffect(() => {
    const s = st.current
    s.mode = !hasFlow || (!running && asked === 0) ? "ambient" : running ? "flow" : "none"
    if (!hasFlow) {
      s.prev = { asked: 0, picked: 0 }
      s.queue = []
      s.pending = 0
      return
    }
    // 숫자가 줄었으면 새 테스트다
    if (asked < s.prev.asked || picked < s.prev.picked) {
      s.prev = { asked: 0, picked: 0 }
      s.queue = []
      s.pending = 0
    }
    const n = Math.max(0, asked - s.prev.asked)
    let m = Math.max(0, picked - s.prev.picked) + s.pending
    s.pending = 0
    s.prev = { asked, picked }

    const fresh: Visit[] = Array.from({ length: n }, () => ({ picksNew: false }))
    // 새 손님 가운데 m명을 고르게 흩어 신제품을 집게 한다
    const order = fresh.map((_, k) => k).sort(() => Math.random() - 0.5)
    for (const k of order) {
      if (m === 0) break
      fresh[k].picksNew = true
      m--
    }
    // picked가 asked보다 늦게 오르면 아직 들어오지 않은 손님에게 넘기고, 그도 없으면 다음 손님에게 미룬다
    for (let k = s.queue.length - 1; k >= 0 && m > 0; k--) {
      if (!s.queue[k].picksNew) {
        s.queue[k].picksNew = true
        m--
      }
    }
    s.pending = m
    s.queue.push(...fresh)
    if (s.queue.length > CUSTOMER.maxBacklog) s.queue.splice(0, s.queue.length - CUSTOMER.maxBacklog)
    if (!running) {
      s.queue = []
      s.pending = 0
    }
  }, [hasFlow, asked, picked, running])

  useFrame(({ clock }, rawDt) => {
    const dt = Math.min(rawDt, 0.1)
    const now = clock.elapsedTime
    const s = st.current
    let inside = 0
    for (const slot of slots) if (slot.active) inside++

    const spawn = (visit: Visit, ambient: boolean) => {
      const free = slots.filter((x) => !x.active).sort((a, b) => a.lastUsed - b.lastUsed)[0]
      if (!free) return
      const lay = layoutRef.current
      // 매대 앞에 이미 선(또는 서러 가는) 손님과 겹치지 않는 x를 고른다
      const taken = slots.filter((x) => x.active).map((x) => x.standX)
      const free_ = (x: number) => taken.every((t) => !(Math.abs(t - x) < CUSTOMER.standSpacing))
      let standX = Number.NaN
      if (visit.picksNew) {
        // 신제품 앞이 차 있으면 바로 옆에 선다
        const x0 = lay.newSlot.position[0]
        for (const k of [0, -1, 1, -2, 2]) {
          const x = clampX(x0 + k * CUSTOMER.standSpacing)
          if (free_(x)) {
            standX = x
            break
          }
        }
        if (Number.isNaN(standX)) standX = x0
      } else {
        for (let tries = 0; tries < 6 && Number.isNaN(standX); tries++) {
          const p = lay.placements[Math.floor(Math.random() * lay.placements.length)]
          const x = clampX((p ? p.position[0] : rand(PATH.standXRange[0], PATH.standXRange[1])) + rand(-CUSTOMER.standJitter, CUSTOMER.standJitter))
          if (free_(x) || tries === 5) standX = x
        }
      }
      const browse = ambient ? CUSTOMER.ambientBrowse : CUSTOMER.browse
      free.active = true
      free.lastUsed = now
      free.visit = visit
      free.steps = route(visit, standX, ambient, rand(browse[0], browse[1]))
      free.i = 0
      free.t = 0
      free.speed = ambient ? CUSTOMER.ambientSpeed : CUSTOMER.speed
      free.picked = false
      free.standX = standX
      free.dotAt = -1
      free.dot.visible = false
      free.bubbleAsked = false
      free.root.position.set(PATH.door[0], 0, PATH.door[1])
      free.root.scale.setScalar(0.001)
      free.heading = Math.PI / 2 // 문에서 매장 안쪽(+x)을 본다
      free.root.rotation.y = free.heading
      free.root.visible = true
      free.anim = null
      free.mixer.stopAllAction()
      play(free, "walk")
      inside++
    }

    if (s.mode === "flow") {
      if (s.queue.length > 0 && inside < CUSTOMER.maxInside && now >= s.nextSpawn) {
        spawn(s.queue.shift()!, false)
        s.nextSpawn = now + CUSTOMER.spawnInterval
      }
    } else if (s.mode === "ambient") {
      if (inside < CUSTOMER.ambientCount && now >= s.nextAmbient) {
        spawn({ picksNew: false }, true)
        s.nextAmbient = now + rand(CUSTOMER.ambientInterval[0], CUSTOMER.ambientInterval[1])
      }
    }

    for (const slot of slots) {
      if (!slot.active) continue
      const step = slot.steps[slot.i]
      if (!step) {
        slot.active = false
        slot.root.visible = false
        slot.mixer.stopAllAction()
        continue
      }
      slot.t += dt
      let face: number | null = null
      let done = false
      const pos = slot.root.position
      switch (step.kind) {
        case "appear":
        case "vanish": {
          const k = Math.min(1, slot.t / CUSTOMER.fade)
          const e = k * k * (3 - 2 * k)
          slot.root.scale.setScalar(Math.max(0.001, step.kind === "appear" ? e : 1 - e))
          if (step.kind === "vanish") play(slot, "walk")
          done = k >= 1
          break
        }
        case "walk": {
          play(slot, "walk")
          const dx = step.to[0] - pos.x
          const dz = step.to[1] - pos.z
          const dist = Math.hypot(dx, dz)
          const move = slot.speed * dt
          if (dist <= move || dist < 1e-4) {
            pos.x = step.to[0]
            pos.z = step.to[1]
            done = true
          } else {
            pos.x += (dx / dist) * move
            pos.z += (dz / dist) * move
            face = Math.atan2(dx, dz)
          }
          break
        }
        case "stand": {
          face = step.face
          // 매대 앞에 서는 순간 말풍선을 띄울지 정한다(테스트가 도는 동안, 한 번에 몇 개만, 사이를 두고)
          if (step.atShelf && !slot.bubbleAsked) {
            slot.bubbleAsked = true
            const b = bubbleRef.current
            const k = slots.indexOf(slot)
            const kind = slot.visit.picksNew ? "picked" : "passed"
            const pool = s.mode === "flow" ? (thoughtsRef.current?.[kind] ?? []) : []
            if (pool.length > 0 && now >= b.next && b.shown.filter(Boolean).length < bubbleMax) {
              const text = pool[b.turn[kind]++ % pool.length]
              b.shown[k] = true
              b.next = now + CUSTOMER.bubbleGap
              step.time = Math.max(step.time, CUSTOMER.bubbleTime)
              setBubbles((prev) => prev.map((x, j) => (j === k ? text : x)))
            }
          }
          if (step.pickAt !== undefined && !slot.picked && slot.t >= step.pickAt) {
            slot.picked = true
            play(slot, "pick")
            if (slot.visit.picksNew) {
              signals.popAt = now
              slot.dotAt = now
            }
          } else if (slot.anim !== "pick" || slot.t >= (step.pickAt ?? 0) + CUSTOMER.pickAnim) {
            play(slot, "idle")
          }
          done = slot.t >= step.time
          break
        }
      }
      if (face !== null) {
        slot.heading += angleTo(slot.heading, face) * Math.min(1, CUSTOMER.turnRate * dt)
        slot.root.rotation.y = slot.heading
      }
      // 걷는 동작의 빠르기를 걷는 속도에 맞춘다
      const walk = slot.actions.walk
      if (walk) walk.timeScale = slot.speed / CUSTOMER.walkAnimSpeed
      slot.mixer.update(dt)

      // 머리 위의 표시: 튀어 오르며 나타났다 줄어들며 사라진다
      if (slot.dotAt >= 0) {
        const a = now - slot.dotAt
        if (a > CUSTOMER.dotTime) {
          slot.dot.visible = false
          slot.dotAt = -1
        } else {
          const inK = Math.min(1, a / CUSTOMER.dotIn)
          const outK = Math.min(1, (CUSTOMER.dotTime - a) / CUSTOMER.dotIn)
          const bump = 1 + CUSTOMER.dotPop * Math.sin(Math.min(1, a / (CUSTOMER.dotIn * 2)) * Math.PI)
          slot.dot.visible = true
          slot.dot.scale.setScalar(CUSTOMER.dotScale * Math.min(inK, outK) * bump)
          slot.dot.rotation.y = a * CUSTOMER.dotSpin - slot.heading
        }
      }

      if (done) {
        // 매대 앞을 떠나면 그 자리를 다른 손님에게 내준다
        if (step.kind === "stand" && step.atShelf) {
          slot.standX = Number.NaN
          const k = slots.indexOf(slot)
          if (bubbleRef.current.shown[k]) {
            bubbleRef.current.shown[k] = false
            setBubbles((prev) => prev.map((x, j) => (j === k ? null : x)))
          }
        }
        slot.i++
        slot.t = 0
      }
    }
  })

  return (
    <group>
      {slots.map((s, k) => (
        <primitive key={k} object={s.root}>
          {bubbles[k] && (
            <Html position={[0, CUSTOMER.bubbleHeight, 0]} center portal={bubbleHost ? portal : undefined} zIndexRange={[20, 10]} style={{ pointerEvents: "none" }}>
              <div data-store-bubble>{bubbles[k]}</div>
            </Html>
          )}
        </primitive>
      ))}
    </group>
  )
}
