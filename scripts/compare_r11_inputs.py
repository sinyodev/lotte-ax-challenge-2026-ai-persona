"""11차 Luna low에서 구매 습관·성분 결측·판매 기간을 독립적으로 시험한다."""

import argparse
import asyncio
from collections import Counter
from contextlib import closing
import json
import os
import sqlite3
from types import SimpleNamespace

import reliability4 as study
from compare_occasion_sources import control_digest, paired_gap


CASES = ("dev-first", "dev-repeat")


def cafe_habit(plan, shelf):
    removed = 0
    for visit in plan.visits:
        uid = visit["uuid"]
        person = plan.plain["profiles"][uid]
        favorites = {person[k] for k in ("좋아하는 음료 1순위", "2순위", "3순위")}
        if "커피전문점 커피" in favorites and "인스턴트·캔 커피" not in favorites:
            habit = plan.plain["purchase_habits"][uid]
            original = habit.get("products", [])
            kept = [key for key in original if shelf[key].kind != "커피"]
            if kept != original:
                habit["products"] = kept
                removed += 1
    return {"people_losing_coffee_name": removed}


def unknown_sugar(plan, shelf):
    changed = 0
    for item in shelf.values():
        if item.added and not item.row["당"]:
            for need in ("N05", "N06", "N07"):
                plan.plain["fulfills"][item.key][need] = "정보 없음"
            changed += 1
    return {"products_with_unknown_sugar": changed}


def period_prices(plan, shelf):
    sales = [r for r in study.onsite.load("pos_clean") if r["channel"] == "편의점"]
    months = sorted({r["month"] for r in sales})
    if len(months) != 24:
        raise ValueError("비교 기간 24개월이 필요합니다.")
    training = [r for r in sales if r["month"] in months[:12]]
    past = {p.sku: p for p in study.catalog._combine(training, study.onsite.load("assets")) if p.sku}
    counts = Counter()
    for row in plan.plain["products"]:
        item = shelf[row["상품명"]]
        if not item.added:
            continue
        historical = past[item.sku]
        if (historical.kind, historical.volume, historical.pack) != (item.kind, item.volume, item.pack):
            raise ValueError("앞 12개월의 제품 규격이 달라졌습니다.")
        counts["price_changes"] += item.price != historical.price
        counts["promotion_changes"] += item.promo != historical.promo
        row.update({"가격(원)": str(historical.price), "행사": historical.promo})
        for need in ("N02", "N03", "N04"):
            plan.plain["fulfills"][item.key][need] = historical.fulfills[need]
    return dict(counts)


def audit(control, plan, condition, label):
    changed = 0
    if plan.visits != control.visits:
        raise ValueError("방문 조건이 다릅니다.")
    for visit in plan.visits:
        system, before, order = study.method.prompts(control, visit, condition)
        new_system, after, new_order = study.method.prompts(plan, visit, condition)
        a, b = json.loads(before), json.loads(after)
        if label == "cafe-habit":
            del a["평소_습관"]["자주_사는_상품"], b["평소_습관"]["자주_사는_상품"]
        else:
            allowed_needs = ("N05", "N06", "N07") if label == "unknown-sugar" else ("N02", "N03", "N04")
            for need in allowed_needs:
                del a["욕구별_상품_번호"][need], b["욕구별_상품_번호"][need]
            if label == "period-prices":
                for entry in a["매대"] + b["매대"]:
                    entry.pop("가격_원")
                    entry.pop("행사", None)
        if (system != new_system or a != b or
                [r["상품명"] for r in order] != [r["상품명"] for r in new_order]):
            raise ValueError(f"{label}에서 의도한 항목 밖의 입력이 바뀌었습니다.")
        changed += before != after
    return changed


