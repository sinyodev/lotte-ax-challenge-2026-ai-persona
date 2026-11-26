"""가상 매출(지시서 28의 B ⑤): 매대 테스트의 선택률을 편의점 POS에 걸어 월별 가상 판매수량과 가상 매출을 낸다.

1. 기준: 매대와 편의점 POS에 함께 있는 같은 종류 제품의 월평균 판매수량의 합을, 컨셉이 없는 매대의 선택률 합으로 나눠
   "선택률 1%p가 월 몇 개"를 구한다. 분모는 매대의 같은 종류 전체(POS에 없는 제품 포함)다. POS에 없는 제품의 판매를
   0으로 본 셈이라 보수적이다. 맞은 제품만으로 나눈 값은 basis에 참고로만 둔다(참가자 결정: 범위에 섞지 않는다).
2. 가상 판매수량 = 컨셉 선택률 × 1번 × 타깃의 인구 비중 × 진열 가능 점포율 × 그 달의 계절 지수.
   가상 매출 = 수량 × 권장 소비자가. 타깃이 사는 몫만 센다.
3. 순증 = 가상 매출 − 자사 제품에서 옮겨 온 수량 × 그 제품의 POS 평균 단가.
4. 범위: 컨셉 선택률의 윌슨 구간만. 기준의 불확실함은 범위에 넣지 않고 가정에 적는다.

모든 값은 코드가 센다. 셀 수 없으면 None을 돌려주고 예외를 내지 않는다. 시장점유율이 아니다.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import onsite
from onsite.concepts import match as known_concept
from scipy.stats import binomtest
from shelftest import catalog, explore, method, result as shelf_result, store

CVS = "편의점"
ALL_KINDS = "전체 음료"
MONTHS = 12
ROOM = "상온"
_LOG = logging.getLogger(__name__)
_NAME_KINDS = (("커피", "커피"), ("라떼", "커피"), ("아메리카노", "커피"), ("주스", "주스"), ("사이다", "탄산"),
               ("콜라", "탄산"), ("소다", "탄산"), ("탄산수", "탄산수"), ("탄산", "탄산"))


# ---------- POS ----------


@dataclass(frozen=True)
class Pos:
    units: dict[str, float]  # 최근 12개월의 편의점 월평균 판매수량(SKU)
    unit_price: dict[str, float]  # 같은 기간의 평균 단가(금액 ÷ 수량)
    months: tuple[str, ...]  # 최근 12개월
    season: dict[str, dict[int, float]] = field(hash=False)  # 종류(또는 전체) → 달 → 지수


def _stamp(name: str) -> tuple:
    info = (onsite.directory() / onsite.FILENAMES[name]).stat()
    return str(onsite.directory()), info.st_ino, info.st_mtime_ns, info.st_size


def kind_of(sale: dict[str, Any]) -> str:
    return catalog._kind(sale.get("category") or "", sale.get("name") or "")


def _season(rows: list[dict[str, Any]], months: list[str]) -> dict[str, dict[int, float]]:
    """12개월 묶음마다 그 달 ÷ 묶음의 월평균을 구해 달마다 평균한다. 온 기간에 팔린 제품만 쓴다
    (중간에 나오거나 사라진 제품이 달의 모양을 바꾸지 않게)."""
    blocks = [months[-MONTHS:]] + ([months[-2 * MONTHS:-MONTHS]] if len(months) >= 2 * MONTHS else [])
    if len(blocks[0]) < MONTHS:
        return {}
    used = {m for b in blocks for m in b}
    sold: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        if r["month"] in used and r["units"] > 0:
            sold[r["sku"]].add(r["month"])
    steady = {sku for sku, at in sold.items() if len(at) == len(used)}
    series: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        if r["sku"] in steady and r["month"] in used:
            for key in (kind_of(r), ALL_KINDS):
                series[key][r["month"]] += r["units"]
    out = {}
    for key, by in series.items():
        found: dict[int, list[float]] = defaultdict(list)
        for block in blocks:
            mean = sum(by[m] for m in block) / len(block)
            for m in block:
                found[int(m[5:7])].append(by[m] / mean)
        out[key] = {m: sum(v) / len(v) for m, v in found.items()}
    return out


@lru_cache(maxsize=4)
def _pos(stamp: tuple) -> Pos | None:
    rows = [r for r in onsite.load("pos_clean")
            if r["channel"] == CVS and r["sku"] and r["month"] and not r.get("after_end")
            and r["units"] is not None and r["amount"] is not None]
    months = sorted({r["month"] for r in rows})
    if not months:
        return None
    recent = months[-MONTHS:]
    units, amount = Counter(), Counter()
    first: dict[str, str] = {}
    for r in rows:
        first[r["sku"]] = min(first.get(r["sku"], r["month"]), r["month"])
        if r["month"] in recent:
            units[r["sku"]] += r["units"]
            amount[r["sku"]] += r["amount"]
    # 이 기간에 나온 제품은 나온 달부터 센다
    spans = {sku: sum(m >= first[sku] for m in recent) for sku in units}
    mean = {sku: n / spans[sku] for sku, n in units.items() if n > 0}
    price = {sku: amount[sku] / n for sku, n in units.items() if n > 0}
    return Pos(mean, price, tuple(recent), _season(rows, months))


def pos() -> Pos | None:
    return _pos(_stamp("pos_clean"))


# ---------- 컨셉이 없는 매대의 선택 ----------


def _price(value: Any) -> int | None:
    """1800, "1,800원" 모두."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value) if value > 0 else None
    m = re.search(r"\d[\d,]*", str(value or ""))
    return int(m[0].replace(",", "")) or None if m else None


