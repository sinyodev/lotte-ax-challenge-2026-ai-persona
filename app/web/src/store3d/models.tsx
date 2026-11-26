import { useLayoutEffect, useMemo, useRef } from "react"
import { useLoader } from "@react-three/fiber"
import * as THREE from "three"
import { GLTFLoader, type GLTF } from "three/addons/loaders/GLTFLoader.js"

/** 같은 주소는 한 번만 불러온다(useLoader가 주소로 기억한다). Draco 같은 바깥 해독기는 쓰지 않는다. */
export function useModel(url: string): GLTF {
  return useLoader(GLTFLoader, url)
}

/** scaleX는 모형의 x 방향(벽이라면 벽의 길이)만 줄이고 늘린다. */
export type Transform = { position: [number, number, number]; rotate?: number; scale?: number; scaleX?: number }

type MeshPart = { geometry: THREE.BufferGeometry; material: THREE.Material; matrix: THREE.Matrix4 }

/** 모형 안의 메시들을 모형 원점 기준의 행렬과 함께 꺼낸다. hide에 든 이름의 마디(와 그 아래)는 뺀다. */
export function meshParts(gltf: GLTF, hide: string[] = []): MeshPart[] {
  const root = gltf.scene
  root.updateMatrixWorld(true)
  const inv = new THREE.Matrix4().copy(root.matrixWorld).invert()
  const parts: MeshPart[] = []
  const walk = (o: THREE.Object3D) => {
    // GLTFLoader는 같은 이름에 _1, _2를 붙인다
    if (hide.some((h) => o.name === h || o.name.startsWith(`${h}_`))) return
    if ((o as THREE.Mesh).isMesh && !(o as THREE.SkinnedMesh).isSkinnedMesh) {
      const m = o as THREE.Mesh
      const mats = Array.isArray(m.material) ? m.material : [m.material]
      parts.push({ geometry: m.geometry, material: mats[0], matrix: new THREE.Matrix4().multiplyMatrices(inv, m.matrixWorld) })
    }
    o.children.forEach(walk)
  }
  walk(root)
  return parts
}

export function transformMatrix(t: Transform) {
  const s = t.scale ?? 1
  return new THREE.Matrix4().compose(
    new THREE.Vector3(...t.position),
    new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), THREE.MathUtils.degToRad(t.rotate ?? 0)),
    new THREE.Vector3(s * (t.scaleX ?? 1), s, s),
  )
}

function PartInstances({ part, transforms }: { part: MeshPart; transforms: Transform[] }) {
  const ref = useRef<THREE.InstancedMesh>(null)
  useLayoutEffect(() => {
    const mesh = ref.current
    if (!mesh) return
    const m = new THREE.Matrix4()
    transforms.forEach((t, i) => mesh.setMatrixAt(i, m.multiplyMatrices(transformMatrix(t), part.matrix)))
    mesh.instanceMatrix.needsUpdate = true
    mesh.computeBoundingSphere()
  }, [part, transforms])
  return (
    <instancedMesh
      ref={ref}
      args={[part.geometry, part.material, transforms.length]}
      castShadow
      receiveShadow
      raycast={() => null}
    />
  )
}

/**
 * 한 모형을 여러 자리에 놓는다(메시마다 InstancedMesh 하나). 누르거나 올려도 반응하지 않는다.
 * brightness를 주면 재질을 복제해 텍스처 색을 그만큼 밝게 곱한다(1보다 크면 밝아진다).
 */
export function ModelInstances({
  url,
  transforms,
  hide,
  brightness,
}: {
  url: string
  transforms: Transform[]
  hide?: string[]
  brightness?: number
}) {
  const gltf = useModel(url)
  const parts = useMemo(() => {
    const ps = meshParts(gltf, hide)
    if (!brightness) return ps
    return ps.map((p) => {
      const material = p.material.clone() as THREE.MeshStandardMaterial
      material.color.multiplyScalar(brightness)
      return { ...p, material }
    })
  }, [gltf, hide, brightness])
  if (transforms.length === 0) return null
  return (
    <group>
      {parts.map((p, i) => (
        <PartInstances key={`${i}-${transforms.length}`} part={p} transforms={transforms} />
      ))}
    </group>
  )
}

