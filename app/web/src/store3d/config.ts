/**
 * 입체 매장(지시서 13)의 값을 모두 여기에 둔다: 모형의 주소, 매장의 크기와 배치, 시점, 빛, 제품의 색 규칙.
 * 길이의 단위는 바닥 타일 한 칸(=1)이다. Kenney Mini Market의 벽 높이가 1, 손님 키가 약 0.7이다.
 * 화면(DOM)의 색과 글씨는 여기에 두지 않는다(테마와 copy.ts). 강조색(신제품 자리)도 테마의 --color-accent를 읽는다.
 */

const BASE = "/models/kenney"
const market = (name: string) => `${BASE}/mini-market/Models/GLB format/${name}.glb`
const food = (name: string) => `${BASE}/food-kit/Models/GLB format/${name}.glb`

/** 쓰는 모형. 같은 모형은 한 번 불러와 여러 번 놓는다. */
export const MODELS = {
  floor: market("floor"),
  wall: market("wall"),
  wallWindow: market("wall-window"),
  wallDoor: market("wall-door-rotate"),
  wallCorner: market("wall-corner"),
  shelfWall: market("shelf-end"),
  shelfBoxes: market("shelf-boxes"),
  shelfBags: market("shelf-bags"),
  displayCans: market("display-cans"),
  displayFruit: market("display-fruit"),
  freezer: market("freezer"),
  cashRegister: market("cash-register"),
  employee: market("character-employee"),
  basket: market("shopping-basket"),
  bottleReturn: market("bottle-return"),
} as const

/** 용기 → 제품 모형. 팩은 작은 용량이면 작은 팩. */
export const CONTAINER_MODELS = {
  can: food("soda-can"),
  pet: food("soda-bottle"),
  bottle: food("wine-white"),
  carton: food("carton"),
  cartonSmall: food("carton-small"),
  cup: food("cup-coffee"),
} as const

export type ContainerModel = keyof typeof CONTAINER_MODELS

export function containerModel(container: string, volume: number): ContainerModel {
  switch (container) {
    case "캔":
      return "can"
    case "병":
      return "bottle"
    case "컵":
      return "cup"
    case "팩":
      return volume > 0 && volume <= SMALL_CARTON_ML ? "cartonSmall" : "carton"
    default:
      return "pet"
  }
}
const SMALL_CARTON_ML = 300

/** 매장: 바닥 9×6칸. 뒤쪽 벽(z가 작은 쪽)이 음료 매대, 왼쪽 벽에 창과 문. 앞쪽과 오른쪽은 열어 둔다(들여다보는 모형). */
export const STORE = {
  width: 9,
  depth: 6,
  wallThickness: 0.6,
  /** 바닥 아래의 받침(떠 있는 모형처럼 보이게) */
  baseHeight: 0.18,
  baseColor: "#e9e7e3",
  /** 바닥 타일의 텍스처를 밝게(편의점의 밝은 바닥) */
  floorBrightness: 1.4,
  /**
   * 왼쪽 벽: 뒤쪽 모서리(모서리 모형이 반 칸을 차지한다) 다음부터 앞으로 한 칸씩. 맨 앞의 반 칸은 벽을 반으로 줄여 채운다.
   * 뒤쪽 벽도 같다: 모서리 다음부터 한 칸씩, 오른쪽 끝의 반 칸은 반으로 줄인 벽.
   */
  leftWall: ["wallWindow", "wallWindow", "wallDoor", "wallWindow", "wall"] as const,
  cornerRotate: 90,
}

/** 음료 매대: 뒤쪽 벽에 벽 선반(shelf-end)을 이어 붙인다. 선반 하나에 두 단, 단마다 칸 여섯. */
export const SHELF = {
  units: 10,
  unitWidth: 0.8,
  /** 선반 모형 안에서 단의 윗면 높이(아래 단, 위 단). 위 단이 눈높이다. */
  tierY: [0.135, 0.505] as const,
  eyeTier: 1,
  /** 단 안에서 쓸 수 있는 폭(선반 기둥 사이)과 칸 수 */
  usableWidth: 0.7,
  slotsPerUnit: 6,
  /** 제품 하나가 차지하는 칸의 최대 수(신제품 자리도 이 폭이다) */
  maxFacings: 2,
  /** 선반 모형의 뒷면이 원점에서 떨어진 거리. 제품이 놓이는 깊이(앞줄, 뒷줄). */
  backOffset: 0.4,
  rowZ: [-0.11, -0.22] as const,
  /** 선반 모형에 붙어 있는 견본 제품(이름). 우리 제품을 올리므로 숨긴다. */
  hideNodes: ["bottle", "carton"],
}

/** 매대 위 제품의 차례: 종류끼리 모으고 이 차례로 왼쪽부터 놓는다. 없는 종류는 뒤에 붙는다. */
export const KIND_ORDER = ["우유·단백", "탄산", "탄산수", "에너지", "이온", "물", "차", "커피", "주스"]