def _same_concept(saved: dict[str, Any], concept: dict[str, Any]) -> bool:
    if saved == concept:
        return True
    return (saved.get("id") == concept.get("id") and saved.get("name") == concept.get("name")
            and _price(saved.get("price")) == _price(concept.get("price"))
            and (not concept.get("volume") or saved.get("volume") == concept.get("volume")))


def find_run(concept: dict[str, Any], result: dict[str, Any]) -> dict[str, Any] | None:
    """이 결과를 낸 실행. result에 run_id가 있으면 그것, 없으면 컨셉 스냅숏이 같은 실행 가운데
    다녀간 사람과 고른 사람의 수가 맞는 것(인원의 1할 안. 공통 방문만 남긴 결과도 있다)."""
    run_id = result.get("run_id")
    if run_id:
        return store.load_meta(run_id) if store.valid_id(run_id) else None
    n, picked = int(result["n"]), int(result["picked"])
    best = None
    for meta in store.all_meta():
        if meta.get("mode") == "explore" or not _same_concept(meta.get("concept") or {}, concept):
            continue
        pairs, _ = shelf_result.concept_visits(store.answers(meta["id"]))
        k = sum(c["product"] == meta["line"] for _, c in pairs)
        gap = (abs(len(pairs) - n), abs(k - picked))
        if gap[0] > 0.1 * n or gap[1] > 0.1 * n:
            continue
        key = (gap, meta.get("updated_at") or "")
        if best is None or gap < best[0][0] or (gap == best[0][0] and key[1] > best[0][1]):
            best = (key, meta)
    return best[1] if best else None


def _run_baseline(meta: dict[str, Any] | None) -> list[str]:
    seen = set()
    while meta and meta["id"] not in seen:
        seen.add(meta["id"])
        pairs, _ = shelf_result.concept_visits(store.answers(meta["id"]))
        if found := [b["product"] for b, _ in pairs if b and b.get("product")]:
            return found
        base = meta.get("base_run_id")
        meta = store.load_meta(base) if store.valid_id(base) else None
    return []


def _stored_baseline() -> list[str]:
    """지금 매대 판의 기준 답(store/baselines). 지금 응답 모델의 것을 먼저, 없으면 답이 가장 많은 것."""
    from shelftest.runner import shopper_model

    shelf_v = method.shelf_v()
    rows = list(store.baselines(shelf_v, shopper_model()).values())
    if not rows:
        for path in store.BASE_DIR.glob(f"{shelf_v}-*.jsonl"):
            other = list(store.baselines(shelf_v, path.stem[len(shelf_v) + 1:]).values())
            rows = max(rows, other, key=len)
    return [r["product"] for r in rows if r.get("product")]


