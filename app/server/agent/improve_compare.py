"""같은 가상 소비자의 원래 안·바꾼 안 선택을 짝지어 집계한다."""

from __future__ import annotations

from collections import Counter
from typing import Any

from shelftest import method, result, store

VisitKey = tuple[str, str, str]
GROUPS = ("자사 제품", "경쟁 제품", "사지 않음", "기록에 없는 제품")


def _choices(rows: list[dict[str, Any]]) -> dict[VisitKey, str]:
    pairs, _ = result.concept_visits(rows)
    return {(row["uuid"], row["visit"], row["occasion"]): row["product"] for _, row in pairs
            if all(row.get(k) for k in ("uuid", "visit", "occasion", "product"))}


def _group(choice: str, shelf: dict[str, bool]) -> str:
    if choice == method.NO_PURCHASE:
        return GROUPS[2]
    if choice not in shelf:
        return GROUPS[3]
    return GROUPS[0] if shelf[choice] else GROUPS[1]


def _interval(gained: int, lost: int, n: int) -> tuple[float, float]:
    """두 전환 비율의 동시 95% 이상 신뢰구간에서 차이의 범위를 구한다."""
    from scipy.stats import beta

    def exact(k: int) -> tuple[float, float]:
        # 각 비율의 Clopper–Pearson 구간에 Bonferroni 보정(양쪽 각 1.25%).
        low = beta.ppf(0.0125, k, n - k + 1) if k else 0.0
        high = beta.ppf(0.9875, k + 1, n - k) if k < n else 1.0
        return float(low), float(high)

    gl, gh = exact(gained)
    ll, lh = exact(lost)
    return gl - lh, gh - ll


def paired(original: dict[str, Any], changed: dict[str, Any],
           before_rows: list[dict[str, Any]], after_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    before, after = _choices(before_rows), _choices(after_rows)
    keys = before.keys() & after.keys()
    n = len(keys)
    if not n:
        return None
    old_line, new_line = original["line"], changed["line"]
    catalog = original.get("shelf_products")
    if catalog is None:
        # 이전 기록에는 공개 매대의 스냅샷이 없다.
        from shelftest.catalog import public

        catalog = [(p.key, p.name, p.is_own) for p in public() if p.shelf == method.SHELF]
    shelf = {key: own for key, _, own in catalog}
    both = neither = 0
    gained_groups: Counter[str] = Counter()
    lost_groups: Counter[str] = Counter()
    for key in keys:
        old, new = before[key], after[key]
        if old == old_line:
            if new == new_line:
                both += 1
            else:
                lost_groups[_group(new, shelf)] += 1
        elif new == new_line:
            gained_groups[_group(old, shelf)] += 1
        else:
            neither += 1
    gained, lost = sum(gained_groups.values()), sum(lost_groups.values())
    low, high = _interval(gained, lost, n)
    low_pp, high_pp = round(100 * low, 1), round(100 * high, 1)

    def groups(counts: Counter[str]) -> list[dict[str, Any]]:
        return [{"label": label, "count": counts[label]} for label in GROUPS if counts[label]]

    return {
        "n": n, "both": both, "gained": gained, "lost": lost, "neither": neither,
        "original_rate": round(100 * (both + lost) / n, 1), "changed_rate": round(100 * (both + gained) / n, 1),
        "delta_pp": round(100 * (gained - lost) / n, 1), "low_pp": low_pp, "high_pp": high_pp,
        "verdict": "more" if low_pp > 0 else "less" if high_pp < 0 else "unclear",
        "gained_groups": groups(gained_groups), "lost_groups": groups(lost_groups),
    }


def same_test(original: dict[str, Any], changed: dict[str, Any]) -> bool:
    """같은 대화·컨셉·매대·응답기로 돌린 변형인지 확인한다(원래 실행 ID가 없는 옛 기록도 지원)."""
    return (
        all(original.get(k) == changed.get(k)
            for k in ("chat_id", "concept_id", "shelf_v", "model", "target", "occasion_code"))
        and changed.get("base_run_id") in (None, original["id"])
        and original.get("concept_prompt_version", 0) == changed.get("concept_prompt_version", 0)
        and original.get("choice_method") == changed.get("choice_method")
        and (not original.get("shopper_adapter") or original.get("shopper_adapter") == changed.get("shopper_adapter"))
    )


def for_runs(base_run: str, changed_run: str) -> dict[str, Any] | None:
    if base_run == changed_run:
        return None
    original, changed = store.load_meta(base_run), store.load_meta(changed_run)
    # 멈춘 변경안도 그때까지 답한 같은 가상 소비자끼리 견준다(11-25: 카드의 "멈추고 지금까지의 결과 보기")
    if not original or not changed or original["status"] != "done" or changed["status"] not in ("done", "stopped"):
        return None
    if not same_test(original, changed):
        return None
    return paired(original, changed, store.answers(base_run), store.answers(changed_run))


def price_curve(base_run: str, current_price: int, points: list[tuple[int, str | None]]) -> list[dict[str, Any]]:
    """세 가격의 완료 응답에서 공통 방문만 남겨 분모를 맞춘다."""
    runs = sorted([*points, (current_price, base_run)], key=lambda point: point[0])
    curve = [{"price": price, "rate": None, "n": 0, "picked": 0,
              **({"run_id": run_id} if run_id else {})} for price, run_id in runs]
    metas = [store.load_meta(run_id) if run_id else None for _, run_id in runs]
    if any(not meta or meta.get("status") != "done" for meta in metas):
        return curve
    original = next(meta for meta in metas if meta["id"] == base_run)
    if any(not same_test(original, meta) for meta in metas):
        return curve
    rows = [store.answers(meta["id"]) for meta in metas]
    choices = [_choices(records) for records in rows]
    common = set.intersection(*(set(answers) for answers in choices))
    if not common:
        return curve
    n = len(common)
    try:
        from calibrate import sales
    except ImportError as err:
        if err.name not in {"calibrate", "calibrate.sales"}:
            raise
        sales = None
    for point, meta, answers, records in zip(curve, metas, choices, rows, strict=True):
        picked = sum(answers[key] == meta["line"] for key in common)
        point.update(rate=round(100 * picked / n, 1), n=n, picked=picked)
        if sales is not None:
            shared = [row for row in records if (row.get("uuid"), row.get("visit"), row.get("occasion")) in common]
            summary = result.summarize(meta, shared, {})
            if projection := sales.estimate(meta["concept"], summary):
                point["sales"] = projection
    return curve
