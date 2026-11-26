"""매대 선택과 정제한 조사·판매 기록에서 신뢰도 네 지표를 계산한다."""

from collections import Counter, defaultdict
from math import fsum

import numpy as np
from scipy.stats import binomtest, rankdata, spearmanr

from agent.improve_compare import _interval


def retest(first, second, no_purchase="사지 않음"):
    paired = [(a, second[k]) for k, a in first.items()
              if a is not None and second.get(k) is not None]
    n = len(paired)
    same = sum(a == b for a, b in paired)
    both_none = sum(a == b == no_purchase for a, b in paired)
    ci = binomtest(same, n).proportion_ci(method="wilson") if n else (None, None)
    product_ci = binomtest(same - both_none, n).proportion_ci(method="wilson") if n else (None, None)
    return {"id": "retest", "name": "재현율", "value": same / n if n else None,
            "low": ci[0], "high": ci[1], "n": n, "threshold": 0.7, "passed": bool(n and same / n >= 0.7),
            "detail": {"same": same, "same_product": same - both_none, "both_no_purchase": both_none,
                       "same_product_rate": (same - both_none) / n if n else None,
                       "same_product_low": product_ci[0], "same_product_high": product_ci[1]}}


def paired_change(on, off, ids):
    n = len(ids)
    gain = sum(on[k] and not off[k] for k in ids)
    loss = sum(off[k] and not on[k] for k in ids)
    p = binomtest(gain, gain + loss, 0.5).pvalue if gain + loss else 1.0
    low, high = _interval(gain, loss, n) if n else (None, None)
    return {"on": sum(on[k] for k in ids), "off": sum(off[k] for k in ids), "n": n,
            "gain": gain, "loss": loss, "p": p, "difference": (gain-loss)/n if n else None,
            "low": low, "high": high}


def direction(by_price, promo_on, wtp, survey_summary):
    prices = sorted(by_price)
    ids = set.intersection(*[{k for k, v in rows.items() if v is not None}
                             for rows in [*by_price.values(), promo_on]])
    levels = [{"price": p, "picked": sum(by_price[p][k] for k in ids), "n": len(ids)} for p in prices]
    counts = [r["picked"] for r in levels]
    ends = paired_change(by_price[prices[0]], by_price[prices[-1]], ids)
    promo = paired_change(promo_on, by_price[1800], ids)
    monotone = counts == sorted(counts, reverse=True)
    price_ok = monotone and ends["on"] > ends["off"] and ends["p"] < .05
    promo_ok = bool(ids) and promo["on"] > promo["off"] and promo["low"] > 0
    valid_wtp = [v for v in wtp if v is not None]
    survey = [{"price": p, "share": sum(v >= p for v in valid_wtp)/len(valid_wtp) if valid_wtp else None,
               "n": len(valid_wtp)} for p in prices]
    return {"id": "direction", "name": "방향 일치", "passed": bool(price_ok and promo_ok),
            "detail": {"price": levels, "price_endpoints": ends, "monotone": monotone,
                       "price_passed": price_ok, "promo": promo, "promo_passed": promo_ok,
                       "survey_wtp": survey, "survey_wtp_summary": survey_summary}}


def shares(amounts):
    total = fsum(amounts.values())
    return {k: v / total for k, v in amounts.items()} if total > 0 else {}


def correlation(x, y):
    if len(x) < 2 or len(set(x)) < 2 or len(set(y)) < 2:
        return None
    return float(spearmanr(x, y).statistic)


def compare_shares(first, second, keys):
    keys = sorted(keys)
    a, b = (shares({k: series.get(k, 0) for k in keys}) for series in (first, second))
    if not a or not b:
        return {"rho": None, "gap": None}
    return {"rho": correlation(list(a.values()), list(b.values())),
            "gap": 50 * fsum(abs(a[k] - b[k]) for k in keys)}


def adjust_kind_totals(virtual, training, reference, kinds):
    observed, simulated = Counter(), Counter()
    for sku, kind in kinds.items():
        observed[kind] += training[sku]
        simulated[kind] += virtual[sku]
    missing = sorted(k for k in observed if observed[k] > 0 and not simulated[k])
    if missing:
        return {"rho": None, "gap": None}, missing
    adjusted = {sku: virtual[sku] * observed[k] / simulated[k] if simulated[k] else 0 for sku, k in kinds.items()}
    return compare_shares(adjusted, reference, kinds), missing