# ---------- 기준: 선택률 1%p가 월 몇 개 ----------


@dataclass(frozen=True)
class Basis:
    kind: str
    low: float  # 1%p에 월 몇 개: 매대의 같은 종류 전체의 선택률로 나눈 값. 셈에 쓴다
    high: float  # POS와 맞은 제품의 선택률만으로 나눈 값(참고)
    products: int  # POS와 맞은 제품
    shelf_products: int  # 매대의 같은 종류 전체
    unknown: int  # 매대의 같은 종류 가운데 POS에 없는 제품
    top: float  # 맞은 제품 가운데 가장 많이 팔린 제품의 월평균


def _wilson(k: int, n: int) -> tuple[float, float]:
    ci = binomtest(k, n).proportion_ci(method="wilson")
    return float(ci.low), float(ci.high)


def _basis_of(kind: str, products: list, counts: Counter, sold: dict[str, float], n: int) -> Basis | None:
    matched = [p for p in products if p.sku in sold]
    units = sum(sold[sku] for sku in {p.sku for p in matched})
    picked, every = (sum(counts[p.key] for p in group) for group in (matched, products))
    if not picked or units <= 0:
        return None
    return Basis(kind, units * n / (100 * every), units * n / (100 * picked), len({p.sku for p in matched}), len(products),
                 len(products) - len(matched), max(sold[p.sku] for p in matched))


def basis(kind: str | None, choices: list[str], sales: Pos) -> Basis | None:
    if not choices:
        return None
    counts = Counter(choices)
    shelf = [p for p in catalog.current() if p.shelf == method.SHELF]
    for name, products in ((kind, [p for p in shelf if p.kind == kind]), (ALL_KINDS, shelf)):
        if name and (found := _basis_of(name, products, counts, sales.units, len(choices))):
            return found
    return None


def target_share(target: dict[str, Any] | None) -> float | None:
    """모집단 구성비(population의 age_gender)에서 타깃이 차지하는 비중. 타깃이 없으면 1, 구성비에 없는 타깃이면 None."""
    age, sex = (target or {}).get("age"), (target or {}).get("sex")
    if not age and not sex:
        return 1.0
    weights = explore.population_weights()
    if not weights:
        return None
    share = sum(w for (a, g), w in zip(explore.CELLS, weights, strict=True) if age in (None, "", a) and sex in (None, "", g))
    return share / sum(weights) if share > 0 else None


# ---------- 컨셉의 사실 ----------


def concept_kind(concept: dict[str, Any], meta: dict[str, Any] | None = None) -> str | None:
    """컨셉에 적힌 종류 → 과제의 컨셉 → 그 대화의 노트 → 이름."""
    name = str(concept.get("name") or "")
    kinds = {p.kind for p in catalog.current() if p.shelf == method.SHELF}
    for value in (concept.get("kind"), (known_concept(name) or {}).get("kind"), _chat_kind(meta)):
        if value in kinds:
            return value
        if value and (found := catalog._kind(str(value), "")) in kinds:
            return found
    return next((kind for word, kind in _NAME_KINDS if word in name), None)


def _chat_kind(meta: dict[str, Any] | None) -> str | None:
    if not meta or not meta.get("chat_id"):
        return None
    try:
        import chats

        return ((chats.load(meta["chat_id"]) or {}).get("note") or {}).get("shelf_kind")
    except Exception:  # noqa: BLE001 — 종류를 모르면 이름에서 찾는다
        return None


def _schedule(concept: dict[str, Any]) -> tuple[list[tuple[str, int]], bool]:
    """((YYYY-MM, 달) 목록, 시즌 한정인지). 출시 달이 없으면 다음 해 1월부터로 본다."""
    known = known_concept(str(concept.get("name") or "")) or {}
    season = concept.get("season") if concept.get("season") is not None else known.get("season")
    launch = concept.get("launch") if concept.get("launch") is not None else known.get("launch")
    months = method.sale_months(str(concept.get("name") or ""), season=season or "", launch=launch or "")
    m = re.match(r"(\d{4})-", launch or "")
    year = int(m[1]) if m else int(pos().months[-1][:4]) + 1
    out = []
    for i, month in enumerate(months):
        if i and month < months[i - 1]:
            year += 1
        out.append((f"{year}-{month:02}", month))
    return out, len(months) < 12


