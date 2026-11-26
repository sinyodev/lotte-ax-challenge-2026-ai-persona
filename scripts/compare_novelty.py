"""새로움 욕구(N08) 보정 세 조건(off, survey, strict)을 개발 패널 20대 100명에게 비교한다.

같은 손님, 같은 진열 순서, 같은 달(5~9월). 11차 글, gpt-6-luna low, Codex 워크스페이스(AX_LLM=codex)만 쓴다.
조건마다 컨셉 없는 매대, 밀키스 화채 PET 500mL 1,800원, 중립 신제품(블렌드 커피 캔 330mL 1,500원)을 묻는다.
응답은 app/server/store/novelty/(저장소에 올리지 않음)에 한 건씩 저장해, 끊겨도 같은 명령으로 이어서 돈다.
실행: uv run --project app/server python scripts/compare_novelty.py [--workers 8] [--dry-run]
"""

import argparse
import asyncio
from collections import Counter
import json
from math import sqrt
import os
from pathlib import Path
import sqlite3
import sys
import time

SERVER = Path(__file__).resolve().parents[1] / "app" / "server"
sys.path.insert(0, str(SERVER))
if __name__ == "__main__" and Path(sys.prefix).resolve() != (SERVER / ".venv").resolve():
    os.execvp("uv", ["uv", "run", "--project", str(SERVER), "--no-env-file", "--locked",
                     "python", str(Path(__file__).resolve()), *sys.argv[1:]])

os.environ.update(AX_LLM="codex", AX_MODEL_SHOPPER="gpt-6-luna", AX_EFFORT_SHOPPER="low", AX_SHOPPER_ROUND="11")

from llm.models import model_for  # noqa: E402
from onsite.concepts import CONCEPTS, spec_of  # noqa: E402
from shelftest import catalog, method, runner  # noqa: E402
from tools import shelf_items  # noqa: E402

OUT = SERVER / "store" / "novelty"
MODES = ("off", "survey", "strict")
SEASON = "5~9월 한정"
NEUTRAL = {"name": "블렌드 커피", "kind": "커피", "container": "캔", "volume": 330, "price": 1500}


def panel():
    people = method.people("19-29", None, pool="dev")[:100]
    if len(people) != 100:
        raise ValueError("개발 패널 20대가 100명이 안 됩니다.")
    return list(people)


def plans(people):
    concept = next(c for c in CONCEPTS if c["id"] == "milkis-hwachae")
    size = next(v for v in spec_of(concept)["variants"] if v["pack"] == "PET")
    line = method.line_name(concept["name"], size["container"], size["volume_ml"])
    milkis = method.plan(None, None, None, len(people), line, size["price"], None, participants=people,
                         storage=concept["storage"], season=SEASON)
    shelf_items.enrich_concept(milkis, {**concept, "appeal": concept["summary"],
                                        "volume": size["volume_ml"], "container": size["container"]})
    milkis.with_concept["concept_prompt_version"] = runner.CONCEPT_PROMPT_VERSION
    name = method.line_name(NEUTRAL["name"], NEUTRAL["container"], NEUTRAL["volume"])
    neutral = method.plan(None, None, None, len(people), name, NEUTRAL["price"], None, participants=people,
                          season=SEASON)
    shelf_items.enrich_concept(neutral, NEUTRAL)
    neutral.with_concept["concept_prompt_version"] = runner.CONCEPT_PROMPT_VERSION
    if [v["visit_month"] for v in milkis.visits] != [v["visit_month"] for v in neutral.visits]:
        raise ValueError("두 컨셉의 방문 달이 다릅니다.")
    return {"base": (milkis, method.BASELINE), "milkis": (milkis, method.CONCEPT), "neutral": (neutral, method.CONCEPT)}


