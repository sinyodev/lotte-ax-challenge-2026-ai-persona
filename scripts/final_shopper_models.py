"""기준 11차 입력으로 16명 비용을 먼저 재고, 10배 미만인 후보를 100명까지 비교한다."""

import argparse
import asyncio
from contextlib import closing
import json
import os
import sqlite3
from types import SimpleNamespace

import reliability4 as study
from compare_occasion_sources import control_digest


CANDIDATES = {"terra-low": ("gpt-6.1-terra", "low"), "luna-high": ("gpt-6-luna", "high")}
CASES = ("dev-first", "dev-repeat")


def summary(pair):
    first, repeat = pair
    rows = [r for batch in pair for r in batch.values()]
    if set(first) != set(repeat) or any(r["product"] is None for r in rows):
        raise ValueError("두 번 모두 유효한 응답이 필요합니다.")
    fit = [study.period_fit(batch.values(), training=True) for batch in pair]
    retest = study.reliability.retest(*[{k: r["product"] for k, r in batch.items()} for batch in pair])
    return {"fit": [{k: item[k] for k in ("n", "bought", "matched_picks", "n_products", "gap", "rho")} for item in fit],
            "retest": retest, "usage": study.cost(rows)}


async def run(candidate, workers):
    model, effort = CANDIDATES[candidate]
    os.environ.update(AX_LLM="codex", AX_MODEL_SHOPPER=model, AX_EFFORT_SHOPPER=effort, AX_SHOPPER_ROUND="11")
    root = study.OUT / ".dev"
    plan, condition = study.make_plan("dev-first", 100, 70)
    digest = control_digest(plan, condition)
    control = root / "luna-low-r11" / "responses.sqlite"
    with closing(sqlite3.connect(control.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        reference = json.loads(db.execute("SELECT settings FROM manifest").fetchone()[0])
        if (reference["model"], reference["effort"], reference["round"], reference["backend"]) != (
                "gpt-6-luna", "low", 11, "codex"):
            raise ValueError("비교 기준이 11차 Luna low와 다릅니다.")
        for case in CASES:
            if db.execute("SELECT digest FROM plans WHERE scenario=?", (case,)).fetchone() != (digest,):
                raise ValueError("비교 기준의 입력과 다릅니다.")
        baseline = [study.responses(db, case) for case in CASES]
    config = {**study.settings(SimpleNamespace(people=100, per_cell=70)), "backend": "codex", "round": 11,
              "control_digest": digest}
    folder = root / f"{candidate}-r11-final"
    report = {}
    with study.records(folder, config) as db:
        for n in (16, 100):
            ids = [v["방문"] for v in plan.visits[:n]]
            if len(ids) != n:
                raise ValueError("개발 패널이 부족합니다.")
            pair = [await study.collect(db, case, 100, 70, workers, prepared_plan=(plan, condition), visit_limit=n)
                    for case in CASES]
            if any(set(batch) != set(ids) for batch in pair):
                raise ValueError("응답을 모두 받지 못했습니다.")
            measured = summary(pair)
            baseline_cost = study.cost([batch[k] for batch in baseline for k in ids])
            candidate_cost = measured["usage"]
            if candidate_cost["unpriced_answers"] or baseline_cost["unpriced_answers"]:
                raise ValueError("비용을 산출할 수 없는 응답이 있습니다.")
            measured["cost_ratio"] = candidate_cost["known_cost_usd"] / baseline_cost["known_cost_usd"]
            measured["baseline_cost"] = baseline_cost
            report[str(n)] = measured
            tmp = folder / "report.tmp"
            tmp.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n")
            tmp.replace(folder / "report.json")
            print(candidate, n, "비용 배수", measured["cost_ratio"], "재현율", measured["retest"]["value"], flush=True)
            if measured["cost_ratio"] >= 10:
                break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", choices=CANDIDATES)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    asyncio.run(run(args.candidate, args.workers))
