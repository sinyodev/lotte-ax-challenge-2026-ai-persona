"""Luna 11차 개발 패널에서 상황 비중과 욕구 변화 원자료를 독립적으로 비교한다."""

import argparse
import asyncio
from collections import Counter, defaultdict
from contextlib import closing
import hashlib
import json
import os
import sqlite3
from types import SimpleNamespace

import numpy as np

import build_occasions as occasions
import reliability4 as study
import pilot


def occasion_shares(rows):
    group = defaultdict(Counter)
    counts = Counter()
    for row in rows:
        for cell in ((row["sex"], row["band"]), ("전체", row["band"])):
            group[cell][row["occ"]] += row["w"]
            counts[cell] += 1
    codes = [code for shelf, code, *_ in occasions.OCCASIONS if shelf == study.method.SHELF]
    out = {}
    for sex, band in group:
        if sex == "전체":
            continue
        cell = (sex, band) if counts[sex, band] >= occasions.MIN_GROUP else ("전체", band)
        weights = group[cell]
        out[sex, band] = [(c, round(100 * weights[c] / weights.total(), 1)) for c in codes]
    return out


def assign_situation(plan, shares):
    for visit in plan.visits:
        options = shares[visit["성별"], visit["연령대"]]
        point = pilot.unit(visit["uuid"], study.method.SHELF, "shelf-test") * 100
        cumulative = 0.
        for code, weight in options:
            cumulative += weight
            if point <= cumulative:
                break
        visit.update({"상황 번호": code, "상황": plan.plain["occasions"][code]["상황"]})


def stable_shifts(ctx, rows):
    shelf = study.method.SHELF
    full = occasions.scores(rows, shelf)
    halves = [[], []]
    for row in rows:
        half = int(hashlib.md5(str(row["id"]).encode()).hexdigest(), 16) % 2
        halves[half].append(row)
    left, right = (occasions.scores(part, shelf) for part in halves)
    scale = 2 / max(abs(x) for x in full.values())
    kept = defaultdict(dict)
    counts = Counter()
    for (occ, code), value in full.items():
        if ctx["shift_sources"].get(occ, {}).get(code) != "자료":
            continue
        original = ctx["shifts"][occ][code]
        if round(value * scale, 1) != original:
            raise ValueError("원자료로 다시 구한 욕구 변화가 기존 값과 다릅니다.")
        a, b = left.get((occ, code), 0), right.get((occ, code), 0)
        if min(a * value, b * value) <= 0:
            counts["direction_disagrees"] += 1
            continue
        size = round(min(abs(original), abs(a) * scale, abs(b) * scale), 1)
        if size < .3:
            counts["below_threshold"] += 1
            continue
        kept[occ][code] = size if value > 0 else -size
        counts["kept"] += 1
    return dict(kept), dict(counts)


def prepare(control, condition, change):
    plan, _ = study.make_plan("dev-first", 100, 70)
    if plan.visits != control.visits:
        raise ValueError("개발 패널과 방문이 재현되지 않습니다.")
    change(plan)
    changed = 0
    distribution = Counter()
    for original, visit in zip(control.visits, plan.visits, strict=True):
        before_system, before_text, before_order = study.method.prompts(control, original, condition)
        after_system, after_text, after_order = study.method.prompts(plan, visit, condition)
        a, b = json.loads(before_text), json.loads(after_text)
        allowed = {"상황별_욕구_변화"}
        if original["상황 번호"] != visit["상황 번호"]:
            allowed.add("오늘_상황")
        if (before_system != after_system or before_order != after_order or
                any(a[k] != b[k] for k in a.keys() | b.keys() if k not in allowed)):
            raise ValueError("원자료 조건 이외의 입력이 바뀌었습니다.")
        changed += before_text != after_text
        distribution[visit["상황 번호"]] += 1
    return plan, {"changed_prompts": changed, "occasions": dict(sorted(distribution.items()))}


def control_digest(plan, condition):
    digest = hashlib.sha256()
    for visit in plan.visits:
        system, prompt, _ = study.method.prompts(plan, visit, condition)
        digest.update(json.dumps([visit["uuid"], visit["방문"], system, prompt], ensure_ascii=False).encode())
    return digest.hexdigest()


