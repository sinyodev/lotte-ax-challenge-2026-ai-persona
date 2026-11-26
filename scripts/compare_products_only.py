"""손님·관계표를 읽지 않고, 제품표 한 장으로 100개 진열 순서의 반복 선택을 측정한다."""

import argparse
import asyncio
from collections import Counter
from contextlib import closing
import json
import os
import sqlite3
from types import SimpleNamespace

import reliability4 as study
import pilot
import reliability as pilot_reliability
from compare_tables_only import ATTRIBUTES, CASES, run_arm


SYSTEM = """당신은 한국의 편의점 매대 앞에 있습니다. 제품표에서 지금 살 상품 한 개의 번호를 고르세요.
살 것이 없으면 0번을 고르세요. 진열 번호는 순위가 아닙니다. 표에 없는 정보를 지어내지 마세요.
1+1은 한 개 값으로 두 개, 2+1은 두 개 값으로 세 개입니다. 선택 이유를 한두 문장으로 적으세요."""


def product_inputs(products, visits):
    rows = [p.row for p in products]
    display = {p.key: p.name for p in products}
    original = study.method.schema(False)
    columns = ("choice_number", "reason_sentence")
    schema = {**original, "required": list(columns), "properties": {k: original["properties"][k] for k in columns}}
    inputs = {}
    for visit in visits:
        order = pilot.shelf_order(rows, {"방문": visit}, study.method.BASELINE, 1, 9)
        basket = []
        for number, row in enumerate(order, 1):
            item = {"번호": number, "이름": display[row["상품명"]], "가격_원": int(row["가격(원)"])}
            if row["행사"] and not row["행사"].startswith("행사 없음"):
                item["행사"] = row["행사"]
            if int(row["묶음 수량"]) > 1:
                item["묶음_수량"] = int(row["묶음 수량"])
            item.update({k: row[k] for k in ATTRIBUTES if row.get(k)})
            basket.append(item)
        inputs[visit] = (SYSTEM, json.dumps(basket, ensure_ascii=False, separators=(",", ":")), order, schema)
    return inputs


def category_revenue_scores(batches, products):
    reference = pilot_reliability.real_share(2025, study.method.SHELF)
    available = {p.key: p for p in products if p.kind in reference}
    scores = []
    for batch in batches:
        amounts = Counter()
        matched = 0
        for row in batch.values():
            product = available.get(row["product"])
            if product:
                amounts[product.kind] += product.price
                matched += 1
        total = amounts.total()
        shares = {k: 100 * amount / total for k, amount in amounts.items()} if total else {}
        scores.append({"gap": pilot_reliability.gap(shares, reference) if total else None, "matched": matched})
    return scores


async def main(workers, dry_run):
    os.environ.update(AX_LLM="codex", AX_MODEL_SHOPPER="gpt-6-luna", AX_EFFORT_SHOPPER="low")
    sales = study.onsite.load("pos_clean")
    catalog = study.catalog._combine(sales, study.onsite.load("assets"), with_fulfills=False)
    products = [p for p in catalog if p.shelf == study.method.SHELF]
    if len(products) != 67 or any(p.fulfills for p in products):
        raise ValueError("관계 없는 기존 제품 67개가 필요합니다.")
    # 이전 실험과 같은 진열 번호와 채점 층을 쓴다. 모델에는 진열된 제품 행만 전달한다.
    visits = []
    for i in range(100):
        age, sex = study.explore.CELLS[i % len(study.explore.CELLS)]
        key = f"T{i + 1:03d}"
        visits.append({"방문": key, "uuid": key, "연령대": age, "성별": sex})
    inputs = product_inputs(products, [v["방문"] for v in visits])
    if len({text for _, text, _, _ in inputs.values()}) != len(visits):
        raise ValueError("진열 순서가 중복됐습니다.")
    print(f"제품 {len(products)}개, 진열 순서 {len(visits)}개, 입력은 제품 행 배열 하나", flush=True)
    if dry_run:
        return
    root = study.OUT / ".dev" / "ontology-tables-r11"
    config = {"model": "gpt-6-luna", "effort": "low", "backend": "codex", "orders": len(inputs)}
    batches = await run_arm(root, "products-only", SimpleNamespace(visits=visits, line=None),
                            study.method.BASELINE, config, inputs, workers)
    kinds = {p.key: (p.sku, p.kind) for p in products if p.sku}
    population = study.explore.population_weights()
    if not population:
        raise ValueError("11차와 같은 채점 가중치가 필요합니다.")
    weights = dict(zip(study.explore.CELLS, population, strict=True))
    sizes = Counter((v["연령대"], v["성별"]) for v in visits)
    equal_order_weights = {k: n / len(visits) for k, n in sizes.items()}
    by_type = {p.key: p.kind for p in products}
    scores = []
    for batch in batches:
        metric = study.reliability.sales_rank(batch.values(), weights, kinds, sales)
        unweighted = study.reliability.sales_rank(batch.values(), equal_order_weights, kinds, sales)
        detail = metric["detail"]
        choices = Counter(r["product"] for r in batch.values())
        category_counts = Counter()
        for key, n in choices.items():
            category_counts[by_type.get(key, study.method.NO_PURCHASE)] += n
        scores.append({"gap": metric["gap"], "rho": metric["value"], "calibrated": detail["calibrated"],
                       "matched_picks": detail["matched_picks"], "n_products": metric["n_products"],
                       "unseen_kinds": detail["unseen_kinds"], "equal_order_gap": unweighted["gap"],
                       "no_purchase": choices[study.method.NO_PURCHASE], "distinct_choices": len(choices),
                       "category_counts": dict(category_counts.most_common())})
    pairs = [{k: r["product"] for k, r in b.items()} for b in batches]
    report = {"scores": scores, "retest": study.reliability.retest(*pairs),
              "usage": study.cost([r for b in batches for r in b.values()])}
    report["category_revenue_2025"] = {"products_only": category_revenue_scores(batches, products)}
    prior = study.OUT / ".dev" / "luna-low-r11" / "responses.sqlite"
    if prior.is_file():
        with closing(sqlite3.connect(prior.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            previous = [study.responses(db, case) for case in CASES]
            manifest = json.loads(db.execute("SELECT settings FROM manifest").fetchone()[0])
        if (manifest["round"], manifest["model"], manifest["effort"]) != (11, config["model"], config["effort"]):
            raise ValueError("비교할 원본 11차의 모델이 다릅니다.")
        if any(set(batch) != set(inputs) or any(r["product"] is None for r in batch.values()) for batch in previous):
            raise ValueError("원본 11차 두 회차의 유효한 응답이 필요합니다.")
        report["category_revenue_2025"]["ontology"] = category_revenue_scores(previous, products)
    path = root / "products-only" / "report.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    tmp.replace(path)
    print(json.dumps(report, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("동시 수는 1 이상이어야 합니다.")
    asyncio.run(main(args.workers, args.dry_run))