def database():
    OUT.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(OUT / "answers.sqlite")
    db.execute("CREATE TABLE IF NOT EXISTS answers (mode TEXT, shelf TEXT, ask TEXT, visit TEXT, body TEXT NOT NULL,"
               " PRIMARY KEY(mode, shelf, ask, visit))")
    return db


async def collect(db, mode, case, plan, condition, workers):
    shelf = method.shelf_v()
    saved = {v: json.loads(b) for v, b in db.execute(
        "SELECT visit, body FROM answers WHERE mode=? AND shelf=? AND ask=?", (mode, shelf, case))}
    model = model_for("shopper").model
    pending = [v for v in plan.visits if v["방문"] not in saved or saved[v["방문"]]["product"] is None]
    print(f"{mode} {case}: 저장 {len(plan.visits) - len(pending)}, 물을 것 {len(pending)}", flush=True)
    semaphore = asyncio.Semaphore(workers)
    calls = 0

    async def one(visit):
        nonlocal calls
        async with semaphore:
            start = time.time()
            answer, error = await runner._ask(plan, visit, condition, model)
            calls += 1
            body = {"product": answer["product"] if answer else None, "error": error,
                    "needs": answer["needs"] if answer else [], "view": (answer or {}).get("view"),
                    "barriers": (answer or {}).get("barriers", []), "sec": round(time.time() - start, 1)}
            db.execute("INSERT OR REPLACE INTO answers VALUES (?,?,?,?,?)",
                       (mode, shelf, case, visit["방문"], json.dumps(body, ensure_ascii=False)))
            db.commit()
            saved[visit["방문"]] = body

    for _ in range(3):
        todo = [v for v in plan.visits if v["방문"] not in saved or saved[v["방문"]]["product"] is None]
        if not todo:
            break
        await asyncio.gather(*(one(v) for v in todo))
    return {v["방문"]: saved[v["방문"]] for v in plan.visits}, calls


def wilson(k, n, z=1.96):
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(100 * (c - h), 1), round(100 * (c + h), 1)]


def summarize(line, base, concept):
    products = {p.key: p for p in catalog.current() if p.shelf == method.SHELF}
    valid = [k for k, r in concept.items() if r["product"] is not None]
    picks = [k for k in valid if concept[k]["product"] == line]
    counts = Counter(concept[k]["product"] for k in valid if concept[k]["product"] != method.NO_PURCHASE)
    rank = 1 + sum(n > counts[line] for key, n in counts.items() if key != line)
    pos = sum(n for key, n in counts.items() if key.startswith("pos:"))
    sold = sum(n for key, n in counts.items() if key in products and products[key].sku)
    before = Counter()
    for k in picks:
        prior = base.get(k, {}).get("product")
        if prior is None:
            before["모름"] += 1
        elif prior == method.NO_PURCHASE:
            before["사지 않음"] += 1
        else:
            before["자사" if prior in products and products[prior].is_own else "경쟁사"] += 1
    reasons = {code: sum(code in concept[k].get("needs", []) for k in picks) for code in ("N07", "N08", "N09")}
    n08 = Counter(int(r.get("needs") and "N08" in r["needs"]) for k, r in concept.items() if k in picks)
    return {"n": len(valid), "picked": len(picks), "rate": round(100 * len(picks) / len(valid), 1) if valid else None,
            "wilson95": wilson(len(picks), len(valid)),
            "share_pos": round(100 * len(picks) / (pos + len(picks)), 1) if pos + len(picks) else None,
            "pos_picks": pos,
            "share_sku": round(100 * len(picks) / (sold + len(picks)), 1) if sold + len(picks) else None,
            "n08_reason": n08[1], "reasons": reasons, "n08_reason_all": sum("N08" in r.get("needs", []) for r in concept.values()),
            "rank": rank, "products": len(products) + 1, "no_purchase": concept and sum(
                r["product"] == method.NO_PURCHASE for r in concept.values()),
            "before": dict(before)}