def category_fit(choices, weights, products, period_sales, *, dev=False):
    """호출자가 지정한 기간만 쓴다. products는 내부명 → (SKU, 종류, 행사 여부)다."""
    valid = [r for r in choices if r["product"] is not None]
    totals = Counter((r["age"], r["sex"]) for r in valid)
    if not weights or any(not totals[k] for k in weights):
        raise ValueError("여덟 칸의 관측값과 모집단 비중이 필요합니다.")
    actual, actual_kinds = Counter(), Counter()
    promoted_units = 0
    for sale in period_sales:
        actual[sale["sku"]] += sale["units"]
        actual_kinds[sale["kind"]] += sale["units"]
        if sale["promoted"]:
            promoted_units += sale["units"]
    matched = {sku: kind for sku, kind, _ in products.values() if sku and actual[sku] > 0}
    virtual, virtual_kinds, matched_kinds, actual_matched = (Counter() for _ in range(4))
    picks = promoted_picks = matched_picks = 0
    for r in valid:
        if r["product"] not in products:
            continue
        sku, kind, promoted = products[r["product"]]
        cell = (r["age"], r["sex"])
        w = weights[cell] / totals[cell]
        picks += 1
        promoted_picks += int(promoted)
        virtual_kinds[kind] += w
        if sku in matched:
            matched_picks += 1
            virtual[sku] += w
            matched_kinds[kind] += w
    for sku, kind in matched.items():
        actual_matched[kind] += actual[sku]
    result = {**compare_shares(virtual, actual, matched), "n_products": len(matched),
            "n": len(valid), "bought": picks, "matched_picks": matched_picks,
            "kinds_all": shares(virtual_kinds), "kinds_matched": shares(matched_kinds),
            "pos_all": shares(actual_kinds), "pos_matched": shares(actual_matched),
            "promoted_picks": promoted_picks,
            "promoted_units_share": promoted_units/sum(actual.values()) if sum(actual.values()) > 0 else None}
    if dev:
        # 개발 기간 안에서 종류별 총량을 맞추면 남는 제품 단위 차이다.
        result["dev_kind_adjusted"], result["unseen_kinds"] = adjust_kind_totals(virtual, actual, actual, matched)
    if any("visit_month" in r for r in valid):
        result["seasonality"] = seasonality(valid, weights, totals, products, period_sales, matched)
    return result


def seasonality(rows, weights, cell_n, products, sales, matched):
    """가중 가상 구매와 실제 낱개 판매에서 공통 제품의 월별 탄산 비중을 비교한다."""
    n = Counter()
    virtual, actual = defaultdict(Counter), defaultdict(Counter)
    for r in rows:
        month = r.get("visit_month")
        product = products.get(r["product"])
        if not month:
            continue
        n[month] += 1
        if product and product[0] in matched:
            cell = (r["age"], r["sex"])
            virtual[month][product[1]] += weights[cell] / cell_n[cell]
    for r in sales:
        if r["sku"] in matched:
            actual[r["month"]][matched[r["sku"]]] += r["units"]

    def proportion(series, months):
        total = sum(series[m].total() for m in months)
        return sum(series[m]["탄산"] for m in months)/total if total else None

    def contrast(series):
        summer = proportion(series, (6, 7, 8))
        winter = proportion(series, (12, 1, 2))
        return None if summer is None or winter is None else summer - winter

    months = [{"month": m, "n": n[m], "virtual": proportion(virtual, [m]),
               "pos": proportion(actual, [m])} for m in range(1, 13)]
    paired = [m for m in months if m["virtual"] is not None and m["pos"] is not None]
    vd, pd = contrast(virtual), contrast(actual)
    return {"months": months, "months_compared": len(paired),
            "rho": correlation([m["virtual"] for m in paired], [m["pos"] for m in paired]),
            "virtual_summer_minus_winter": vd, "pos_summer_minus_winter": pd,
            "same_direction": None if vd is None or pd is None else bool(vd * pd > 0)}


