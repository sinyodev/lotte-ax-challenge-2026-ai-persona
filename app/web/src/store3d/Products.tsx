import { useLayoutEffect, useMemo, useRef } from "react"
import type { ThreeEvent } from "@react-three/fiber"
import * as THREE from "three"
import { CONTAINER_MODELS, PRODUCT, type ContainerModel } from "./config"
import type { ShelfLayout } from "./layout"
import { splitByTexture, useModel } from "./models"

export type HoverInfo = { item: number; clientX: number; clientY: number } | null

type Props = {
  layout: ShelfLayout
  hovered: number | null
  onHover: (info: HoverInfo) => void
}

const bodyMaterial = new THREE.MeshStandardMaterial({ color: "#ffffff", roughness: 0.55, metalness: 0 })

function ContainerInstances({ model, layout, hovered, onHover }: Props & { model: ContainerModel }) {
  const gltf = useModel(CONTAINER_MODELS[model])
  const split = useMemo(() => splitByTexture(gltf, PRODUCT.bodyChroma), [gltf])
  const placements = useMemo(() => layout.placements.filter((p) => p.model === model), [layout, model])
  const bodyRef = useRef<THREE.InstancedMesh>(null)
  const trimRef = useRef<THREE.InstancedMesh>(null)

  // 색은 배치가 바뀔 때만 칠한다
  useLayoutEffect(() => {
    const body = bodyRef.current
    if (!body) return
    const c = new THREE.Color()
    placements.forEach((p, i) => body.setColorAt(i, c.setStyle(layout.colors[p.item])))
    if (body.instanceColor) body.instanceColor.needsUpdate = true
  }, [placements, layout])

  // 자리는 올린 제품이 바뀔 때도 다시 놓는다(올린 제품만 조금 들린다)
  useLayoutEffect(() => {
    const m = new THREE.Matrix4()
    const q = new THREE.Quaternion()
    const s = new THREE.Vector3()
    const v = new THREE.Vector3()
    for (const mesh of [bodyRef.current, trimRef.current]) {
      if (!mesh) continue
      placements.forEach((p, i) => {
        v.set(p.position[0], p.position[1] + (p.item === hovered ? PRODUCT.hoverLift : 0), p.position[2])
        mesh.setMatrixAt(i, m.compose(v, q, s.setScalar(p.scale)))
      })
      mesh.instanceMatrix.needsUpdate = true
      mesh.computeBoundingSphere()
    }
  }, [placements, hovered])

  if (placements.length === 0) return null
  const move = (e: ThreeEvent<PointerEvent>) => {
    e.stopPropagation()
    if (e.instanceId === undefined) return
    onHover({ item: placements[e.instanceId].item, clientX: e.nativeEvent.clientX, clientY: e.nativeEvent.clientY })
  }
  const out = () => onHover(null)
  return (
    <group>
      <instancedMesh
        key={`b${placements.length}`}
        ref={bodyRef}
        args={[split.body, bodyMaterial, placements.length]}
        castShadow
        onPointerMove={move}
        onPointerOut={out}
      />
      <instancedMesh
        key={`t${placements.length}`}
        ref={trimRef}
        args={[split.trim, split.trimMaterial, placements.length]}
        castShadow
        onPointerMove={move}
        onPointerOut={out}
      />
    </group>
  )
}

/** 매대 위의 제품. 용기 모형마다 몸통과 테두리 두 개의 InstancedMesh로 그린다. */
export function Products(props: Props) {
  return (
    <group>
      {(Object.keys(CONTAINER_MODELS) as ContainerModel[]).map((m) => (
        <ContainerInstances key={m} model={m} {...props} />
      ))}
    </group>
  )
}