def _storage(concept: dict[str, Any], meta: dict[str, Any] | None) -> str:
    return (concept.get("storage") or (meta or {}).get("storage")
            or ((meta or {}).get("placement") or {}).get("storage")
            or (known_concept(str(concept.get("name") or "")) or {}).get("storage") or ROOM)


# ---------- 가상 매출 ----------


def man(value: float) -> str:
    """판매수량을 읽기 쉬운 어림수로."""
    return f"{value / 10000:,.1f}만 개" if value >= 10000 else f"{value:,.0f}개"


def won(value: float) -> str:
    sign, v = ("-" if value < 0 else ""), abs(value)
    if v >= 1e8:
        return f"{sign}{v / 1e8:,.1f}억 원"
    return f"{sign}{v / 1e4:,.0f}만 원" if v >= 1e4 else f"{sign}{v:,.0f}원"


def _names(values: list[str]) -> str:
    return ", ".join(values[:2]) + (f" 외 {len(values) - 2}개" if len(values) > 2 else "")


def _range(values) -> list[int]:
    return [int(round(v)) for v in values]


def compute(concept: dict[str, Any], result: dict[str, Any]) -> tuple[dict[str, Any], list[str]] | None:
    """(estimate의 값, 보고서체로 쓴 가정). 셀 수 없으면 None."""
    if not onsite.available() or not concept or not result:
        return None
    n, picked, price = int(result.get("n") or 0), int(result.get("picked") or 0), _price(concept.get("price"))
    sales = pos()
    if n <= 0 or not 0 <= picked <= n or not price or sales is None:
        return None
    meta = find_run(concept, result)
    choices, own_run = _run_baseline(meta), True
    if not choices:
        choices, own_run = _stored_baseline(), False
    kind = concept_kind(concept, meta)
    base = basis(kind, choices, sales)
    if base is None:
        return None
    storage = _storage(concept, meta)
    store_rate = 1.0
    if storage in ("냉장", "냉동"):
        percent = catalog.store_rate(storage)
        if percent is None:
            return None
        store_rate = percent / 100
    target = (meta or {}).get("target") or result.get("target")
    share = target_share(target)
    if share is None:
        return None
    schedule, seasonal = _schedule(concept)
    index = sales.season.get(base.kind)

    low, high = _wilson(picked, n)
    unit = 100 * share * store_rate  # 선택률 1(=100%)을 %p로, 타깃 몫과 점포율을 건다
    flat = (low * base.low * unit if picked else 0.0, picked / n * base.low * unit, high * base.low * unit)
    by_month = [(label, [u * (index.get(m, 1.0) if index else 1.0) for u in flat]) for label, m in schedule]
    total = [sum(u[i] for _, u in by_month) for i in range(3)]

    # 옮겨 온 자사 제품: 고른 사람이 컨셉 없는 매대에서 집던 것
    came = result.get("from") or {}
    known = picked - int(came.get("pending") or 0)
    by_name = {p.name: p for p in catalog.current() if p.shelf == method.SHELF}
    lost, missing, net = [], [], None
    if known > 0 or not picked:
        loss_per_unit = 0.0
        for row in came.get("own") or []:
            p = by_name.get(row["name"])
            won_each = sales.unit_price.get(p.sku) if p and p.sku else None
            won_each = won_each if won_each is not None else (float(p.price) if p else None)
            if won_each is None or not known:
                missing.append(row["name"])
                continue
            moved = row["count"] / known
            loss_per_unit += moved * won_each
            lost.append({"sku": p.sku, "name": p.name, "amount": int(round(total[1] * moved * won_each))})
        net = {"amount": _range(sorted(u * (price - loss_per_unit) for u in total)), "lost_own": lost}

    value = {
        "monthly": [{"month": label, "units": _range(u), "amount": _range(x * price for x in u)} for label, u in by_month],
        "season_total": {"units": _range(total), "amount": _range(x * price for x in total)},
        "net": net,  # 전에 집던 것을 하나도 모르면 None
        "assumptions": [],
        "basis": {"per_point_units": round(base.low, 1), "per_point_units_high": round(base.high, 1),
                  "category": base.kind, "store_rate": round(store_rate, 4), "target_share": round(share, 4),
                  "products": base.products},
        "backtest": None,
    }
    pairs = _assumptions(base=base, kind=kind, own_run=own_run, sales=sales, storage=storage, store_rate=store_rate,
                         index=index, seasonal=seasonal, schedule=schedule, price=price, picked=picked,
                         pending=int(came.get("pending") or 0), net=net, missing=missing, mid=flat[1],
                         unpriced=[r["name"] for r in lost if not r["sku"]], concept=concept, share=share, target=target)
    value["assumptions"] = [spoken for spoken, _ in pairs]
    return value, [paper for _, paper in pairs]


