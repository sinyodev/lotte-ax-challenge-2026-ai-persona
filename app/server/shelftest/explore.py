"""탐색의 층화 표본과 가중 선택률."""

from __future__ import annotations

import math
from collections import Counter
from itertools import zip_longest
from typing import Any

import onsite
from shelftest import method, result
from tools.consumer import Group, default_label
from tools.occasion_display import show as show_occasion

AGES = {"19~29세": "19-29", "30~39세": "30-39", "40~49세": "40-49", "50~59세": "50-59"}
SEXES = {"여성": "여자", "남성": "남자"}
CELLS = tuple((age, sex) for age in AGES.values() for sex in SEXES.values())


def participants(per_cell: int) -> list[method.Person]:
    """기존 손님 순서대로 칸을 채우고, 각 칸의 첫 손님부터 번갈아 내보낸다."""
    groups = [method.people(age, sex)[:per_cell] for age, sex in CELLS]
    return [p for round_people in zip_longest(*groups) for p in round_people if p is not None]


def population_weights() -> list[float] | None:
    try:
        rows = onsite.load("population")
    except (onsite.NoData, KeyError, ValueError):
        return None
    weights = {}
    for row in rows:
        if row.get("dimension") != "age_gender":
            continue
        cell = (AGES.get(row.get("age_band")), SEXES.get(row.get("gender")))
        if cell not in CELLS:
            continue
        share = row.get("share")
        if cell in weights or not isinstance(share, (int, float)) or not math.isfinite(share) or share < 0:
            return None
        weights[cell] = share
    if len(weights) != len(CELLS) or sum(weights.values()) <= 0:
        return None
    return [weights[cell] for cell in CELLS]


def _rate(picked: int, n: int) -> float | None:
    return round(100 * picked / n, 1) if n else None


SEX_GROUPS = (("여자", "여성"), ("남자", "남성"))
AGE_GROUPS = tuple((code, label) for label, code in AGES.items())
MIN_AXIS_N = 30
Z_CRIT = 1.96  # 두 비율의 차이 검정, 양측 5%
CHI2_CRIT_DF3 = 7.815  # 동질성 카이제곱 검정, 자유도 3, 5%


def _two_prop_z(groups: list[dict]) -> float | None:
    (n1, k1), (n2, k2) = ((g["n"], g["picked"]) for g in groups)
    pooled = (k1 + k2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    return (k1 / n1 - k2 / n2) / se if se else 0.0


def _chi2(groups: list[dict]) -> float:
    n, k = sum(g["n"] for g in groups), sum(g["picked"] for g in groups)
    p = k / n
    if p in (0, 1):
        return 0.0
    return sum((g["picked"] - g["n"] * p) ** 2 / (g["n"] * p * (1 - p)) for g in groups)


def _axis(name: str, defs: tuple, index: int, answers: Counter, picked: Counter, done: bool) -> dict[str, Any]:
    groups = []
    for code, label in defs:
        n = sum(v for cell, v in answers.items() if cell[index] == code)
        k = sum(v for cell, v in picked.items() if cell[index] == code)
        groups.append({"key": code, "label": label, "n": n, "picked": k, "rate": _rate(k, n)})
    clear, stat = None, None
    if done and all(g["n"] >= MIN_AXIS_N for g in groups):
        if len(groups) == 2:
            stat = _two_prop_z(groups)
            clear = abs(stat) >= Z_CRIT
        else:
            stat = _chi2(groups)
            clear = stat >= CHI2_CRIT_DF3
        stat = round(stat, 2)
    return {"axis": name, "groups": groups, "clear": clear, "stat": stat,
            "test": "two_proportion_z" if len(groups) == 2 else "chi_square_df3"}


def axes(meta: dict[str, Any], answers: Counter, picked: Counter) -> dict[str, Any]:
    """성별(두 그룹)과 연령대(네 그룹)로 묶어 뚜렷하게 갈리는지 코드로 판정한다."""
    done = meta.get("status") in ("done", "stopped")  # 멈춘 탐색도 지금까지의 답으로 판정한다(그룹마다 MIN_AXIS_N 이상일 때만)
    return {"sex": _axis("sex", SEX_GROUPS, 1, answers, picked, done),
            "age": _axis("age", AGE_GROUPS, 0, answers, picked, done)}


def summarize(meta: dict[str, Any], pairs: list[tuple[dict | None, dict]]) -> dict[str, Any]:
    planned = {p["visit"]: (p["age"], p["sex"]) for p in meta["participants"]}
    totals = Counter(planned.values())
    answers: Counter = Counter()
    picked: Counter = Counter()
    by_occasion: dict[str, list[int]] = {}
    for _, row in pairs:
        cell = planned.get(row["visit"])
        if cell is None:
            continue
        chose = row["product"] == meta["line"]
        answers[cell] += 1
        picked[cell] += chose
        occ = by_occasion.setdefault(row["occasion"], [0, 0])
        occ[0] += 1
        occ[1] += chose

    weights = meta.get("population_weights")
    cells = []
    included, overall = 0.0, 0.0
    for i, (age, sex) in enumerate(CELLS):
        key = (age, sex)
        n, k = answers[key], picked[key]
        low, high = result.wilson(k, n) if n else (None, None)
        cells.append({"age": age, "sex": sex, "label": default_label(Group(age=age, sex=sex)),
                      "total": totals[key], "n": n, "picked": k, "rate": _rate(k, n), "low": low, "high": high})
        if n:
            weight = weights[i] if weights is not None else 1
            included += weight
            overall += weight * k / n

    measured = sorted((c for c in cells if c["n"]), key=lambda c: c["picked"] / c["n"], reverse=True)
    suggested, overlap = None, False
    if measured:
        first, *others = measured
        overlap = any(first["low"] <= other["high"] for other in others)
        if meta["status"] in ("done", "stopped") and len(measured) == len(CELLS) and first["picked"] and not overlap:
            suggested = {key: first[key] for key in ("age", "sex", "label")}
    names = method.occasions()
    occasions = [{"occasion": show_occasion(names.get(code, {}).get("상황", code)), "n": n, "picked": k, "rate": _rate(k, n)}
                 for code, (n, k) in sorted(by_occasion.items(), key=lambda kv: (-kv[1][0], kv[0]))]
    return {"cells": cells, "occasions": occasions,
            "overall_rate": round(100 * overall / included, 1) if included else None,
            "weighting": "population" if weights is not None else "equal",
            "suggested": suggested, "overlap": overlap, "axes": axes(meta, answers, picked)}
