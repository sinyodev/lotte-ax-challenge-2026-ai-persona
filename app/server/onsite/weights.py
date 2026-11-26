"""연령대×성별과 권역의 구성비에 맞추는 가중치."""

import numpy as np
import pandas as pd

DIMENSIONS = {"age_gender": ("age_band", "gender"), "region": ("region",)}
WEIGHT_CAP = 5.0
RAKE_TOLERANCE = 1e-8
RAKE_ITERATIONS = 200


def _scale_with_cap(values: np.ndarray, total: float, caps: np.ndarray) -> np.ndarray:
    result = np.zeros(len(values))
    # 한 차례에 0이 된 가중치도 다음 차례의 구간 합계에 필요하면 다시 올릴 수 있다.
    values = np.maximum(values, np.finfo(float).eps)
    remaining = np.arange(len(values))
    while len(remaining):
        proportion = values[remaining] / values[remaining].sum()
        proposed = proportion * total
        overflow = proposed > caps[remaining]
        if not overflow.any():
            result[remaining] = proposed
            break
        capped = remaining[overflow]
        result[capped] = caps[capped]
        total = max(0.0, total - caps[capped].sum())
        remaining = remaining[~overflow]
    return result


def _adjustment_groups(groups: dict, targets: dict) -> list[tuple[np.ndarray, float]]:
    # 모집단에 값이 없는 표본 구간은 표본의 몫을 유지한다.
    known = [(rows, targets[key]) for key, rows in groups.items() if key in targets]
    unknown = [(rows, float(len(rows))) for key, rows in groups.items() if key not in targets]
    if not known or not any(share for _, share in known):
        return []
    counts = np.array([len(rows) for rows, _ in known])
    # 빈 구간의 목표 몫과 상한을 넘는 몫은 표본이 있는 구간에 다시 나눈다.
    totals = _scale_with_cap(
        np.array([share for _, share in known]), float(counts.sum()), WEIGHT_CAP * counts
    )
    return unknown + [(rows, total) for (rows, _), total in zip(known, totals)]


def rake_weights(respondents: pd.DataFrame, population: pd.DataFrame) -> tuple[np.ndarray, str]:
    """상한과 평균 1을 함께 유지하고, 두 원래 목표와의 차이를 남긴다."""
    dimensions = []
    adjustments = []
    for name, columns in DIMENSIONS.items():
        groups = respondents.groupby(
            columns[0] if len(columns) == 1 else list(columns), dropna=False
        ).indices
        target = population.loc[population["dimension"].eq(name)]
        targets = target.set_index(list(columns))["share"].to_dict()
        dimensions.append((name, groups, targets))
        adjustments.append(_adjustment_groups(groups, targets))

    weights = np.ones(len(respondents))
    for _ in range(RAKE_ITERATIONS):
        previous = weights.copy()
        for groups in adjustments:
            for rows, total in groups:
                weights[rows] = _scale_with_cap(
                    weights[rows], total, np.full(len(rows), WEIGHT_CAP)
                )
        if np.allclose(weights, previous, rtol=0, atol=RAKE_TOLERANCE):
            break

    detail = " ".join(_dimension_detail(name, groups, targets, weights)
                      for name, groups, targets in dimensions)
    return weights, detail


def _dimension_detail(name: str, groups: dict, targets: dict, weights: np.ndarray) -> str:
    label = "연령대×성별" if name == "age_gender" else "권역"
    if not targets:
        return f"{label}은 비교할 모집단 구성비가 없어요."

    comparisons = []
    errors = []
    total_weight = weights.sum()
    for key, target in targets.items():
        rows = groups.get(key, np.array([], dtype=int))
        category = " ".join(key) if isinstance(key, tuple) else key
        if total_weight:
            share = float(weights[rows].sum() / total_weight)
            errors.append(abs(share - target))
            comparisons.append(f"{category} {len(rows) / len(weights):.1%} → {share:.1%}"
                               f" (목표 {target:.1%})")
        else:
            comparisons.append(f"{category} 목표 {target:.1%}")
    if not total_weight:
        return f"{label}은 남은 응답이 없어요. {', '.join(comparisons)}."

    unmatched = [rows for key, rows in groups.items() if key not in targets]
    if unmatched:
        share = sum(weights[rows].sum() for rows in unmatched) / total_weight
        comparisons.append(f"그 밖의 구간 {sum(map(len, unmatched)) / len(weights):.1%} → {share:.1%}"
                           " (목표 없음)")
    return (f"{label}의 보정 전 → 후 응답 비중은 {', '.join(comparisons)}예요. "
            f"목표가 있는 구간의 최대 차이는 {max(errors) * 100:.2f}%p예요.")