/** 제품 모형의 크기. Food Kit은 Mini Market보다 크게 만들어져 있어 줄인다. 용량에 따라 조금 크고 작게. */
export const PRODUCT = {
  baseScale: { can: 0.5, pet: 0.5, bottle: 0.45, carton: 0.42, cartonSmall: 0.48, cup: 0.8 } as Record<ContainerModel, number>,
  referenceMl: 450,
  minFactor: 0.85,
  maxFactor: 1.15,
  /** 올렸을 때 제품이 들리는 높이 */
  hoverLift: 0.025,
  /** 용기의 몸통으로 보는 텍스처 색의 채도(최대-최소). 이보다 낮은 회색·흰색(뚜껑, 테두리)은 원래 색을 둔다. */
  bodyChroma: 0.22,
}

/** 제품의 색: 같은 브랜드는 비슷한 색. 이름에서 늘 같게 정한다. */
export const PRODUCT_COLOR = {
  /** 이름 맨 앞의 회사 이름은 브랜드가 아니라 건너뛴다. */
  makerWords: ["롯데", "매일", "남양", "맥심", "광동", "웅진", "동원", "빙그레", "해태", "농심"],
  /** 브랜드의 열쇠: 브랜드 낱말의 앞 두 글자(펩시콜라·펩시 → 펩시) */
  brandKeyLength: 2,
  /** 브랜드가 고르는 색상(도). 보라는 뺀다(화면의 원칙). */
  hues: [4, 18, 30, 42, 52, 95, 140, 165, 190, 205, 220, 345],
  saturation: [0.55, 0.75] as const,
  lightness: [0.5, 0.6] as const,
  /** 같은 브랜드 안에서 제품마다 색상이 흔들리는 폭(도) */
  hueJitter: 14,
  /** "제로"가 붙은 제품은 더 어둡게 */
  zeroLightness: -0.2,
}

/** 신제품 자리: 눈높이 단의 한 칸(제품 하나 너비)을 비우고 강조색 테두리와 떠 있는 표시를 단다. */
export const NEW_SLOT = {
  /** 테마가 없을 때만 쓰는 강조색 */
  fallbackColor: "#da291c",
  frameThickness: 0.018,
  markerSize: 0.14,
  markerHeight: 0.5,
  bob: 0.025,
  bobSpeed: 2.2,
}

/** 시점: 위에서 비스듬히(등각에 가깝게) 내려다보는 직교 카메라. 각도는 라디안. */
export const VIEW = {
  target: [0.2, 0.25, -0.3] as const,
  azimuth: 0.42,
  polar: 0.95,
  distance: 20,
  azimuthRange: 0.6,
  polarMin: 0.55,
  polarMax: 1.2,
  /** 처음 시점에서 매장이 창을 채우는 비율 */
  fitMargin: 0.94,
  minZoomFactor: 0.8,
  maxZoomFactor: 4,
  /** 끌어 옮길 수 있는 범위(시점의 중심) */
  panLimit: { x: 3.5, z: 2.5 },
}

export const LIGHT = {
  hemisphereSky: "#ffffff",
  hemisphereGround: "#d8d4cc",
  hemisphere: 1.6,
  directional: 1.4,
  directionalPosition: [6, 12, 8] as const,
  shadowMapSize: 2048,
  shadowRadius: 6,
  shadowBias: -0.0004,
  /** 받침 아래의 옅은 그림자 */
  contactOpacity: 0.22,
  contactBlur: 2.8,
}

/** 매장의 소품(손님이 지나다닐 길을 비워 둔다). 위치 [x, z], 돌림(도, y축). */
export const PROPS: { model: keyof typeof MODELS; at: [number, number]; rotate?: number }[] = [
  // 가운데 양면 진열대 두 줄(앞뒤로 붙여 놓는다)
  { model: "shelfBoxes", at: [-2.6, 0.15] },
  { model: "shelfBags", at: [-1.8, 0.15] },
  { model: "shelfBoxes", at: [-1.0, 0.15] },
  { model: "shelfBags", at: [-2.6, -0.55], rotate: 180 },
  { model: "shelfBoxes", at: [-1.8, -0.55], rotate: 180 },
  { model: "shelfBags", at: [-1.0, -0.55], rotate: 180 },
  // 오른쪽: 아이스크림 냉동고와 행사 진열대
  { model: "freezer", at: [1.4, -0.2] },
  { model: "displayCans", at: [1.4, 0.75] },
  { model: "displayFruit", at: [-1.8, 1.6] },
  // 앞쪽 오른편 계산대(직원이 앞쪽을 본다)
  { model: "cashRegister", at: [2.8, 1.75] },
  // 문 옆의 장바구니
  { model: "basket", at: [-3.75, 1.05] },
  { model: "basket", at: [-3.75, 1.4] },
  { model: "bottleReturn", at: [-3.8, 2.5], rotate: 90 },
]

export const EMPLOYEE = { at: [2.8, 1.1] as [number, number], rotate: 0, animation: "idle" }

// ---------- 지시서 16: 걸어 다니는 손님 ----------

const people = (name: string) => `${BASE}/mini-characters-1/Models/GLB format/character-${name}.glb`

