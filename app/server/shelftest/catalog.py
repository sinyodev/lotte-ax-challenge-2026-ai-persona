"""공개 매대와 현장 판매 자료를 실행 중에 결합한 제품 목록."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from threading import Lock
from types import MappingProxyType
from typing import Any, Mapping

import onsite

REPO = Path(__file__).resolve().parents[3]
OURS = REPO / "data" / "ours"
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.append(str(SCRIPTS))

BEVERAGES = "음료"
NO_PROMO = "행사 없음"
_CVS = "편의점"

_KIND_CONTAINER = {
    "물": "페트", "탄산수": "페트", "이온": "페트", "차": "페트", "주스": "페트",
    "탄산": "캔", "에너지": "캔", "커피": "캔", "우유·단백": "팩", "소주": "병",
    "맥주": "캔", "막걸리": "페트", "와인": "병",
}
_PACKAGES = {"슬림캔": "캔", "캔": "캔", "can": "캔", "페트": "페트", "pet": "페트",
             "유리병": "병", "병": "병", "팩": "팩", "파우치": "팩", "컵": "컵", "생수": "페트"}
_VOLUME = re.compile(r"(\d+(?:\.\d+)?)\s*(ml|l|리터)", re.IGNORECASE)
_PACK_WORDS = re.compile("|".join(_PACKAGES), re.IGNORECASE)
_TITLE_PACK = re.compile(r"(?<![\w])(?:슬림캔|캔|can|페트|pet|유리병|병|팩|파우치|컵)(?![\w])")
_CLOSED = {"단종", "개발중단"}
# 용량과 용기가 일치할 때만 적용하는 공개 제품명의 별칭.
_PUBLIC_NAMES = {"밀키스": "밀키스오리지널", "델몬트오렌지주스": "델몬트오렌지"}
_CACHE_LOCK = Lock()


def _text(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip().casefold()


def _compact(value: str) -> str:
    return re.sub(r"[^\w]|_", "", _text(value))


def _title(value: str) -> str:
    # 괄호 안의 맛·제로·한정 같은 식별자는 남긴다.
    without_volume = _VOLUME.sub(" ", _text(value))
    return _compact(_TITLE_PACK.sub(" ", without_volume))


def _volume(value: str) -> int:
    m = _VOLUME.search(_text(value))
    if not m:
        return 0
    return int(float(m[1]) * (1 if m[2] == "ml" else 1000))


def _package(value: str) -> str:
    m = _PACK_WORDS.search(_text(value))
    return _PACKAGES[m[0]] if m else ""


def container_of(shape: str, display: str, kind: str) -> str:
    """매대의 모양, 상품명, 종류 순으로 화면용 용기를 정한다."""
    return shape or _package(display) or _KIND_CONTAINER.get(kind, "페트")


def _read_public(name: str) -> list[dict[str, str]]:
    with (OURS / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


@dataclass(frozen=True)
class Product:
    name: str
    row: Mapping[str, str]
    fulfills: Mapping[str, str]
    sku: str | None = None
    added: bool = False

    @property
    def key(self) -> str:
        return self.row["상품명"]

    @property
    def shelf(self) -> str:
        return self.row["매대"]

    @property
    def kind(self) -> str:
        return self.row["종류"]

    @property
    def is_own(self) -> bool:
        return self.row["우리 제품"] == "예"

    @property
    def volume(self) -> int:
        return int(self.row["용량(ml)"] or 0)

    @property
    def pack(self) -> int:
        return int(self.row["묶음 수량"] or 1)

    @property
    def price(self) -> int:
        return int(self.row["가격(원)"])

    @property
    def container(self) -> str:
        if self.added and not self.row["모양"]:
            return "기타"
        return container_of(self.row["모양"].strip(), self.name, self.kind)

    @property
    def promo(self) -> str:
        return self.row["행사"]


@lru_cache(maxsize=2)
def public(*, with_fulfills: bool = True) -> tuple[Product, ...]:
    names = {r["상품명"]: r["손님이 보는 이름"] for r in _read_public("shelf_display_names.csv")}
    needs: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    if with_fulfills:
        for row in _read_public("fulfills.csv"):
            needs[row["매대"], row["상품명"]][row["욕구 번호"]] = row["정도"]
    return tuple(
        Product(names.get(row["상품명"], row["상품명"]), MappingProxyType(row),
                MappingProxyType(needs[row["매대"], row["상품명"]]))
        for row in _read_public("shelf_products.csv")
    )


def _kind(category: str, title: str) -> str:
    kinds = (("커피", "커피"), ("탄산수", "탄산수"), ("탄산", "탄산"), ("주스", "주스"),
             ("과채", "주스"), ("이온", "이온"), ("에너지", "에너지"),
             ("우유", "우유·단백"), ("두유", "우유·단백"), ("차", "차"), ("생수", "물"))
    for text in (category, title):
        for value, kind in kinds:
            if value in text:
                return kind
    return "기타 음료"


def _asset_for(sale: dict, candidates: list[dict], as_of: str) -> dict:
    """코드가 재사용돼도 같은 제품 변형의 자산만 본다."""
    title = _title(sale["name"])
    volume, shape = _volume(sale["name"]), _package(sale["name"])

    def compatible(name: str) -> bool:
        other_volume, other_shape = _volume(name), _package(name)
        return (not volume or not other_volume or volume == other_volume) and (
            not shape or not other_shape or shape == other_shape
        )

    eligible = [
        a for a in candidates
        if _title(a.get("name") or "") == title
        and compatible(a.get("name") or "")
        and (not a.get("brand") or _compact(a["brand"]) == _compact(sale["brand"]))
        and ((a.get("launched") or "")[:7] <= as_of or _compact(a.get("status")) in _CLOSED)
    ]
    return max(eligible, key=lambda a: (
        a.get("launched") or "", _compact(a.get("status")) == "운영", a.get("asset_id") or "",
    ), default={})


def _closed(asset: dict, as_of: str) -> bool:
    status = _compact(asset.get("status"))
    if status in {"개발중단", "아이디어"}:
        return True
    return status == "단종" and (not asset.get("ended") or asset["ended"][:7] <= as_of)


def _identity(public_product: Product) -> tuple[str, int, str, str]:
    p = public_product
    title = _title(p.name)
    return (_PUBLIC_NAMES.get(title, title), p.volume, p.row["모양"] or _package(p.name), p.kind)


def _onsite_identity(sale: dict, kind: str, volume: int, shape: str) -> tuple[str, int, str, str]:
    title = _title(sale["name"])
    return (_PUBLIC_NAMES.get(title, title), volume, shape, kind)


def _latest_promo(rows: list[dict]) -> str:
    """가장 최근 달에서 판매수량이 가장 큰 행사를 쓰고, 동률이면 행사명 순."""
    latest = max(r["month"] for r in rows)
    counts = Counter()
    for r in rows:
        if r["month"] == latest:
            promo = r.get("promo") or NO_PROMO
            counts[NO_PROMO if promo == "없음" else promo] += r["units"]
    return min(counts, key=lambda promo: (-counts[promo], promo))


def _added(sale: dict, kind: str, volume: int, shape: str, price: int, promo: str, *, with_fulfills: bool = True) -> Product:
    name, brand, sku = sale["name"], sale["brand"], sale["sku"]
    sugar = "제로" if "제로" in name else "무가당" if "무가당" in name else ""
    if not sugar and (kind == "탄산" or any(word in name for word in ("마일드", "라떼"))):
        sugar = "가당"
    row = {
        "매대": BEVERAGES, "상품명": f"pos:{sku}:{name}", "제조사": "롯데칠성" if sale["is_own"] else brand,
        "우리 제품": "예" if sale["is_own"] else "아니오", "종류": kind,
        "용량(ml)": volume, "묶음 수량": 1, "가격(원)": price, "행사": promo,
        "당": sugar, "카페인": "많음" if kind == "커피" else "", "탄산": "있음" if kind == "탄산" else "없음",
        "성분": "", "모양": shape, "알려진 브랜드": "예" if sale["is_own"] else "",
    }
    product = Product(name, MappingProxyType({k: str(v) for k, v in row.items()}), MappingProxyType({}), sku, added=True)
    if not with_fulfills:
        return product
    from build_shelves import beverage_rules

    rules = beverage_rules(row)
    # 원자료에 성분이나 용량이 없는 제품에는 그 사실을 전제로 하는 판정을 붙이지 않는다.
    if not sugar:
        for code in ("N05", "N06", "N07"):
            rules[code] = ("못 채움", "")
    if not volume:
        rules["N04"] = ("못 채움", "")
    return replace(product, fulfills=MappingProxyType({code: degree for code, (degree, _) in rules.items()}))


def _combine(pos: list[dict], assets: list[dict], *, with_fulfills: bool = True) -> tuple[Product, ...]:
    products = list(public(with_fulfills=with_fulfills))
    by_sku: dict[str, list[dict]] = defaultdict(list)
    asset_by_sku: dict[str, list[dict]] = defaultdict(list)
    for r in assets:
        asset_by_sku[r["sku"]].append(r)
    for r in pos:
        if (r["channel"] == _CVS and r["sku"] and r["name"] and r["month"]
                and not r.get("after_end") and r.get("units") is not None and r.get("amount") is not None):
            by_sku[r["sku"]].append(r)
    as_of = max((r["month"] or "" for r in pos), default="")
    by_identity: dict[tuple, list[int]] = defaultdict(list)
    for i, p in enumerate(products):
        if p.shelf == BEVERAGES and p.pack == 1:
            by_identity[_identity(p)].append(i)
    matched = set()
    for sku, rows in sorted(by_sku.items()):
        sale = max(rows, key=lambda r: (r["month"], r["units"], r["name"], r["brand"] or ""))
        asset = _asset_for(sale, asset_by_sku[sku], as_of)
        if _closed(asset, as_of):
            continue

        pack, title, category = asset.get("pack") or "", sale["name"], sale["category"] or ""
        kind = _kind(category, title)
        volume = _volume(pack) or _volume(title)
        shape = _package(pack) or _package(title) or _package(category)
        candidates = by_identity.get(_onsite_identity(sale, kind, volume, shape), [])
        brand = _compact(sale["brand"])
        candidates = [i for i in candidates if brand and
                      (_title(products[i].name).startswith(brand) or _compact(products[i].row["제조사"]) == brand)]
        if volume and shape and len(candidates) == 1 and candidates[0] not in matched:
            i = candidates[0]
            row = MappingProxyType({**products[i].row, "우리 제품": "예" if sale["is_own"] else "아니오"})
            products[i] = replace(products[i], row=row, sku=sku)
            matched.add(i)
            continue

        units = sum(r["units"] for r in rows)
        amount = sum(r["amount"] for r in rows)
        # Σ금액/Σ수량의 10원 단위 반올림(정확히 5원이면 올림).
        price = 10 * ((amount + 5 * units) // (10 * units)) if units > 0 else 0
        if price > 0:
            products.append(_added(sale, kind, volume, shape, price, _latest_promo(rows), with_fulfills=with_fulfills))
    return tuple(products)


def _file_stamp(name: str) -> tuple[Path, int, int, int] | None:
    path = onsite.directory() / f"{name}.csv"
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return path.absolute(), stat.st_ino, stat.st_mtime_ns, stat.st_size


def _load(name: str) -> list[dict]:
    try:
        return onsite.load(name)
    except onsite.NoData:
        return []


@lru_cache(maxsize=4)
def _current(pos_stamp: tuple, asset_stamp: tuple | None) -> tuple[Product, ...]:
    return _combine(_load("pos_clean"), _load("assets") if asset_stamp else [])


def current() -> tuple[Product, ...]:
    """파일이 바뀐 경우에만 POS를 다시 읽고 제품 단위로 집계한다."""
    pos_stamp, asset_stamp = _file_stamp("pos_clean"), _file_stamp("assets")
    if pos_stamp is None:
        return public()
    with _CACHE_LOCK:
        return _current(pos_stamp, asset_stamp)


@lru_cache(maxsize=1)
def public_version(round_number: int) -> str:
    h = hashlib.sha256(f"r{round_number}".encode())
    names = ["shelf_products.csv", "shelf_display_names.csv"]
    if round_number == 11:
        names += ["needs.csv", "persona_needs.csv", "occasion_needs.csv", "fulfills.csv"]
    for name in names:
        h.update((OURS / name).read_bytes())
    return h.hexdigest()[:10]


def version(products: tuple[Product, ...], round_number: int) -> str:
    base = public_version(round_number)
    rows = [(p.name, p.sku, dict(p.row), dict(p.fulfills)) for p in products if p.shelf == BEVERAGES and p.sku]
    if not rows:
        return base
    signature = json.dumps([base, rows], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(signature.encode()).hexdigest()[:10]


@lru_cache(maxsize=4)
def _infra(stamp: tuple) -> dict[str, float | None]:
    return next((r for r in _load("infra") if r["channel"] == _CVS), {})


def store_rate(storage: str) -> float | None:
    stamp = _file_stamp("infra")
    if stamp is None:
        return None
    key = "frozen_rate" if storage == "냉동" else "chilled_rate"
    rate = _infra(stamp).get(key)
    return round(rate * 100, 6) if rate is not None and 0 <= rate <= 1 else None