def paired_gap(control, trial_rows, *, training=True):
    """비교 기간의 판매는 고정하고, 같은 성별·연령대 안에서 같은 손님 쌍을 함께 복원추출한다."""
    if control.keys() != trial_rows.keys():
        raise ValueError("비교할 방문 쌍이 다릅니다.")
    ids = sorted(control)
    products = {p.key: p.sku for p in study.catalog.current() if p.shelf == study.method.SHELF and p.sku}
    sales = [r for r in study.onsite.load("pos_clean") if r["channel"] == "편의점"]
    months = sorted({r["month"] for r in sales})
    if len(months) != 24:
        raise ValueError("판매 비교에 24개월 자료가 필요합니다.")
    period = set(months[:12] if training else months[-12:])
    units = Counter()
    for row in sales:
        if row["month"] in period:
            units[row["sku"]] += row["units"]
    skus = sorted(s for s in set(products.values()) if units[s] > 0)
    pos = np.array([units[s] for s in skus], dtype=float)
    pos /= pos.sum()
    rng = np.random.default_rng(35)
    # 첫 행은 실제 표본, 나머지는 층화 복원추출이다. 두 조건 모두 같은 가중치를 받는다.
    weights = np.zeros((5001, len(ids)))
    for cell, weight in zip(study.explore.CELLS, study.explore.population_weights(), strict=True):
        indices = [i for i, k in enumerate(ids) if (control[k]["age"], control[k]["sex"]) == cell]
        n = len(indices)
        weights[0, indices] = weight / n
        weights[1:, indices] = rng.multinomial(n, np.full(n, 1/n), size=5000) * (weight / n)

    gaps = []
    for batch in (control, trial_rows):
        choices = [products.get(batch[k]["product"]) for k in ids]
        matched = np.array([[s == pick for s in skus] for pick in choices], dtype=float)
        totals = weights @ matched
        with np.errstate(divide="ignore", invalid="ignore"):
            share = totals / totals.sum(axis=1, keepdims=True)
        gaps.append(50 * np.abs(share - pos).sum(axis=1))
    delta = gaps[1] - gaps[0]
    for estimate, batch in zip(gaps, (control, trial_rows), strict=True):
        if not np.isclose(estimate[0], study.period_fit(batch.values(), training=training)["gap"]):
            raise ValueError("재표집의 원표본과 기존 판매 오차 계산이 다릅니다.")
    low, high = np.nanquantile(delta[1:], [.025, .975])
    return {"delta_pp": float(delta[0]), "low": float(low), "high": float(high)}


async def trial(label, root, config, plan, condition, audit, workers, baseline):
    folder = root / f"luna-low-r11-{label}"
    with study.records(folder, {**config, "variant": label}) as db:
        batches = []
        for case in ("dev-first", "dev-repeat"):
            batch = await study.collect(db, case, 100, 70, workers, prepared_plan=(plan, condition))
            if len(batch) != 100 or any(r["product"] is None for r in batch.values()):
                raise RuntimeError(f"{label} {case}에 유효 응답 100건이 필요합니다.")
            batches.append(batch)
        first, repeat = batches
        report = {"audit": audit, "fit": study.period_fit(first.values(), training=True),
                  "repeat_fit": study.period_fit(repeat.values(), training=True),
                  "paired_gap_vs_json": paired_gap(baseline, first),
                  "retest": study.reliability.retest(*[{k: r["product"] for k, r in b.items()} for b in batches]),
                  "total_usage": study.cost([r for b in batches for r in b.values()])}
        tmp = folder / "report.tmp"
        tmp.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n")
        tmp.replace(folder / "report.json")
        print(label, report["fit"]["gap"], report["fit"]["rho"], report["retest"]["value"], flush=True)


async def main(workers, dry_run):
    os.environ.update(AX_LLM="codex", AX_MODEL_SHOPPER="gpt-6-luna", AX_EFFORT_SHOPPER="low", AX_SHOPPER_ROUND="11")
    control, condition = study.make_plan("dev-first", 100, 70)
    full = [r for r in occasions.drink_records() if r["shelf"] == study.method.SHELF]
    selected = [r for r in occasions.drink_records(retail_foods=True) if r["shelf"] == study.method.SHELF]
    if occasion_shares(full) != study.method._weights():
        raise ValueError("원자료의 전체 집단으로 기존 상황 비중을 재현하지 못했습니다.")
    shares = occasion_shares(selected)
    shifts, counts = stable_shifts(control.plain, full)
    faces, a = prepare(control, condition, lambda p: assign_situation(p, shares))
    needs, b = prepare(control, condition, lambda p: p.plain.update(shifts=shifts))
    a.update(full_records=len(full), selected_records=len(selected))
    sources = control.plain["shift_sources"]
    beverage_codes = [code for code, row in control.plain["occasions"].items() if row["매대"] == study.method.SHELF]
    b.update(counts, assumptions_removed=sum(source == "가정" for code in beverage_codes
                                             for source in sources.get(code, {}).values()))
    print("상황 비중", a, "욕구 변화", b, flush=True)
    if dry_run:
        return
    root = study.OUT / ".dev"
    fingerprint = control_digest(control, condition)
    config = {**study.settings(SimpleNamespace(people=100, per_cell=70)), "round": 11, "backend": "codex"}
    path = (root / "luna-low-r11" / "responses.sqlite").resolve()
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        if (json.loads(db.execute("SELECT settings FROM manifest").fetchone()[0]) != config or
                db.execute("SELECT digest FROM plans WHERE scenario='dev-first'").fetchone() != (fingerprint,)):
            raise ValueError("기준 11차와 모델 또는 질문이 다릅니다.")
        baseline = study.responses(db, "dev-first")
        if len(baseline) != 100 or any(r["product"] is None for r in baseline.values()):
            raise ValueError("기준 11차 첫 응답 100건이 필요합니다.")
    with occasions.SUBSET.open("rb") as source:
        config.update(source_digest=hashlib.file_digest(source, "sha256").hexdigest(), control_digest=fingerprint)
    await asyncio.gather(trial("food-occasions", root, config, faces, condition, a, (workers + 1) // 2, baseline),
                         trial("stable-shifts", root, config, needs, condition, b, workers // 2, baseline))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true", help="원자료와 질문만 대조한다.")
    args = parser.parse_args()
    if args.workers < 2:
        parser.error("두 조건을 비교하려면 workers가 2 이상이어야 합니다.")
    asyncio.run(main(args.workers, args.dry_run))
