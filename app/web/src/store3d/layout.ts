import { KIND_ORDER, PRODUCT, PRODUCT_COLOR, SHELF, STORE, containerModel, type ContainerModel } from "./config"

/** GET /api/shelf의 제품 하나(app/server/tools/shelf_items.py). */
export type ShelfItem = {
  id: string
  name: string
  kind: string
  container: string
  volume: number
  pack: number
  price: number
  promo: string | null
  ours: boolean
}

/** 매대 위의 한 칸에 놓인 제품 하나(같은 제품이 여러 칸에 놓인다). */
export type Placement = {
  item: number // items의 차례
  model: ContainerModel
  position: [number, number, number]
  scale: number
}

export type ShelfLayout = {
  placements: Placement[]
  /** 신제품 자리의 가운데(단의 윗면)와 폭 */
  newSlot: { position: [number, number, number]; width: number }
  colors: string[]
}

/** 뒤쪽 벽 안쪽 면의 z. */
export const backWallInner = -STORE.depth / 2 + STORE.wallThickness / 2

/** 선반 모형 하나의 놓는 자리(x, z). 왼쪽부터. */
export function shelfUnitPositions(): [number, number][] {
  const total = SHELF.units * SHELF.unitWidth
  return Array.from({ length: SHELF.units }, (_, i) => [
    -total / 2 + SHELF.unitWidth * (i + 0.5),
    backWallInner + SHELF.backOffset,
  ])
}

function hash(text: string) {
  let h = 2166136261
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

export function brandKey(name: string) {
  const words = name.trim().split(/\s+/)
  const word = words.length > 1 && PRODUCT_COLOR.makerWords.includes(words[0]) ? words[1] : words[0]
  return word.slice(0, PRODUCT_COLOR.brandKeyLength)
}

/** 제품의 색: 브랜드에서 색상을, 이름에서 채도와 밝기를 정한다. 같은 이름은 늘 같은 색. */
export function productColor(name: string) {
  const c = PRODUCT_COLOR
  const b = hash(brandKey(name))
  const n = hash(name)
  const hue = (c.hues[b % c.hues.length] + ((n % 1000) / 1000 - 0.5) * c.hueJitter + 360) % 360
  const pick = (range: readonly [number, number], seed: number) => range[0] + (range[1] - range[0]) * ((seed % 997) / 996)
  const sat = pick(c.saturation, b >>> 7)
  let light = pick(c.lightness, n >>> 11)
  if (name.includes("제로")) light += c.zeroLightness
  return `hsl(${hue.toFixed(0)}, ${(sat * 100).toFixed(0)}%, ${(Math.max(0.2, light) * 100).toFixed(0)}%)`
}

export function productScale(model: ContainerModel, volume: number) {
  const f = volume > 0 ? Math.cbrt(volume / PRODUCT.referenceMl) : 1
  return PRODUCT.baseScale[model] * Math.min(PRODUCT.maxFactor, Math.max(PRODUCT.minFactor, f))
}

/**
 * 매대 배치. 종류끼리 모아 왼쪽부터 "열"을 세운다. 열 하나 = 위 단 제품 하나 + 아래 단 제품 하나.
 * 종류 사이의 경계 가운데 매대 한가운데에 가장 가까운 곳에 빈 열(신제품 자리)을 하나 끼운다.
 * 열마다 같은 제품을 칸 여럿(facings)에 나란히 놓아 매대를 채운다. 빈 칸은 같은 단의 왼쪽 제품으로 채운다.
 */
export function layoutShelf(items: ShelfItem[]): ShelfLayout {
  const order = new Set([...KIND_ORDER, ...items.map((item) => item.kind)])
  const groups = [...order]
    .map((kind) => items.map((it, idx) => ({ it, idx })).filter((x) => x.it.kind === kind).map((x) => x.idx))
    .filter((g) => g.length > 0)

  type Column = { top: number | null; bottom: number | null; isNew?: boolean }
  const columns: Column[] = []
  const boundaries: number[] = [0]
  for (const g of groups) {
    const topCount = Math.ceil(g.length / 2)
    for (let i = 0; i < topCount; i++) columns.push({ top: g[i], bottom: g[topCount + i] ?? null })
    boundaries.push(columns.length)
  }

  const slotsPerTier = SHELF.units * SHELF.slotsPerUnit
  const center = (columns.length + 1) / 2
  const at = boundaries.reduce((best, b) => (Math.abs(b - center) < Math.abs(best - center) ? b : best), boundaries[0])
  columns.splice(at, 0, { top: null, bottom: null, isNew: true })
  const facings = Math.max(1, Math.min(SHELF.maxFacings, Math.floor(slotsPerTier / columns.length)))

  // 단마다 칸(slot) → 제품. null은 빈 칸. 신제품 자리는 -1.
  const tiers: (number | null)[][] = [Array(slotsPerTier).fill(null), Array(slotsPerTier).fill(null)]
  const used = columns.length * facings
  const startSlot = Math.floor((slotsPerTier - Math.min(used, slotsPerTier)) / 2)
  let newStart = 0
  columns.forEach((col, c) => {
    for (let f = 0; f < facings; f++) {
      const s = startSlot + c * facings + f
      if (s >= slotsPerTier) return
      if (col.isNew) {
        if (f === 0) newStart = s
        tiers[SHELF.eyeTier][s] = -1
        continue
      }
      tiers[1][s] = col.top
      tiers[0][s] = col.bottom
    }
  })
  for (const tier of tiers) {
    for (let s = 0; s < tier.length; s++) {
      if (tier[s] !== null) continue
      const left = tier.slice(0, s).reverse().find((v) => v !== null && v >= 0)
      const right = tier.slice(s + 1).find((v) => v !== null && v >= 0)
      tier[s] = left ?? right ?? null
    }
  }

  const units = shelfUnitPositions()
  const slotWidth = SHELF.usableWidth / SHELF.slotsPerUnit
  const slotX = (s: number) => {
    const [ux] = units[Math.floor(s / SHELF.slotsPerUnit)]
    return ux - SHELF.usableWidth / 2 + slotWidth * ((s % SHELF.slotsPerUnit) + 0.5)
  }
  const z0 = units[0][1]

  const placements: Placement[] = []
  tiers.forEach((tier, t) => {
    tier.forEach((item, s) => {
      if (item === null || item < 0) return
      const it = items[item]
      const model = containerModel(it.container, it.volume)
      for (const rz of SHELF.rowZ) {
        placements.push({ item, model, position: [slotX(s), SHELF.tierY[t], z0 + rz], scale: productScale(model, it.volume) })
      }
    })
  })

  const newSlotX = (slotX(newStart) + slotX(newStart + facings - 1)) / 2
  return {
    placements,
    newSlot: {
      position: [newSlotX, SHELF.tierY[SHELF.eyeTier], z0 + (SHELF.rowZ[0] + SHELF.rowZ[1]) / 2],
      width: slotWidth * facings,
    },
    colors: items.map((i) => productColor(i.name)),
  }
}

/** 빈 매대(서버가 꺼져 있을 때)에도 신제품 자리는 보인다. */
export const emptyLayout = () => layoutShelf([])