def sales_rank(choices, weights, catalog, sales):
    """catalog은 매대 내부 제품명 → (매칭된 POS SKU, 종류), weights는 모집단 칸별 비중."""
    rows = [r for r in sales if r["channel"] == "편의점"]
    months = sorted({r["month"] for r in rows})
    if len(months) != 24:
        raise ValueError("앞·뒤 12개월의 편의점 판매가 필요합니다.")
    first, last = Counter(), Counter()
    for r in rows:
        (first if r["month"] <= months[11] else last)[r["sku"]] += r["units"]
    common = {sku for sku in first if first[sku] > 0 and last[sku] > 0}
    floor = compare_shares(first, last, first.keys() | last.keys())
    floor["rho"] = compare_shares(first, last, common)["rho"]
    floor.update(n_products=len(common), gap_products=len(first.keys() | last.keys()))

    valid = [r for r in choices if r["product"] is not None]
    totals = Counter((r["age"], r["sex"]) for r in valid)
    if not weights or any(totals[cell] == 0 for cell in weights):
        raise ValueError("모집단 가중치 또는 칸별 판매 비교 표본이 비었습니다.")
    kinds = {sku: kind for sku, kind in catalog.values() if last[sku] > 0}
    virtual = Counter()
    for r in valid:
        product = catalog.get(r["product"])
        if product and product[0] in kinds:
            cell = (r["age"], r["sex"])
            virtual[product[0]] += weights[cell] / totals[cell]
    base = compare_shares(virtual, last, kinds)

    # 앞 12개월로 종류별 총량만 맞춘다. 같은 종류 안의 제품 간 비율은 보존한다.
    calibrated, missing = adjust_kind_totals(virtual, first, last, kinds)
    ok = base["rho"] is not None and base["rho"] >= .5 and base["gap"] <= 20
    return {"id": "sales_rank", "name": "판매 순위 일치", "value": base["rho"], "gap": base["gap"],
            "n_products": len(kinds), "threshold": {"rho": .5, "gap": 20}, "passed": ok,
            "detail": {"calibrated": calibrated, "floor": floor, "unseen_kinds": missing,
                       "matched_history": compare_shares(first, last, kinds),
                       "n": len(valid), "matched_picks": sum(r["product"] in catalog and
                           catalog[r["product"]][0] in kinds for r in valid),
                       "train_months": [months[0], months[11]], "test_months": [months[12], months[-1]]}}


def rank_interval(x, y, cell_sizes):
    """고정된 여덟 칸 각각에서 가상 응답을 복원추출한다. 조사 TOP2는 관측값에 고정한다."""
    rho = correlation(x, y)
    if rho is None:
        return None, None, None
    sizes = np.asarray(cell_sizes)
    draws = np.random.default_rng(35).binomial(sizes, x, size=(10000, len(x))) / sizes
    a, b = rankdata(draws, axis=1), rankdata(y)
    a -= a.mean(axis=1, keepdims=True)
    b -= b.mean()
    denom = np.linalg.norm(a, axis=1) * np.linalg.norm(b)
    valid = denom > 0
    if not np.any(valid):
        return rho, None, None
    correlations = np.sum(a[valid] * b, axis=1) / denom[valid]
    low, high = np.quantile(correlations, [.025, .975])
    return rho, float(np.clip(low, -1, 1)), float(np.clip(high, -1, 1))


def survey_match(choices, segments, overall, weights):
    concepts, virtual = [], {}
    for name, rows in choices.items():
        cells = defaultdict(list)
        for r in rows:
            if r["selected"] is not None:
                cells[(r["age"], r["sex"])].append(r["selected"])
        rates = {k: sum(v)/len(v) for k, v in cells.items()}
        keys = [k for k in weights if k in rates and segments[name].get(k) is not None]
        rho, low, high = rank_interval([rates[k] for k in keys], [segments[name][k] for k in keys],
                                       [len(cells[k]) for k in keys])
        virtual[name] = (sum(weights[k]*rates[k] for k in weights)/sum(weights.values())
                         if weights and all(k in rates for k in weights) else None)
        comparisons = [{"age": k[0], "sex": k[1], "picked": sum(cells[k]), "n": len(cells[k]),
                        "rate": rates[k], "survey_top2": segments[name][k]} for k in keys]
        concepts.append({"name": name, "rho": rho, "low": low, "high": high, "cells": len(keys),
                         "cell_rates": comparisons, "rate": virtual[name], "survey_top2": overall[name]})
    def ordering(scores):
        return sorted(scores, key=scores.get, reverse=True) if None not in scores.values() else []
    observed, predicted = ordering(overall), ordering(virtual)
    # 둘 중 어느 쪽이든 동률이면 엄격한 세 컨셉의 순서를 확인할 수 없다.
    same = len(choices) == len(set(virtual.values())) == len(set(overall.values())) == 3 and bool(predicted) and predicted == observed
    positive = sum(c["cells"] == len(weights) and c["rho"] is not None and c["rho"] > 0 for c in concepts)
    return {"id": "survey_match", "name": "조사 일치", "passed": positive >= 2 and same,
            "detail": {"concepts": concepts, "positive": positive,
                       "order": {"survey": observed, "virtual": predicted, "same": same}}}