// ---------- 제품 모형: 몸통(색을 칠하는 곳)과 테두리(원래 색)로 나눈다 ----------

export type SplitModel = { body: THREE.BufferGeometry; trim: THREE.BufferGeometry; trimMaterial: THREE.Material }

function texturePixels(texture: THREE.Texture | null) {
  const image = texture?.image as CanvasImageSource & { width: number; height: number } | undefined
  if (!image || !image.width) return null
  const canvas = document.createElement("canvas")
  canvas.width = image.width
  canvas.height = image.height
  const ctx = canvas.getContext("2d", { willReadFrequently: true })
  if (!ctx) return null
  ctx.drawImage(image, 0, 0)
  return { data: ctx.getImageData(0, 0, image.width, image.height).data, width: image.width, height: image.height }
}

/**
 * 모형의 삼각형마다 텍스처에서 색을 읽어, 채도가 높은 곳(캔의 몸통, 병의 라벨)은 몸통으로, 회색·흰색(뚜껑, 테두리)은 테두리로 가른다.
 * 몸통은 제품마다 색을 칠하고, 테두리는 원래의 텍스처를 쓴다.
 */
export function splitByTexture(gltf: GLTF, bodyChroma: number): SplitModel {
  const parts = meshParts(gltf)
  const material = parts[0].material as THREE.MeshStandardMaterial
  const pixels = texturePixels(material.map)
  const body: number[][] = [[], [], []]
  const trim: number[][] = [[], [], []]
  const normalMatrix = new THREE.Matrix3()
  const v = new THREE.Vector3()
  for (const part of parts) {
    const g = part.geometry.index ? part.geometry.toNonIndexed() : part.geometry
    const pos = g.getAttribute("position")
    const nor = g.getAttribute("normal")
    const uv = g.getAttribute("uv")
    normalMatrix.getNormalMatrix(part.matrix)
    for (let t = 0; t < pos.count; t += 3) {
      let isBody = false
      if (pixels && uv) {
        const u = (uv.getX(t) + uv.getX(t + 1) + uv.getX(t + 2)) / 3
        const w = (uv.getY(t) + uv.getY(t + 1) + uv.getY(t + 2)) / 3
        const px = Math.min(pixels.width - 1, Math.max(0, Math.floor((u - Math.floor(u)) * pixels.width)))
        const py = Math.min(pixels.height - 1, Math.max(0, Math.floor((w - Math.floor(w)) * pixels.height)))
        const k = (py * pixels.width + px) * 4
        const r = pixels.data[k], gg = pixels.data[k + 1], b = pixels.data[k + 2]
        isBody = (Math.max(r, gg, b) - Math.min(r, gg, b)) / 255 >= bodyChroma
      }
      const out = isBody ? body : trim
      for (let j = t; j < t + 3; j++) {
        v.fromBufferAttribute(pos, j).applyMatrix4(part.matrix)
        out[0].push(v.x, v.y, v.z)
        v.fromBufferAttribute(nor, j).applyMatrix3(normalMatrix).normalize()
        out[1].push(v.x, v.y, v.z)
        out[2].push(uv ? uv.getX(j) : 0, uv ? uv.getY(j) : 0)
      }
    }
  }
  const make = ([p, n, u]: number[][]) => {
    const geo = new THREE.BufferGeometry()
    geo.setAttribute("position", new THREE.Float32BufferAttribute(p, 3))
    geo.setAttribute("normal", new THREE.Float32BufferAttribute(n, 3))
    geo.setAttribute("uv", new THREE.Float32BufferAttribute(u, 2))
    geo.computeBoundingSphere()
    return geo
  }
  return { body: make(body), trim: make(trim), trimMaterial: material }
}
