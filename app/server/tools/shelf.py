"""매대에서 비슷한 제품의 가격대를 읽는다. 모델을 부르지 않는다.

자료: data/ours/shelf_products.csv(음료는 CU 정가, 주류는 세븐일레븐 행사와 한국소비자원 가격),
현장 편의점 판매 집계 및 data/ours/fulfills.csv(제품이 니즈를 채우는 정도),
data/clean/fis_pos_2024_cvs.csv, fis_pos_2025_cvs.csv(aT 식품산업통계정보 소매 POS의 편의점 매출).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache

from shelftest import catalog
from tools.consumer import CLEAN, OURS

SHELF_SOURCE = "편의점 공개 매대 및 현장 판매 집계(제공 시)"
CONTAINERS = ["캔", "페트", "병", "팩", "컵", "기타"]

# 기록의 종류 → 가장 가까운 매대의 종류
_RECORD_TO_SHELF = {
    "커피(커피만)": "커피",
    "커피(당·프림 등 첨가)": "커피",
    "탄산음료": "탄산",
    "탄산음료(저칼로리)": "탄산",
    "과일·채소음료": "주스",
    "차": "차",
    "소주": "소주",
    "맥주": "맥주",
    "막걸리": "막걸리",
}


def closest_shelf_kind(record_kind: str | None) -> str | None:
    return _RECORD_TO_SHELF.get(record_kind or "")


@dataclass
class Product:
    shelf: str  # 음료, 주류
    kind: str
    name: str
    container: str
    volume: int
    price: int
    promo: str
    sugar: str = ""  # 당: 제로, 가당, 저당 등
    fizz: str = ""  # 탄산: 있음, 없음, 모름(빈칸)
    ours: bool = False
    sku: str | None = None

    @property
    def is_own(self) -> bool:
        return self.ours

    @property
    def is_zero(self) -> bool:
        return self.sugar == "제로"


def products() -> list[Product]:
    return [Product(p.shelf, p.kind, p.name, p.container, p.volume, p.price, p.promo,
                    p.row["당"], p.row["탄산"], p.is_own, p.sku)
            for p in catalog.current() if p.pack == 1]  # 묶음은 낱개와 비교할 수 없다


def shelf_kinds() -> list[str]:
    seen: list[str] = []
    for p in products():
        if p.kind not in seen:
            seen.append(p.kind)
    return seen


def shelf_of_kind(kind: str) -> str | None:
    for p in products():
        if p.kind == kind:
            return p.shelf
    return None


@dataclass
class Similar:
    kind: str
    container: str | None  # 용기가 같은 것만 모았으면 그 용기, 아니면 None
    volume: int
    low: int
    high: int
    count: int
    names: list[str]

    @property
    def middle(self) -> int:
        """범위의 가운데를 100원 단위로."""
        return int(round((self.low + self.high) / 2 / 100) * 100)


def similar(kind: str | None, container: str | None, volume: int | None) -> Similar | None:
    """비슷한 제품: 같은 매대 종류, 용량 ±30%, 용기가 같은 것. 용기가 같은 것이 없으면 용기를 따지지 않는다.
    용량을 모르면 용량을 따지지 않는다. 하나도 없으면 None."""
    if not kind:
        return None
    same_kind = [p for p in products() if p.kind == kind]

    def near(p: Product) -> bool:
        return not volume or (p.volume and 0.7 * volume <= p.volume <= 1.3 * volume)

    for use_container in (True, False):
        found = [p for p in same_kind if near(p) and (not use_container or p.container == container)]
        if found:
            prices = [p.price for p in found]
            return Similar(kind, container if use_container else None, volume or 0, min(prices), max(prices),
                           len(found), [p.name for p in found])
    return None


# ---------- 경쟁 제품(지시서 12)과 자사 유사 제품(지시서 14): 컨셉 카드의 두 줄 ----------

RIVALS = 2


def _closest(kind: str | None, container: str | None, volume: int | None, zero: bool | None, ours: bool,
             k: int) -> list[Product]:
    """같은 매대 종류에서(자사 제품이면 자사 것만, 아니면 다른 회사 것만) 용량이 가장 가까운 제품 k개.
    제로인지가 같은 제품을 먼저 보고, 그 안에서 비슷한 제품(similar)과 같은 차례로 좁힌다: 용량 ±30%에 용기가 같은 것 → 용량 ±30% → 용기가 같은 것 → 같은 종류.
    (가격의 범위와 비교표가 같은 용량대를 보게 한다.) 용량대가 같은 것들 안에서는 제로인지가 같은 것을 먼저, 그다음 용량이 가까운 것, 매대 자료의 차례."""
    if not kind:
        return []
    same_kind = [p for p in products() if p.kind == kind and p.ours == ours]
    if zero is not None:  # 제로인지가 같은 제품이 있으면 그 안에서만 고른다(실제로 겨루는 제품)
        same_kind = [p for p in same_kind if p.is_zero == zero] or same_kind
    near = [p for p in same_kind if volume and p.volume and 0.7 * volume <= p.volume <= 1.3 * volume]
    pool = ([p for p in near if p.container == container] or near
            or [p for p in same_kind if p.container == container] or same_kind)

    def rank(item: tuple[int, Product]) -> tuple:
        i, p = item
        gap = abs(p.volume - volume) if volume and p.volume else 0
        same_zero = 0 if zero is None or p.is_zero == zero else 1
        # 용량대가 같은 것들 안에서는 제로인지가 같은 것을 먼저 본다
        return (same_zero, gap, i) if near else (gap, same_zero, i)

    return [p for _, p in sorted(enumerate(pool), key=rank)[:k]]


def rivals(kind: str | None, container: str | None, volume: int | None, zero: bool | None = None) -> list[Product]:
    """경쟁 제품: 자사가 아닌 제품에서 둘. 같은 종류가 없으면 빈 목록."""
    return _closest(kind, container, volume, zero, False, RIVALS)


def own_similar(kind: str | None, container: str | None, volume: int | None,
                zero: bool | None = None) -> Product | None:
    """자사 유사 제품: 자사 제품에서 같은 규칙으로 가장 가까운 것 하나. 없으면 None."""
    found = _closest(kind, container, volume, zero, True, 1)
    return found[0] if found else None


def by_name(name: str) -> Product | None:
    """화면용 이름으로 낱개 제품을 찾는다(제안서의 비교표가 매대 자료에서 칸을 다시 읽는다)."""
    return next((p for p in products() if p.name == name), None)


def has_promo(p: Product) -> bool:
    return bool(p.promo) and not p.promo.startswith("행사 없음")


def kind_fizz(kind: str | None) -> bool | None:
    """그 종류가 탄산이 있는 제품인가. 대부분 있으면 True, 모두 없으면 False, 모르면(주류 등) None."""
    marks = [p.fizz for p in products() if p.kind == kind and p.fizz]
    if not kind or not marks:
        return None
    yes = sum(1 for m in marks if m == "있음")
    if yes * 2 > len(marks):
        return True
    return False if yes == 0 else None


_NOT_BRANDS = {"롯데", "컵", "서울", "로제", "하이볼에"}  # 첫 낱말이지만 흔한 말이거나 맛의 이름


def brand_words() -> set[str]:
    """매대 제품 이름의 첫 낱말(칠성사이다, 코카콜라 등). 모델이 쓴 글에 경쟁 제품의 이름이 들었는지 보는 데 쓴다."""
    return {w for p in products() if p.name.split() for w in [p.name.split()[0]] if w not in _NOT_BRANDS}


# ---------- 이 니즈를 채우는 제품이 편의점 매대에 몇 개 ----------


@dataclass
class Need:
    code: str
    name: str
    desc: str
    shelf: str  # 공통, 음료, 주류


@lru_cache(maxsize=1)
def needs() -> dict[str, Need]:
    with (OURS / "needs.csv").open(encoding="utf-8") as f:
        return {r["번호"]: Need(r["번호"], r["욕구"], r["풀어 쓴 설명"], r["범위"]) for r in csv.DictReader(f)}


def find_need(text: str | None, shelf: str = "음료") -> Need | None:
    """글에 든 니즈의 번호나 이름. 그 매대에 쓰는 니즈만."""
    if not text:
        return None
    for n in needs().values():
        if n.shelf not in ("공통", shelf):
            continue
        if n.code == text.strip() or n.name in text:
            return n
    return None


@dataclass
class NeedCount:
    need: Need
    shelf: str
    total: int  # 그 매대의 제품 수(묶음 상품 포함)
    filled: int  # 잘 채우는 제품 수
    ours: int  # 그 가운데 롯데칠성 제품 수
    names: list[str]


def need_count(need: Need, shelf: str) -> NeedCount:
    products = [p for p in catalog.current() if p.shelf == shelf]
    filled = [p for p in products if p.fulfills.get(need.code) == "잘 채움"]
    return NeedCount(need, shelf, len(products), len(filled), sum(p.is_own for p in filled),
                     sorted(p.name for p in filled))


@dataclass
class KindCount:
    kind: str
    shelf: str
    total: int  # 그 매대의 제품 수
    same: int  # 같은 종류의 제품 수
    ours: int


def kind_count(kind: str) -> KindCount | None:
    products = catalog.current()
    rows = [p for p in products if p.kind == kind]
    if not rows:
        return None
    shelf = rows[0].shelf
    total = sum(p.shelf == shelf for p in products)
    return KindCount(kind, shelf, total, len(rows), sum(p.is_own for p in rows))


# ---------- 편의점 매출 ----------

SALES_SOURCE = "aT 식품산업통계정보 소매 POS(마켓링크)"
# 기록의 종류 → 편의점 매출의 품목
_RECORD_TO_FIS = {
    "탄산음료": "탄산음료", "탄산음료(저칼로리)": "탄산음료", "과일·채소음료": "과채음료", "차": "액상차",
    "커피(커피만)": "액상커피", "커피(당·프림 등 첨가)": "액상커피", "소주": "소주", "맥주": "맥주", "막걸리": "탁주",
}
_FIS_NAMES = {"탄산음료": "탄산음료", "과채음료": "과채 음료", "액상차": "차 음료", "액상커피": "커피 음료",
              "탁주": "막걸리", "소주": "소주", "맥주": "맥주", "두유": "두유", "단백질음료": "단백질 음료",
              "우유": "우유", "발효유": "발효유"}


@dataclass
class Sales:
    item: str  # 품목(집계의 이름)
    name: str  # 화면의 이름
    shelf: str
    y24: int  # 편의점 매출(백만원)
    y25: int
    share25: float  # 2025년 편의점 안에서의 비중(%)

    @property
    def change(self) -> float:
        return 100 * (self.y25 - self.y24) / self.y24 if self.y24 else 0.0


def sales(record_kind: str | None) -> Sales | None:
    item = _RECORD_TO_FIS.get(record_kind or "")
    if not item:
        return None

    def read(year: int) -> dict[str, dict[str, str]]:
        with (CLEAN / f"fis_pos_{year}_cvs.csv").open(encoding="utf-8") as f:
            return {r["품목"]: r for r in csv.DictReader(f)}

    a, b = read(2024).get(item), read(2025).get(item)
    if not a or not b:
        return None
    col = "편의점 매출(백만원, 곱한 값)"
    return Sales(item, _FIS_NAMES.get(item, item), b["매대"], int(a[col]), int(b[col]), float(b["편의점 안에서의 비중(%)"]))