async def measure(root, label, plan, condition, config, changes, control, workers):
    folder = root / f"luna-low-r11-{label}"
    with study.records(folder, {**config, "variant": label}) as db:
        scores = {}
        batches = []
        for case in CASES:
            batch = await study.collect(db, case, 100, 70, workers, prepared_plan=(plan, condition))
            if batch.keys() != control[case].keys() or any(r["product"] is None for r in batch.values()):
                raise ValueError(f"{label} {case}에 유효한 짝 100건이 필요합니다.")
            batches.append(batch)
            fit = study.period_fit(batch.values(), training=True)
            scores[case] = {key: fit[key] for key in ("gap", "rho", "n_products", "matched_picks", "kinds_matched")}
            scores[case]["paired_gap"] = paired_gap(control[case], batch)
            print(label, case, "판매 비중 차이", round(fit["gap"], 2), flush=True)
        retest = study.reliability.retest(*[{k: r["product"] for k, r in b.items()} for b in batches])
        report = {"audit": changes, "scores": scores, "retest": retest,
                  "usage": study.cost([r for b in batches for r in b.values()])}
        temp = folder / "report.tmp"
        temp.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n")
        temp.replace(folder / "report.json")


async def main(workers, dry_run, baseline_sales):
    os.environ.update(AX_LLM="codex", AX_MODEL_SHOPPER="gpt-6-luna", AX_EFFORT_SHOPPER="low", AX_SHOPPER_ROUND="11")
    root = study.OUT / ".dev"
    control, condition = study.make_plan("dev-first", 100, 70)
    digest = control_digest(control, condition)
    config = {**study.settings(SimpleNamespace(people=100, per_cell=70)), "round": 11, "backend": "codex"}
    saved = (root / "luna-low-r11" / "responses.sqlite").resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(saved, uri=True)) as db:
        if json.loads(db.execute("SELECT settings FROM manifest").fetchone()[0]) != config:
            raise ValueError("기준 11차와 측정 조건이 다릅니다.")
        saved_digests = dict(db.execute("SELECT scenario,digest FROM plans"))
        if any(saved_digests.get(case) != digest for case in CASES):
            raise ValueError("저장된 두 회차와 입력이 다릅니다.")
        baseline = {case: study.responses(db, case) for case in CASES}
    if any(len(b) != 100 or any(r["product"] is None for r in b.values()) for b in baseline.values()):
        raise ValueError("기준 11차가 두 회차 모두 완전해야 합니다.")
    if baseline_sales:
        for case in CASES:
            metric = study.score(3, [baseline[case]])
            detail = metric["detail"]
            print(json.dumps({"case": case, "n": detail["n"], "matched_picks": detail["matched_picks"],
                              "n_products": metric["n_products"], "train_months": detail["train_months"],
                              "test_months": detail["test_months"], "raw": {"gap": metric["gap"], "rho": metric["value"]},
                              "calibrated": detail["calibrated"], "past_sales_only": detail["matched_history"]},
                             ensure_ascii=False, allow_nan=False))
        return
    config["control_digest"] = digest
    trials = []
    shelf = {p.key: p for p in study.catalog.current() if p.shelf == study.method.SHELF}
    variants = (("cafe-habit", cafe_habit), ("unknown-sugar", unknown_sugar), ("period-prices", period_prices))
    for index, (label, change) in enumerate(variants):
        plan, _ = study.make_plan("dev-first", 100, 70)
        counts = change(plan, shelf)
        counts["changed_prompts"] = audit(control, plan, condition, label)
        print(label, counts, flush=True)
        if not counts["changed_prompts"]:
            raise ValueError(f"{label}의 입력이 기준과 같습니다.")
        capacity = workers // len(variants) + int(index < workers % len(variants))
        trials.append((root, label, plan, condition, config, counts, baseline, capacity))
    if not dry_run:
        await asyncio.gather(*(measure(*args) for args in trials))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=8, help="세 실험을 합친 동시 호출 수")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--baseline-sales", action="store_true", help="저장된 기준 11차 두 회차로 앞·뒤 12개월을 대조한다")
    args = parser.parse_args()
    if not args.baseline_sales and args.workers < 3:
        parser.error("세 조건의 동시 측정에는 workers가 3 이상이어야 합니다.")
    asyncio.run(main(args.workers, args.dry_run, args.baseline_sales))
