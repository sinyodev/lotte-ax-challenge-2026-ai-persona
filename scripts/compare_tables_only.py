"""원본 11차와 관계를 제거한 표 입력으로 같은 손님에게 두 번씩 묻는다."""

import argparse
import asyncio
from contextlib import closing
import json
import os
import re
import sqlite3
from types import SimpleNamespace

import reliability4 as study
from compare_occasion_sources import control_digest, paired_gap


CASES = ("dev-first", "dev-repeat")
ATTRIBUTES = ("제조사", "종류", "용량(ml)", "모양", "당", "카페인", "탄산", "성분")


def table_inputs(plan, condition):
    if condition != study.method.BASELINE:
        raise ValueError("기존 상품 매대에서만 비교합니다.")
    system = """당신은 한국의 편의점에 들른 손님 한 사람입니다. 아래에 주어지는 사람이 되어, 그 사람이라면 지금 이 매대에서 무엇을 살지 정하세요.

주어진 사람의 형편과 습관에 맞게 고르세요. 매대에 적힌 것만 보고 판단하세요. 적히지 않은 정보를 지어내지 마세요.
꼭 사야 하는 것은 아닙니다. 사지 않을 것 같거나 마음에 드는 것이 없으면 0번을 고르고 그 이유를 적으세요. 번호의 순서에는 뜻이 없습니다.
종류별 월 구매 횟수는 그 종류 전체의 횟수입니다. 1+1은 한 개 값으로 두 개, 2+1은 두 개 값으로 세 개입니다. 집이나 일터에 있는 것으로 해결할 수도 있습니다.
이유는 그 사람이 직접 말하듯 한두 문장으로 쓰세요."""
    original_schema = study.method.schema(False)
    columns = ("choice_number", "reason_sentence")
    schema = {**original_schema, "properties": {k: original_schema["properties"][k] for k in columns},
              "required": list(columns)}
    result = {}
    for visit in plan.visits:
        _, original, order = study.method.prompts(plan, visit, condition)
        data = json.loads(original)
        # 원본과 같은 표 행만 허용한다. 방문의 배정 상황과 욕구 관련 표는 전송하지 않는다.
        basket = []
        for item, row in zip(data["매대"], order, strict=True):
            expected_name = plan.plain["display"][row["상품명"]]
            if item["이름"] != expected_name or item["번호"] != len(basket) + 1:
                raise ValueError("매대 줄의 이름이나 진열 순서가 다릅니다.")
            basket.append({**item, **{k: row[k] for k in ATTRIBUTES if row.get(k)}})
        payload = {"손님": data["손님"], "평소_습관": data["평소_습관"],
                   "방문": {k: data["오늘_상황"][k] for k in ("월", "월평균_기온")},
                   "비구매_번호": data["비구매_번호"], "매대": basket}
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        outbound = system + text + json.dumps(schema, ensure_ascii=False)
        if re.search(r"reason_needs|욕구별_상품_번호|평소_욕구|상황별_욕구_변화|(?<![A-Za-z0-9])[NABD]\d{2}(?![A-Za-z0-9])", outbound):
            raise ValueError("표 입력에 온톨로지 전용 필드나 코드가 남았습니다.")
        result[visit["방문"]] = (system, text, order, schema)
    return result


async def run_arm(root, name, plan, condition, config, inputs, workers):
    batches = []
    with study.records(root / name, {**config, "arm": name}) as db:
        for case in CASES:
            rows = await study.collect(db, case, 100, 70, workers, prepared_plan=(plan, condition), prepared_inputs=inputs)
            if set(rows) != {v["방문"] for v in plan.visits} or any(r["product"] is None for r in rows.values()):
                raise ValueError(f"{name} {case}에는 유효 응답 100건이 필요합니다.")
            batches.append(rows)
            print(name, case, "완료", flush=True)
    return batches


def arm_scores(batches):
    retest = study.reliability.retest(*[{k: r["product"] for k, r in b.items()} for b in batches])
    scores = []
    for batch in batches:
        metric = study.score(3, [batch])
        detail = metric["detail"]
        scores.append({"gap": metric["gap"], "rho": metric["value"], "calibrated": detail["calibrated"],
                       "matched_picks": detail["matched_picks"], "n_products": metric["n_products"],
                       "past_sales_only": detail["matched_history"]})
    return {"scores": scores, "retest": retest, "usage": study.cost([r for b in batches for r in b.values()])}


def linked_reasons(batches, plan):
    rules = plan.plain["fulfills"]
    report = []
    for batch in batches:
        purchases = [r for r in batch.values() if r["product"] in rules]
        linked = sum(any(rules[r["product"]].get(c) in ("잘 채움", "조금 채움") for c in r["needs"])
                     for r in purchases)
        report.append({"purchases": len(purchases), "with_positive_product_link": linked})
    return report


async def main(workers, dry_run):
    os.environ.update(AX_LLM="codex", AX_MODEL_SHOPPER="gpt-6-luna", AX_EFFORT_SHOPPER="low", AX_SHOPPER_ROUND="11")
    plan, condition = study.make_plan("dev-first", 100, 70)
    root = study.OUT / ".dev"
    digest = control_digest(plan, condition)
    config = {**study.settings(SimpleNamespace(people=100, per_cell=70)), "round": 11, "backend": "codex"}
    prior = root / "luna-low-r11" / "responses.sqlite"
    if prior.exists():
        with closing(sqlite3.connect(prior.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            saved = dict(db.execute("SELECT scenario,digest FROM plans"))
            if (any(saved.get(c) != digest for c in CASES) or
                    json.loads(db.execute("SELECT settings FROM manifest").fetchone()[0]) != config):
                raise ValueError("원본 11차 기준이 바뀌었습니다.")
    inputs = table_inputs(plan, condition)
    print(f"{len(inputs)}명 × {len(plan.plain['products'])}개 상품 대조 완료", flush=True)
    if dry_run:
        return
    folder = root / "ontology-tables-r11"
    config["control_digest"] = digest
    on, off = await asyncio.gather(run_arm(folder, "ontology", plan, condition, config, None, workers // 2),
                                   run_arm(folder, "tables", plan, condition, config, inputs, workers - workers // 2))
    report = {"ontology": arm_scores(on), "tables": arm_scores(off),
              "tables_minus_ontology_gap": [paired_gap(a, b, training=False) for a, b in zip(on, off, strict=True)],
              "total_usage": study.cost([r for b in on + off for r in b.values()])}
    report["ontology"]["reason_links"] = linked_reasons(on, plan)
    temp = folder / "report.tmp"
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temp.replace(folder / "report.json")
    print(json.dumps(report, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.workers < 2:
        parser.error("두 조건을 병렬로 실행하려면 동시 수가 2 이상이어야 합니다.")
    asyncio.run(main(args.workers, args.dry_run))