def _assumptions(*, base: Basis, kind, own_run, sales: Pos, storage, store_rate, index, seasonal, schedule, price, picked,
                 pending, net, missing, mid, unpriced, concept, share, target) -> list[tuple[str, str]]:
    """(해요체, 보고서체)의 짝."""
    out: list[tuple[str, str]] = []

    def add(spoken: str, paper: str) -> None:
        out.append((spoken, paper))

    span = f"{sales.months[0]}~{sales.months[-1]}"
    if base.kind != kind:
        why = f"{kind} 제품" if kind else "같은 종류의 제품"
        add(f"{why}으로는 기준을 셀 수 없어 편의점 음료 전체로 넓혔어요.",
            f"{why}으로 기준 산출 불가, 편의점 음료 전체로 확대")
    name = "음료 전체" if base.kind == ALL_KINDS else base.kind
    add(f"기준은 매대와 편의점 판매 자료에 함께 있는 {name} 제품 {base.products}개예요({span} 편의점 월평균).",
        f"기준: 매대와 편의점 POS에 함께 있는 {name} 제품 {base.products}개({span} 편의점 월평균)")
    add(f"선택률 1%p를 월 {man(base.low)}로 봤어요(매대의 {name} {base.shelf_products}개 전체의 선택률로 나눈 값).",
        f"선택률 1%p당 월 {man(base.low)}(매대의 {name} {base.shelf_products}개 전체 선택률 기준)")
    if base.unknown:
        add(f"판매 자료에 없는 {name} {base.unknown}개의 판매를 몰라 보수적으로 셌어요. 실제로는 더 클 수 있어요.",
            f"POS에 없는 {name} {base.unknown}개의 판매를 알 수 없어 보수적으로 산출. 실제는 더 클 수 있음")
    add("범위에는 선택률의 오차만 넣었어요.", "범위는 선택률의 표본 오차만 반영")
    if not own_run:
        add("이 테스트에 기존 제품의 선택 기록이 없어 같은 매대에서 모아 둔 다른 가상 소비자의 선택을 썼어요.",
            "기존 제품의 선택은 같은 매대에서 수집한 다른 가상 소비자의 기록 사용")
    if (target or {}).get("age") or (target or {}).get("sex"):
        add(f"타깃이 사는 몫만 셌어요(인구의 {100 * share:.1f}%). 타깃 밖의 구매는 넣지 않았어요. "
            "음료를 사는 양은 나이와 성별에 관계없이 같다고 봤어요.",
            f"타깃의 인구 비중 {100 * share:.1f}%만 반영, 타깃 밖의 구매 제외. 나이·성별에 따른 음료 구매량의 차이는 미반영")
    else:
        add("타깃을 좁히지 않아 가상 소비자의 선택률을 편의점 음료 구매 전체에 걸었어요.",
            "타깃 한정 없음, 가상 소비자의 선택률을 편의점 음료 구매 전체에 적용")
    if store_rate < 1 or storage != ROOM:
        add(f"{storage} 진열이 가능한 편의점 {100 * store_rate:.0f}%에만 놓인다고 봤어요.",
            f"{storage} 진열 가능 점포율 {100 * store_rate:.0f}% 반영")
    else:
        add("모든 편의점에 놓인다고 봤어요.", "전 편의점 취급 가정")
    when = f"{schedule[0][0]}~{schedule[-1][0]}"
    if index:
        word = "시즌" if seasonal else "한 해"
        add(f"{word}({when})의 월별 모양은 {name}의 편의점 월별 판매를 따랐어요.",
            f"판매 기간 {when}, 월별 모양은 {name}의 편의점 월별 판매 적용")
    else:
        add(f"{when}의 월별 모양은 낼 수 없어 달마다 같다고 봤어요.", f"판매 기간 {when}, 월별 모양은 자료 부족으로 균등 가정")
    if not (concept.get("launch") or (known_concept(str(concept.get("name") or "")) or {}).get("launch")):
        add("출시 달이 정해지지 않아 다음 해 1월부터로 봤어요.", "출시 시점 미정, 다음 해 1월 출시로 가정")
    add(f"가격은 권장 소비자가 {price:,}원 그대로예요. 1+1 같은 행사와 할인은 넣지 않았어요.",
        f"권장 소비자가 {price:,}원 적용, 행사·할인 미반영")
    if not picked:
        add("고른 가상 소비자가 없어 가운데 값은 0이고, 높은 값은 우연히 0명일 수 있는 만큼만 잡았어요.",
            "선택 0명으로 중앙값 0, 상한은 표본 오차 범위 적용")
    if net is None:
        add("전에 집던 제품의 답이 아직 없어 순증 가상 매출은 내지 않았어요.", "기존 선택 미수집으로 순증 가상 매출 미산출")
    else:
        if pending:
            add(f"고른 사람 가운데 {pending}명은 전에 집던 것을 아직 몰라 나머지의 비율로 봤어요.",
                f"기존 선택 미확인 {pending}명은 나머지의 비율 적용")
        add("순증은 자사 제품에서 옮겨 온 만큼을 그 제품의 편의점 평균 판매 단가로 뺀 값이에요.",
            "순증은 자사 제품에서 옮겨 온 수량 × 그 제품의 편의점 평균 단가를 차감")
        if unpriced:
            names = _names(unpriced)
            add(f"판매 자료에 없는 제품({names})은 매대 가격으로 뺐어요.", f"판매 자료에 없는 제품({names})은 매대 가격으로 차감")
        if missing:
            names = _names(missing)
            add(f"가격을 모르는 제품({names})은 빼지 못했어요.", f"가격을 확인할 수 없는 제품({names})은 차감 제외")
    add("처음 보는 새 제품을 고른 비율이에요. 실제로는 이보다 덜 사는 경향, 광고, 진열 위치, 재구매는 넣지 않았어요. 편의점만 셌어요.",
        "신제품을 처음 본 선택 기준. 의향 대비 실제 구매의 감소, 광고, 진열 위치, 재구매, 편의점 밖의 채널 미반영")
    if mid > base.top:
        add(f"가운데 값이 기준 제품 가운데 실제로 가장 많이 팔린 제품(월 {man(base.top)})의 {mid / base.top:.1f}배예요. "
            "크기보다 안끼리의 차이를 보는 데 쓰세요.",
            f"중앙값이 기준 제품 중 실제 최다 판매 제품(월 {man(base.top)})의 {mid / base.top:.1f}배로, 규모보다 안 사이의 비교에 사용")
    return out


def estimate(concept: dict[str, Any], result: dict[str, Any]) -> dict[str, Any] | None:
    """가상 매출. 모양은 chat/contract-improve.ts의 ImproveSales와 지시서 28. 셀 수 없으면 None."""
    found = report(concept, result)
    return found[0] if found else None


def report(concept: dict[str, Any], result: dict[str, Any]) -> tuple[dict[str, Any], list[str]] | None:
    """estimate의 값과 보고서체 가정."""
    try:
        return compute(concept, result)
    except Exception as err:  # noqa: BLE001 — 결과 화면은 가상 매출이 없어도 나와야 한다
        _LOG.warning("가상 매출을 내지 못했어요: %s", type(err).__name__)
        return None