async def relation_study(values, cases_to_ask, workers):
    """strict 고정에서 컨셉의 N08 관계(AX_CONCEPT_NOVELTY)를 바꾼다. 컨셉 없는 매대는 strict의 저장된 답을 쓴다."""
    os.environ["AX_NOVELTY"] = "strict"
    os.environ["AX_CONCEPT_NOVELTY"] = "well"
    people = panel()
    db = database()
    base_shelf = method.shelf_v()
    base = {v: json.loads(b) for v, b in db.execute(
        "SELECT visit, body FROM answers WHERE mode='strict' AND shelf=? AND ask='base'", (base_shelf,))}
    if len(base) != 100 or any(r["product"] is None for r in base.values()):
        raise ValueError("strict 컨셉 없는 매대의 답 100건이 먼저 필요합니다.")
    path = OUT / "relation_report.json"
    report = json.loads(path.read_text()) if path.exists() else {}
    began, total = time.time(), 0
    for value in values:
        os.environ["AX_CONCEPT_NOVELTY"] = value
        cases = plans(people)
        if cases["base"][0].plain["products"] != plans_base_products(people):
            raise ValueError("컨셉 없는 매대가 달라졌습니다.")
        for case in cases_to_ask:
            plan, condition = cases[case]
            answers, calls = await collect(db, f"strict-{value}", case, plan, condition, workers)
            total += calls
            report.setdefault(value, {})[case] = summarize(plan.line, base, answers)
            report[value]["fulfills_N08"] = cases["milkis"][0].with_concept["fulfills"][cases["milkis"][0].line].get("N08")
            report[value]["shelf_v"] = method.shelf_v()
    report.setdefault("runs", []).append({"calls": total, "seconds": round(time.time() - began), "values": values,
                                          "cases": cases_to_ask})
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def plans_base_products(people):
    current = os.environ["AX_CONCEPT_NOVELTY"]
    os.environ["AX_CONCEPT_NOVELTY"] = "well"
    try:
        return plans(people)["base"][0].plain["products"]
    finally:
        os.environ["AX_CONCEPT_NOVELTY"] = current


async def main(workers, dry_run):
    from calibrate import novelty
    people = panel()
    db = database()
    report, total_calls, began = {}, 0, time.time()
    for mode in MODES:
        os.environ["AX_NOVELTY"] = mode
        os.environ["AX_CONCEPT_NOVELTY"] = "well"  # 첫 비교는 컨셉의 N08 관계를 그대로 둔다
        cases = plans(people)
        strength = cases["base"][0].plain["strength"]
        levels = Counter(int(strength[p.uuid]["N08"]) for p in people)
        print(mode, "판", method.shelf_v(), "N08 분포", dict(sorted(levels.items())), flush=True)
        if dry_run:
            continue
        answers = {}
        for case, (plan, condition) in cases.items():
            answers[case], calls = await collect(db, mode, case, plan, condition, workers)
            total_calls += calls
        report[mode] = {"shelf_v": method.shelf_v(), "signature": novelty.signature(mode),
                        "panel_n08": dict(sorted(levels.items())),
                        "milkis": summarize(cases["milkis"][0].line, answers["base"], answers["milkis"]),
                        "neutral": summarize(cases["neutral"][0].line, answers["base"], answers["neutral"]),
                        "baseline_no_purchase": sum(r["product"] == method.NO_PURCHASE for r in answers["base"].values())}
    if dry_run:
        return
    report["calls_this_run"] = total_calls
    report["seconds_this_run"] = round(time.time() - began)
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--relation", nargs="+", choices=("well", "partly", "none"),
                        help="strict 고정에서 컨셉의 N08 관계만 바꿔 잰다")
    parser.add_argument("--cases", nargs="+", choices=("milkis", "neutral"), default=["milkis"])
    args = parser.parse_args()
    if args.relation:
        asyncio.run(relation_study(args.relation, args.cases, args.workers))
    else:
        asyncio.run(main(args.workers, args.dry_run))
