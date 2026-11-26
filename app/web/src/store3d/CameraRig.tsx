import { forwardRef, type ComponentRef, useCallback, useImperativeHandle, useLayoutEffect, useRef } from "react"
import { useThree } from "@react-three/fiber"
import { OrbitControls } from "@react-three/drei"
import * as THREE from "three"
import { VIEW } from "./config"
import { FIT_POINTS } from "./Scene"

type OrbitControlsImpl = ComponentRef<typeof OrbitControls>

export type CameraRigHandle = { reset: () => void }


/**
 * 직교 카메라를 처음 시점에 놓고, 매장 전체가 창에 들어오도록 확대 정도를 맞춘다(fit).
 * 돌리기는 좌우로 제한된 범위, 위아래는 바닥 아래로 내려가지 않게. 당기고 밀기는 fit의 배수로 제한.
 * 창 크기가 바뀌면 fit을 다시 구하고 사용자가 당긴 만큼(배수)은 그대로 둔다.
 * zoomable이 false면 휠로 당기지 않는다(카드 안에서 페이지를 스크롤하다 걸리지 않게). 휠 이벤트도 막지 않는다.
 */
export const CameraRig = forwardRef<CameraRigHandle, { onInteract?: () => void; zoomable?: boolean }>(function CameraRig(
  { onInteract, zoomable = true },
  ref,
) {
  const camera = useThree((s) => s.camera) as THREE.OrthographicCamera
  const size = useThree((s) => s.size)
  const controls = useRef<OrbitControlsImpl>(null)
  const fit = useRef(1)

  /** 처음 시점의 방향으로 카메라를 놓고, 매장이 가운데 오도록 중심을 옮긴 뒤 fit을 구한다. */
  const place = useCallback(() => {
    const target = new THREE.Vector3(...VIEW.target)
    const dir = new THREE.Vector3().setFromSphericalCoords(VIEW.distance, VIEW.polar, VIEW.azimuth)
    camera.position.copy(target).add(dir)
    camera.lookAt(target)
    camera.updateMatrixWorld()
    const box = new THREE.Box2()
    for (const c of FIT_POINTS) {
      const p = c.clone().applyMatrix4(camera.matrixWorldInverse)
      box.expandByPoint(new THREE.Vector2(p.x, p.y))
    }
    const center = box.getCenter(new THREE.Vector2())
    const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0)
    const up = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 1)
    const shift = right.multiplyScalar(center.x).add(up.multiplyScalar(center.y))
    const bw = box.max.x - box.min.x
    const bh = box.max.y - box.min.y
    return { target: target.add(shift), position: camera.position.clone().add(shift), zoom: Math.min(size.width / bw, size.height / bh) * VIEW.fitMargin }
  }, [camera, size.width, size.height])

  const apply = useCallback(
    (keepFactor: boolean) => {
      const factor = keepFactor ? camera.zoom / fit.current : 1
      const c = controls.current
      if (c && !keepFactor) {
        // 끌기를 멈춘 뒤에도 남은 관성(damping)이 처음 시점을 다시 밀어내지 않게, 남은 움직임을 먼저 다 써 버린다
        c.enableDamping = false
        c.update()
        c.enableDamping = true
      }
      const prev ={ position: camera.position.clone(), target: controls.current?.target.clone() }
      const p = place()
      fit.current = p.zoom
      if (keepFactor && prev.target) {
        camera.position.copy(prev.position)
        controls.current?.target.copy(prev.target)
      } else {
        camera.position.copy(p.position)
        controls.current?.target.copy(p.target)
      }
      camera.zoom = p.zoom * factor
      camera.updateProjectionMatrix()
      if (controls.current) {
        controls.current.minZoom = p.zoom * VIEW.minZoomFactor
        controls.current.maxZoom = p.zoom * VIEW.maxZoomFactor
        controls.current.update()
      }
    },
    [camera, place],
  )

  const first = useRef(true)
  useLayoutEffect(() => {
    apply(!first.current)
    first.current = false
  }, [apply])

  useImperativeHandle(ref, () => ({ reset: () => apply(false) }), [apply])

  /** 끌어 옮기기는 매장 안에서만 */
  const clampPan = () => {
    const c = controls.current
    if (!c) return
    const t = c.target
    const cx = THREE.MathUtils.clamp(t.x, -VIEW.panLimit.x, VIEW.panLimit.x)
    const cz = THREE.MathUtils.clamp(t.z, -VIEW.panLimit.z, VIEW.panLimit.z)
    if (cx !== t.x || cz !== t.z) {
      camera.position.x += cx - t.x
      camera.position.z += cz - t.z
      t.set(cx, t.y, cz)
    }
  }

  return (
    <OrbitControls
      ref={controls}
      makeDefault
      enableDamping
      enableZoom={zoomable}
      screenSpacePanning={false}
      minAzimuthAngle={VIEW.azimuth - VIEW.azimuthRange}
      maxAzimuthAngle={VIEW.azimuth + VIEW.azimuthRange}
      minPolarAngle={VIEW.polarMin}
      maxPolarAngle={VIEW.polarMax}
      onChange={clampPan}
      onStart={onInteract}
    />
  )
})