/**
 * 손님 모형(Kenney Mini Characters, CC0). 보라·남색 옷과 머리가 두드러진 것(여자 a·b·c·d·f, 남자 g)과 경찰복(남자 c)은 뺐다.
 * 모두 같은 뼈대와 동작(idle, walk, pick-up …)을 가진다. 앞이 +z.
 */
export const CUSTOMER_MODELS = [
  people("male-e"),
  people("male-a"),
  people("female-e"),
  people("male-b"),
  people("male-d"),
  people("male-f"),
] as const

/** 손님의 움직임. 시간은 초, 속도는 칸/초. */
export const CUSTOMER = {
  /** 매장 안에 동시에 있는 손님의 최대 수 */
  maxInside: 8,
  /** 밀린 손님을 들여보내는 간격 */
  spawnInterval: 0.4,
  /** 밀린 손님이 이보다 많으면 오래된 것부터 건너뛴다 */
  maxBacklog: 20,
  /** 테스트가 돌 때 걷는 속도와, 구경할 때(테스트가 없을 때) 걷는 속도 */
  speed: 1.35,
  ambientSpeed: 0.75,
  /** 걷는 동작이 이 속도에서 제 빠르기로 돈다(발이 미끄러지지 않게 동작의 빠르기를 속도에 맞춘다) */
  walkAnimSpeed: 1.1,
  /** 방향을 돌리는 빠르기(클수록 빨리 돈다) */
  turnRate: 10,
  /** 문에서 나타나고 사라지는 데 걸리는 시간 */
  fade: 0.3,
  /** 매대 앞에 서 있는 시간(집지 않는 손님): 최소~최대 */
  browse: [1.0, 2.0] as const,
  ambientBrowse: [2.2, 3.8] as const,
  /** 집는 손님: 보고 → 집고 → 잠깐 더 선다 */
  lookBeforePick: 0.7,
  pickHold: 0.6,
  /** 계산대 앞에 서 있는 시간 */
  pay: 0.9,
  /** 같은 길을 걸어도 겹치지 않게 손님마다 옆으로 비키는 폭(±) */
  laneJitter: 0.08,
  /** 서는 곳이 매대 앞에서 손님마다 달라지는 폭(±, x) */
  standJitter: 0.06,
  /** 매대 앞에 선 손님끼리 떨어지는 최소 거리(x) */
  standSpacing: 0.36,
  /** 구경하는 손님의 수와 들어오는 간격(최소~최대) */
  ambientCount: 2,
  ambientInterval: [2.5, 6] as const,
  /** 말풍선(손님의 말): 머리 위 높이, 떠 있는 시간, 한 번에 몇 개까지, 다음 풍선까지의 사이 */
  bubbleHeight: 1.25,
  bubbleTime: 4.2,
  bubbleMax: 2,
  /** 매장의 폭이 이보다 좁으면 풍선을 하나만 띄운다(px) */
  bubbleNarrow: 720,
  bubbleGap: 1.6,
  /** 머리 위의 표시(집은 제품 모양): 높이, 크기, 떠 있는 시간 */
  dotHeight: 1.04,
  dotScale: 0.85,
  dotTime: 1.6,
  dotPop: 0.18,
  /** 표시가 커지고 줄어드는 시간, 도는 빠르기(라디안/초) */
  dotIn: 0.18,
  dotSpin: 1.5,
  /** 동작을 바꿀 때 섞는 시간, 집는 동작(pick-up)이 끝나는 시간 */
  crossFade: 0.15,
  pickAnim: 0.4,
}

/**
 * 손님이 다니는 길목 점 [x, z]. 진열대와 계산대를 피해 이 점들을 잇는다.
 * 문은 왼쪽 벽의 가운데(z=0). 왼쪽 통로(x≈-3.5)는 들어오는 줄과 나가는 줄로 나눈다.
 * 뒤쪽 통로(z=-1.6)는 음료 매대와 가운데 진열대 사이, 가운데 통로(x=0.2)는 진열대와 냉동고 사이,
 * 앞쪽 통로(z=2.55)는 계산대 앞을 지난다.
 */
export const PATH = {
  door: [-4.25, 0] as [number, number],
  inLane: [-3.7, -0.1] as [number, number],
  outLane: [-3.3, 0.15] as [number, number],
  backAisleZ: -1.6,
  /** 왼쪽 통로가 뒤쪽 통로와 만나는 곳의 x(들어올 때, 나갈 때) */
  backInX: -3.7,
  backOutX: -3.3,
  midAisleX: 0.2,
  frontAisleZ: 2.55,
  /** 계산대 앞에 서는 곳(직원을 본다) */
  register: [2.75, 2.45] as [number, number],
  /** 앞쪽 통로에서 왼쪽 통로로 올라가는 곳의 x */
  frontOutX: -3.3,
  /** 매대 앞에 서는 곳: 매대 앞면에서 떨어진 거리. 서는 x의 범위 */
  standGap: 0.3,
  standXRange: [-3.85, 3.85] as const,
}

/** 신제품 자리의 표시가 손님이 집을 때 한 번 튀는 정도 */
export const NEW_SLOT_POP = { duration: 0.45, scale: 0.7, lift: 0.08 }
