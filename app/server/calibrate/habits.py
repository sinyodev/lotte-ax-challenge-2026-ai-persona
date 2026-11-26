"""앞 12개월의 판매와 조사 집계로 가상 손님의 구매 습관을 배정한다."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json

import onsite
from shelftest import catalog, explore
import pilot


FIELDS = {"탄산": "buy_soda", "커피": "buy_coffee", "주스": "buy_juice"}
LABELS = {"탄산": "탄산음료", "커피": "커피음료", "주스": "주스"}
COVERAGE = {8: .5, 9: 1., 10: 1., 11: 1.}


@dataclass
class Reference:
    products: dict  # 종류 → [((매대 열쇠, 이름, 브랜드), 판매수량)]
    frequencies: dict  # (연령대, 성별, 종류) → [(월 구매 횟수, 조사 가중치 합)]
    signature: str


def aggregate(sales, respondents, shelf):
    """판매자료가 24개월일 때 앞 절반만 사용하고, 조사 응답자의 종류별 주변분포만 보관한다."""
    sales = [r for r in sales if r["channel"] == "편의점"]
    months = sorted({r["month"] for r in sales})
    # 판매 이력이 짧은 앱에서도 매대를 열 수 있다. 앞·뒤 12개월이 확보되기 전에는 조사 빈도만 쓴다.
    training = set(months[:12]) if len(months) >= 24 else set()
    units, brands = Counter(), defaultdict(Counter)
    for r in sales:
        if r["month"] in training and r["sku"] and r["units"] and r["units"] > 0:
            units[r["sku"]] += r["units"]
            brands[r["sku"]][r["brand"] or ""] += r["units"]
    products = defaultdict(list)
    for sku, key, name, kind in sorted(shelf):
        if kind in FIELDS and units[sku]:
            brand = min(brands[sku], key=lambda b: (-brands[sku][b], b))
            products[kind].append(((key, name, brand), units[sku]))

    cells = defaultdict(Counter)
    for row in respondents:
        age, sex = explore.AGES.get(row["age_band"]), explore.SEXES.get(row["gender"])
        weight = row.get("weight")
        if age and sex and weight is not None and weight > 0:
            for kind, field in FIELDS.items():
                value = row[field]
                if value is not None and value >= 0:
                    cells[age, sex, kind][value] += weight
    frequencies = {cell: sorted(hist.items()) for cell, hist in cells.items()}
    payload = [sorted(products.items()), sorted(frequencies.items())]
    signature = hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()
    return Reference(dict(products), frequencies, signature)


def reference():
    names = ("pos_clean", "survey_respondents")
    stamps = []
    for name in names:
        path = onsite.directory() / onsite.FILENAMES[name]
        try:
            stamp = path.stat()
            stamps.append((str(path), stamp.st_ino, stamp.st_mtime_ns, stamp.st_size))
        except FileNotFoundError:
            stamps.append((str(path),))
    shelf = tuple((p.sku, p.key, p.name, p.kind) for p in catalog.current() if p.sku and p.shelf == catalog.BEVERAGES)
    return _cached(tuple(stamps), shelf)


@lru_cache(maxsize=4)
def _cached(stamps, shelf):
    sources = []
    for name in ("pos_clean", "survey_respondents"):
        try:
            sources.append(onsite.load(name))
        except onsite.NoData:
            sources.append([])
    return aggregate(*sources, shelf)


def _sample(histogram, uuid, field, kind):
    point = pilot.unit(uuid, "purchase-habit-v1", field, kind) * sum(w for _, w in histogram)
    for value, weight in histogram:
        if point < weight:
            return value
        point -= weight
    return histogram[-1][0]


def _kind(favorite):
    if "탄산음료" in favorite:
        return "탄산"
    if "커피" in favorite:
        return "커피"
    if "주스" in favorite or "과즙" in favorite:
        return "주스"
    return None


def _frequency_kinds(ref, uuid, original, monthly):
    available = {k: w for k, w in monthly.items() if w > 0 and k in ref.products}
    if len(available) < len(original):
        return original
    sampled = []
    for slot in range(len(original)):
        kind = _sample(list(available.items()), uuid, "frequency-kind-v1", str(slot))
        sampled.append(kind)
        del available[kind]
    # 두 조건에 공통으로 배정된 종류는 원래 위치에 둔다.
    replacements = iter(k for k in sampled if k not in original)
    return [k if k in sampled else next(replacements) for k in original]


def assign(ref, uuid, age, sex, favorites, coverage, *, variant="original"):
    if variant not in ("original", "frequency-kinds", "paired-lines"):
        raise ValueError("알 수 없는 구매 습관 조건입니다.")
    if pilot.unit(uuid, "purchase-habit-v1", "exposure") >= coverage:
        return {}
    monthly = {}
    for kind in FIELDS:
        histogram = ref.frequencies.get((age, sex, kind))
        if histogram:
            monthly[kind] = _sample(histogram, uuid, "monthly", kind)
    kinds = [k for k in dict.fromkeys(_kind(f) for f in favorites if f) if k in ref.products and monthly.get(k) != 0][:2]
    if variant == "frequency-kinds":
        kinds = _frequency_kinds(ref, uuid, kinds, monthly)
    products = [_sample(ref.products[k], uuid, "product", k) for k in kinds]
    lines = []
    if products:
        lines.append("평소 자주 사는 제품은 " + ", ".join(p[1] for p in products) + "입니다.")
    if monthly:
        lines.append("한 달에 보통 " + ", ".join(f"{LABELS[k]} {v}회" for k, v in monthly.items()) + " 정도 삽니다.")
    if variant == "paired-lines" and products and all(k in monthly for k in kinds):
        names = {k: p[1] for k, p in zip(kinds, products, strict=True)}
        lines = []
        for k, count in monthly.items():
            line = f"{LABELS[k]}는 한 달에 모두 {count}회 정도 삽니다."
            if k in names:
                line += f" 평소 자주 사는 {LABELS[k]}는 {names[k]}입니다."
            lines.append(line)
    return {"lines": lines, "monthly": monthly, "products": [p[0] for p in products], "brands": [p[2] for p in products],
            "has_frequency": bool(monthly)} if lines else {}
