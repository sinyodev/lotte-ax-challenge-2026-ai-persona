"""가상 소비자 네 지표를 같은 판의 응답에서 재계산한다. 실행법은 docs/reliability.md."""

import argparse
import asyncio
from collections import Counter
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from math import fsum
import os
from pathlib import Path
import re
import sqlite3
import sys
import time

SERVER = Path(__file__).resolve().parents[1] / "app" / "server"
sys.path.insert(0, str(SERVER))
if __name__ == "__main__" and Path(sys.prefix).resolve() != (SERVER / ".venv").resolve():
    os.execvp("uv", ["uv", "run", "--project", str(SERVER), "--no-env-file", "--locked",
                     "python", str(Path(__file__).resolve()), *sys.argv[1:]])

import onsite
from calibrate import reliability
from llm import usage
from llm.models import model_for
from onsite.concepts import CONCEPTS, spec_of
from shelftest import catalog, explore, method, runner
from tools import shelf_items

OUT = SERVER / "store" / "reliability"
PRICES = (1600, 1800, 2000)
CHECKS = ("check-regular", "check-can", "check-twenties", "check-original")
NEUTRAL = {"name": "블렌드 커피", "kind": "커피", "container": "캔", "volume": 330}
NEUTRAL_CASES = ("neutral-1500", "neutral-2000", "neutral-promo")
BRAND_CHECK = {"name": "칠성사이다 배향", "brand": "칠성사이다", "kind": "탄산",
               "flavor": "배향", "container": "캔", "volume": 330}
METHOD_KEYS = ("shelf", "model", "effort", "method", "prompt_version")


def conditions(metric):
    if metric == 1:
        return ["retest-a", "retest-b"]
    if metric == 2:
        return [f"price-{p}" for p in PRICES] + ["promo"]
    if metric == 3:
        return ["explore-base"]
    return [c["id"] for c in CONCEPTS]


def make_plan(case, people, per_cell):
    development = case.startswith("dev-")
    selected = None
    if development:
        groups = [method.people(age, sex, pool="dev") for age, sex in explore.CELLS]
        selected = [p for row in zip(*groups) for p in row][:people]
        if len(selected) != people:
            raise ValueError("개발 패널이 부족합니다.")
    variant = case.removeprefix("dev-")
    if variant in (*NEUTRAL_CASES, "brand"):
        product = BRAND_CHECK if variant == "brand" else NEUTRAL
        price = 2000 if variant == "neutral-2000" else 1500
        name = method.line_name(product["name"], product["container"], product["volume"])
        plan = method.plan(None, None, None, people, name, price, "1+1" if variant == "neutral-promo" else None,
                           participants=selected, annual_months=True, training=development)
        if len(plan.visits) != people:
            raise ValueError("보조 컨셉 비교에 필요한 패널이 부족합니다.")
        shelf_items.enrich_concept(plan, product)
        plan.with_concept["concept_prompt_version"] = runner.CONCEPT_PROMPT_VERSION
        return plan, method.CONCEPT
    if development:
        return method.plan(None, None, None, people, "측정 기준", 1, None, participants=selected,
                           annual_months=True, training=True), method.BASELINE
    study = case == "explore-base" or case in {c["id"] for c in CONCEPTS}
    age = "19-29" if case == "check-twenties" else None
    selected = explore.participants(per_cell) if study else method.people(age, None)[:people]
    if len(selected) != (len(explore.CELLS) * per_cell if study else people):
        raise ValueError("요청한 인원을 채울 수 없습니다.")
    concept = next((c for c in CONCEPTS if c["id"] == case), CONCEPTS[0])
    variants = spec_of(concept)["variants"]
    # 밀키스 화채는 지시서의 PET 500mL, 나머지 컨셉은 과제 보드의 단일 규격.
    size = next((v for v in variants if v["pack"] == "PET"), variants[0])
    if case == "check-can":
        size = next(v for v in variants if v["pack"] == "슬림캔")
    price = int(case.split("-")[1]) if case.startswith("price-") else size["price"]
    line = method.line_name(concept["name"], size["pack"] if case == "check-can" else size["container"], size["volume_ml"])
    if case == "check-original":
        original, = [p for p in catalog.current() if p.shelf == method.SHELF and p.volume == 500
                     and p.container == "페트" and "밀키스 오리지널" in p.name]
        plan = method.plan(None, None, None, len(selected), original.name, original.price, original.promo,
                           participants=selected)
        # 원래 제품의 가격·행사·속성을 복사하고 기존 줄을 뺀다. 67개 중 한 줄만 새 제품으로 소개한다.
        ctx = plan.with_concept
        replacement = {**original.row, "상품명": original.name, "용기": original.container}
        ctx["products"] = [replacement if p["상품명"] == original.key else p for p in plan.plain["products"]]
        ctx["fulfills"] = {**ctx["fulfills"], original.name: dict(original.fulfills)}
        ctx["concept_prompt_version"] = runner.CONCEPT_PROMPT_VERSION
        return plan, method.CONCEPT
    condition = method.BASELINE if case.startswith("retest-") or case == "explore-base" else method.CONCEPT
    plan = method.plan(None, None, None, len(selected), line, price, "1+1" if case == "promo" else None,
                       participants=selected, storage=concept["storage"], annual_months=condition == method.BASELINE)
    if condition == method.CONCEPT:
        shelf_items.enrich_concept(plan, {**concept, "appeal": concept["summary"],
                                         "volume": size["volume_ml"], "container": size["container"]})
        plan.with_concept["concept_prompt_version"] = runner.CONCEPT_PROMPT_VERSION
    return plan, condition


@contextmanager
def records(folder, settings):
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("같은 판을 이미 측정하고 있습니다.") from exc
        db = sqlite3.connect(folder / "responses.sqlite")
        try:
            db.execute("CREATE TABLE IF NOT EXISTS manifest (settings TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS answers (scenario TEXT, visit TEXT, body TEXT NOT NULL, PRIMARY KEY(scenario,visit))")
            db.execute("CREATE TABLE IF NOT EXISTS plans (scenario TEXT PRIMARY KEY, digest TEXT NOT NULL)")
            manifest = json.dumps(settings, ensure_ascii=False, sort_keys=True)
            old = db.execute("SELECT settings FROM manifest").fetchone()
            if old and old[0] != manifest:
                raise ValueError("표본·매대·모델이 바뀌었습니다. 새 --version을 지정하세요.")
            if not old:
                db.execute("INSERT INTO manifest VALUES (?)", (manifest,))
            db.commit()
            yield db
        finally:
            db.close()


def responses(db, case):
    return {visit: json.loads(body) for visit, body in db.execute(
        "SELECT visit,body FROM answers WHERE scenario=? ORDER BY visit", (case,))}


def reuse_saved(db, case, checksum, total):
    if case.startswith(("retest-", "dev-")):
        return {}
    local = Path(db.execute("PRAGMA database_list").fetchone()[2])
    config = json.loads(db.execute("SELECT settings FROM manifest").fetchone()[0])
    for other in sorted(local.parent.parent.glob("*/responses.sqlite")):
        if other == local:
            continue
        with closing(sqlite3.connect(other.as_uri() + "?mode=ro", uri=True)) as saved:
            if not saved.execute("SELECT 1 FROM sqlite_master WHERE name='plans'").fetchone():
                continue
            match = saved.execute("SELECT 1 FROM plans WHERE scenario=? AND digest=?", (case, checksum)).fetchone()
            prior = json.loads(saved.execute("SELECT settings FROM manifest").fetchone()[0])
            if not match or any(prior.get(k) != config.get(k) for k in METHOD_KEYS):
                continue
            found = responses(saved, case)
        if len(found) != total or any(r["product"] is None for r in found.values()):
            continue
        for key, row in found.items():
            row.setdefault("reused_from", other.parent.name)
            db.execute("INSERT INTO answers VALUES (?,?,?)", (case, key, json.dumps(row, ensure_ascii=False)))
        db.commit()
        return found
    return {}


class AttemptCosts:
    def __init__(self):
        self.attempts = []

    @contextmanager
    def call(self):
        with usage.collect() as measured:
            try:
                yield
            finally:
                self.attempts.append(measured.summary())


async def collect(db, case, people, per_cell, workers, *, recover=True, prepared_plan=None, visit_limit=None,
                  prepared_inputs=None):
    manifest = json.loads(db.execute("SELECT settings FROM manifest").fetchone()[0])
    if manifest.get("shelf") and method.shelf_v() != manifest["shelf"]:
        raise ValueError("측정 도중 매대가 바뀌었습니다. 새 판이 필요합니다.")
    plan, condition = prepared_plan if prepared_plan is not None else make_plan(case, people, per_cell)
    # 방문 번호만으로 다른 사람의 응답을 이어 쓰지 않도록 실제 입력과 진열 순서를 확인한다.
    digest = hashlib.sha256()
    for v in plan.visits:
        if prepared_inputs is None:
            system, prompt, order = method.prompts(plan, v, condition)
            if condition == method.CONCEPT:
                prompt += shelf_items.concept_prompt(plan, order)
            fingerprint = [v["uuid"], v["방문"], system, prompt]
        else:
            system, prompt, order, schema = prepared_inputs[v["방문"]]
            fingerprint = [v["uuid"], v["방문"], system, prompt, [row["상품명"] for row in order], schema]
        digest.update(json.dumps(fingerprint, ensure_ascii=False).encode())
    checksum = digest.hexdigest()
    old = db.execute("SELECT digest FROM plans WHERE scenario=?", (case,)).fetchone()
    if old and old[0] != checksum:
        raise ValueError(f"{case}의 소비자·상황·매대가 바뀌었습니다. 새 판이 필요합니다.")
    db.execute("INSERT OR IGNORE INTO plans VALUES (?,?)", (case, checksum))
    db.commit()
    existing = responses(db, case)
    if not existing:
        existing = reuse_saved(db, case, checksum, len(plan.visits))
    visits = plan.visits[:visit_limit]
    existing = {v["방문"]: existing[v["방문"]] for v in visits if v["방문"] in existing}
    model = model_for("shopper").model
    transport_errors = {"LLMError", "LLMTimeout"}
    valid_count = sum(r["product"] is not None for r in existing.values())
    print(f"{case} 유효 {valid_count}/{len(visits)}", flush=True)

    async def one(visit, semaphore):
        nonlocal valid_count
        async with semaphore:
            start = time.time()
            measured = AttemptCosts()
            if prepared_inputs is None:
                answer, error = await runner._ask(plan, visit, condition, model, measured)
            else:
                answer, error = await runner._ask_prepared(*prepared_inputs[visit["방문"]], condition == method.CONCEPT,
                                                           model, measured)
            attempts = measured.attempts
            costs = [a["est_cost_usd"] for a in attempts if a["est_cost_usd"] is not None]
            body = {"product": answer["product"] if answer else None, "error": error,
                    "selected": answer["product"] == plan.line if answer else None,
                    "age": visit["연령대"], "sex": visit["성별"], "start": start, "end": time.time(),
                    "calls": sum(a["calls"] for a in attempts),
                    "priced_calls": sum(a["calls"] for a in attempts if a["est_cost_usd"] is not None),
                    "known_usd": fsum(costs), "usd": fsum(costs) if len(costs) == len(attempts) else None,
                    "answer_cost_known": bool(answer and attempts and attempts[-1]["est_cost_usd"] is not None)}
            if answer and "journey" in answer:
                body["journey"] = answer["journey"]
                if condition == method.CONCEPT:
                    body["concept_key"] = plan.line
            if condition == method.CONCEPT and answer:
                body["barriers"] = list(dict.fromkeys(answer.get("barriers", [])))
            if case in ("dev-first", "dev-repeat") and answer:
                # 응답 원문과 사람의 서술은 저장하지 않고, 미리 등록한 이유 범주와 필요 코드만 센다.
                body["reason_tags"] = reason_tags(answer)
                body["needs"] = answer["needs"]
            if "visit_month" in visit:
                body["visit_month"] = visit["visit_month"]
            previous = existing.get(visit["방문"])
            if previous:
                body["history"] = [*previous.get("history", []), {k: v for k, v in previous.items() if k != "history"}]
            db.execute("INSERT OR REPLACE INTO answers VALUES (?,?,?)",
                       (case, visit["방문"], json.dumps(body, ensure_ascii=False)))
            db.commit()
            existing[visit["방문"]] = body
            if answer:
                valid_count += 1
                if valid_count % 50 == 0 or valid_count == len(visits):
                    print(f"{case} 유효 {valid_count}/{len(visits)}", flush=True)

    for parallel in ((workers, min(4, workers), 1) if recover else (workers,)):
        pending = [v for v in visits if v["방문"] not in existing or
                   (recover and existing[v["방문"]]["error"] in transport_errors)]
        if not pending:
            break
        semaphore = asyncio.Semaphore(parallel)
        await asyncio.gather(*(one(v, semaphore) for v in pending))
    if recover and any(r["error"] in transport_errors for r in existing.values()):
        raise RuntimeError(f"{case}에 전송 실패가 남았습니다. 같은 명령으로 이어서 실행하세요.")
    # 새 응답과 저장된 응답의 가중 합을 같은 순서로 계산한다.
    return {v["방문"]: existing[v["방문"]] for v in visits if v["방문"] in existing}


def reason_tags(answer):
    sentence = " ".join([answer["sentence"], answer["other"]])
    patterns = {"건강·당": "건강|무가당|저당|당류|당분|당이|달지|칼로리|부담 없|부담없",
                "행사": "행사|덤|[12]\\s*\\+\\s*1|원플러스|투플러스|하나 더",
                "가격": "가격|저렴|가성비|싼|싸서|할인|원이라",
                "상황": "식사|식후|운동|출근|퇴근|갈증|목이|피곤|잠을|아침|간식|이동|걷|산책",
                "맛·기호": "맛|좋아하|선호|입맛", "습관·익숙함": "평소|익숙|늘 |자주|습관|즐겨"}
    return [name for name, pattern in patterns.items() if re.search(pattern, sentence)]


def settings(args):
    selected = model_for("shopper")
    return {"people": args.people, "per_cell": args.per_cell, "shelf": method.shelf_v(),
            "prompt_version": runner.CONCEPT_PROMPT_VERSION, "model": selected.model,
            "effort": selected.effort, "method": 1}


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--people", type=int, default=300)
    parser.add_argument("--per-cell", type=int, default=70)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--only", type=int, nargs="+", choices=range(1, 5), default=[1, 2, 3, 4])
    parser.add_argument("--version", default="v3")
    parser.add_argument("--diagnostics", action="store_true", help="공식 지표와 별도로 네 조건을 각 100명에게 확인")
    parser.add_argument("--neutral-direction", action="store_true", help="평가 패널 100명에게 별도 중립 컨셉 가격·행사 비교")
    parser.add_argument("--dev-study", help="앞 12개월·개발용 패널로 비교할 후보 이름")
    parser.add_argument("--dev-claude", action="store_true", help="개발 패널 첫 30명만 한 번씩 Claude로 대조")
    parser.add_argument("--dev-guard", action="store_true", help="개발 패널의 중립 컨셉과 같은 브랜드 신제품 전환도 측정")
    args = parser.parse_args()
    if min(args.people, args.per_cell, args.workers) < 1 or not re.fullmatch(r"[a-zA-Z0-9_-]+", args.version):
        parser.error("인원과 동시 수는 양수이고 판 이름은 영문·숫자·밑줄·하이픈이어야 합니다.")
    if args.dev_study and not re.fullmatch(r"[a-zA-Z0-9_-]+", args.dev_study):
        parser.error("후보 이름은 영문·숫자·밑줄·하이픈이어야 합니다.")
    if args.dev_claude and not args.dev_study:
        parser.error("Claude 비교는 --dev-study에만 사용할 수 있습니다.")
    if args.dev_guard and (not args.dev_study or args.dev_claude):
        parser.error("개발 보조 측정은 Codex의 --dev-study에만 사용할 수 있습니다.")
    if sum(map(bool, (args.dev_study, args.diagnostics, args.neutral_direction))) > 1:
        parser.error("개발 비교·기존 진단·중립 컨셉 비교 중 하나를 지정하세요.")
    return args


def cost(rows):
    # 재시작 사이의 공백은 빼고, 동시 호출 시간의 합집합만 잰다.
    elapsed = 0.
    until = 0.
    visits = [part for r in rows for part in [*r.get("history", []), r]]
    for row in sorted(visits, key=lambda r: r["start"]):
        elapsed += max(0., row["end"] - max(until, row["start"]))
        until = max(until, row["end"])
    calls = sum(r["calls"] for r in visits)
    priced = sum(r["calls"] if r["usd"] is not None else r.get("priced_calls", 0) for r in visits)
    known = fsum(r.get("known_usd", r["usd"] or 0) for r in visits)
    # 초기 수집분의 일부는 전송 오류와 성공이 합산되어 성공 응답의 출력량을 분리할 수 없다.
    missing_answers = sum(r["product"] is not None and not r.get("answer_cost_known", r["usd"] is not None) for r in rows)
    known_answers = [r["usd"] for r in rows if r["product"] is not None and r["usd"] is not None]
    completed_cost = known if not missing_answers else (
        known + missing_answers * fsum(known_answers) / len(known_answers) if known_answers else None)
    return {"calls": calls, "elapsed_s": round(elapsed, 2), "priced_calls": priced,
            "unpriced_calls": calls - priced, "known_cost_usd": known, "unpriced_answers": missing_answers,
            "est_cost_usd": known if priced == calls else None,
            "completed_est_cost_usd": completed_cost,
            "recovered_visits": sum(r["product"] is not None and bool(r.get("history")) for r in rows),
            "reused_visits": sum("reused_from" in r for r in rows),
            "invalid": sum(r["product"] is None for r in rows)}


def score(metric, batches):
    if metric == 1:
        groups = [{k: r["product"] for k, r in rows.items()} for rows in batches]
        result = reliability.retest(*groups)
    elif metric == 2:
        summary = onsite.load_json("survey_summary")["concepts"][CONCEPTS[0]["name"]]
        wtp = [r["wtp"] for r in onsite.load("survey_ratings") if r["concept"] == CONCEPTS[0]["name"]]
        groups = [{k: r["selected"] for k, r in rows.items()} for rows in batches]
        result = reliability.direction(dict(zip(PRICES, groups[:3], strict=True)), groups[-1], wtp, summary["wtp"])
        product_map = {p.key: p for p in catalog.current() if p.shelf == method.SHELF}
        overview = []
        for case, batch in zip(conditions(2), batches, strict=True):
            counts = Counter(r["product"] for r in batch.values() if r["product"] is not None)
            n = counts.total()
            no_purchase = counts.pop(method.NO_PURCHASE, 0)
            info = {"condition": case, "n": n, "no_purchase": no_purchase,
                    "distinct_products": len(counts), "top_three_picks": sum(v for _, v in counts.most_common(3))}
            if case == "price-1800":
                info["top_products"] = [{"name": product_map[k].name if k in product_map else k, "n": v}
                                        for k, v in counts.most_common(10)]
                info["promoted_picks"] = sum(v for k, v in counts.items() if k in product_map
                                             and product_map[k].promo not in ("", "없음", method.NO_PROMO))
                panel = Counter((r["age"], r["sex"]) for r in batch.values())
                info["panel"] = [{"age": a, "sex": s, "n": v} for (a, s), v in sorted(panel.items())]
            overview.append(info)
        result["detail"]["basket"] = overview
    else:
        weights = explore.population_weights()
        if weights is None:
            raise ValueError("모집단 연령·성별 가중치가 필요합니다.")
        weights = dict(zip(explore.CELLS, weights, strict=True))
        if metric == 3:
            products = {p.key: (p.sku, p.kind) for p in catalog.current() if p.shelf == method.SHELF and p.sku}
            result = reliability.sales_rank(batches[0].values(), weights, products, onsite.load("pos_clean"))
            result["detail"]["category_fit"] = period_fit(batches[0].values(), training=False)
        else:
            survey = onsite.load_json("survey_summary")["concepts"]
            selections, segments, overall = {}, {}, {}
            for concept, batch in zip(CONCEPTS, batches, strict=True):
                name = concept["name"]
                selections[name] = batch.values()
                segments[name] = {(explore.AGES[r["age_band"]], explore.SEXES[r["gender"]]): r["top2"]
                                  for r in survey[name]["segments"]}
                top2 = survey[name]["top2"]
                overall[name] = top2["order_adjusted"] if top2.get("order_adjusted") is not None else top2["weighted"]
            result = reliability.survey_match(selections, segments, overall, weights)
    funnels = {name: journey_funnel(batch) for name, batch in zip(conditions(metric), batches)}
    if any(funnels.values()):
        result["detail"]["journeys"] = {name: funnel for name, funnel in funnels.items() if funnel}
    result["detail"]["usage"] = cost([r for batch in batches for r in batch.values()])
    return result


def period_fit(rows, *, training):
    sales = [r for r in onsite.load("pos_clean") if r["channel"] == "편의점"]
    months = sorted({r["month"] for r in sales})
    if len(months) != 24:
        raise ValueError("24개월 판매 자료가 필요합니다.")
    included = set(months[:12] if training else months[-12:])
    products = {p.key: (p.sku, p.kind, p.promo not in ("", "없음", method.NO_PROMO))
                for p in catalog.current() if p.shelf == method.SHELF}
    period = [{"sku": r["sku"], "kind": catalog._kind(r["category"] or "", r["name"]), "month": int(r["month"][5:7]),
               "promoted": r["promo"] not in ("", None, "없음", method.NO_PROMO), "units": r["units"]}
              for r in sales if r["month"] in included]
    weights = explore.population_weights()
    if not weights:
        raise ValueError("모집단 가중치가 없습니다.")
    return reliability.category_fit(rows, dict(zip(explore.CELLS, weights)), products, period, dev=training)


def occasion_table(plan, batch):
    products = {p.key: (p.kind, p.sku) for p in catalog.current() if p.shelf == method.SHELF}
    sales = [r for r in onsite.load("pos_clean") if r["channel"] == "편의점"]
    months = set(sorted({r["month"] for r in sales})[:12])
    matched = {r["sku"] for r in sales if r["month"] in months and r["units"] > 0}
    counts = {code: Counter() for code, o in method.occasions().items() if o["매대"] == method.SHELF}
    for visit in plan.visits:
        product = batch[visit["방문"]]["product"]
        row = counts[visit["상황 번호"]]
        row["assigned"] += 1
        if product is None:
            continue
        row["n"] += 1
        kind, sku = products.get(product, (None, None))
        group = kind if kind in ("탄산", "커피", "주스") else ("비구매" if product == method.NO_PURCHASE else "기타")
        row[group] += 1
        row["matched"] += sku in matched
    return [{"code": code, "occasion": method.occasions()[code]["상황"],
             **{key: row[key] for key in ("assigned", "n", "탄산", "커피", "주스", "기타", "비구매", "matched")}}
            for code, row in sorted(counts.items())]


def dev_report(batch, repeat=None):
    plan, _ = make_plan("dev-first", len(batch), 70)
    kinds = {p.key: p.kind for p in catalog.current() if p.shelf == method.SHELF}
    top, top3, follows, follows3, visible = 0, 0, 0, 0, 0
    for v in plan.visits:
        row = batch[v["방문"]]
        if row["product"] is None:
            continue
        h = plan.plain["profiles"][v["uuid"]]
        favorites = [h["좋아하는 음료 1순위"], h["2순위"], h["3순위"]]
        _, prompt, _ = method.prompts(plan, v, method.BASELINE)
        visible += int(all(value in prompt for value in favorites if value))
        carbonated = ["탄산음료" in f for f in favorites]
        picked = kinds.get(row["product"]) == "탄산"
        top += carbonated[0]
        top3 += any(carbonated)
        follows += carbonated[0] and picked
        follows3 += any(carbonated) and picked
    tags = Counter(t for r in batch.values() for t in r.get("reason_tags", []))
    assigned = plan.plain.get("purchase_habits", {})
    assignments = [assigned.get(v["uuid"], {}) for v in plan.visits]
    result = {"fit": period_fit(batch.values(), training=True), "occasions": occasion_table(plan, batch),
              "habits": {"favorites_in_prompt": visible, "soda_first": top, "soda_first_picked": follows,
                         "soda_in_top3": top3, "soda_top3_picked": follows3,
                         "with_usual_product": sum(bool(a.get("products")) for a in assignments),
                         "with_monthly_frequency": sum(bool(a.get("has_frequency")) for a in assignments),
                         "picked_usual_product": sum(batch[v["방문"]]["product"] in a.get("products", ())
                                                     for v, a in zip(plan.visits, assignments))},
              "reason_tags": dict(tags.most_common()), "usage": cost(list(batch.values()))}
    if plan.round_number == 10:
        from shelftest import journey
        traces = [r["journey"] for r in batch.values() if r.get("journey")]
        result["journey"] = {"source": "simulated", "visits": len(traces),
                             "noticed": sum(len(t["noticed"]) for t in traces),
                             "considered": sum(len(t["considered"]) for t in traces)}
        try:
            result["online_reference"] = journey.online_reference(onsite.load("journeys_online"))
        except onsite.NoData:
            pass
    if repeat is not None:
        result["retest"] = reliability.retest({k: r["product"] for k, r in batch.items()},
                                               {k: r["product"] for k, r in repeat.items()})
        result["usage"] = cost([*batch.values(), *repeat.values()])
    return result


def journey_funnel(batch):
    from shelftest import journey

    line = next((r["concept_key"] for r in batch.values() if r.get("concept_key")), None)
    return journey.funnel(batch.values(), line) if line else None


def paired_neutral(batches):
    low, high, promo = [{k: row["selected"] for k, row in batch.items()} for batch in batches]
    paired = {k for k in low if all(arm.get(k) is not None for arm in (low, high, promo))}
    funnels = {case: journey_funnel(batch) for case, batch in zip(NEUTRAL_CASES, batches)}
    return {**({"journeys": funnels} if any(funnels.values()) else {}), "name": NEUTRAL["name"], "volume": NEUTRAL["volume"], "container": NEUTRAL["container"],
            "n": len(paired), "prices": [1500, 2000], "promo_price": 1500,
            "price": reliability.paired_change(low, high, paired), "promo": reliability.paired_change(promo, low, paired),
            "usage": cost([row for batch in batches for row in batch.values()])}


def brand_transfers(first, brand, familiar, own):
    valid = {k for k, r in first.items() if r["product"] is not None and k in brand and brand[k]["selected"] is not None}
    buyers = {k for k in valid if brand[k]["selected"]}
    from_own = {k for k in valid if first[k]["product"] in own}
    same = valid & familiar
    return {"n": len(valid), "new_picks": len(buyers), "habit_same_brand": len(same),
            "habit_same_brand_picked": len(same & buyers), "own_before": len(from_own),
            "from_own": len(from_own & buyers),
            "from_own_share_of_new": len(from_own & buyers) / len(buyers) if buyers else None,
            "new_share_of_own_before": len(from_own & buyers) / len(from_own) if from_own else None}


async def dev_study(args):
    claude = args.dev_claude
    backend = "cli" if claude else "codex"
    if os.environ.setdefault("AX_LLM", backend) != backend:
        raise ValueError(f"개발 비교 응답기는 {backend}여야 합니다.")
    args.people = 30 if claude else 100
    config = {**settings(args), "round": method.prompt_round(), "backend": backend}
    folder = OUT / ".dev" / args.dev_study
    with records(folder, config) as db:
        path = folder / "report.json"
        previous = json.loads(path.read_text()) if path.exists() else {}
        guards = args.dev_guard or "brand_transfer" in previous
        if claude:
            runner.RETRIES = 0

        async def sequence(cases, workers):
            return [await collect(db, c, args.people, args.per_cell, workers, recover=not claude) for c in cases]

        baseline_cases = ["dev-first"] if claude else ["dev-first", "dev-repeat"]
        guard_cases = [f"dev-{c}" for c in (*NEUTRAL_CASES, "brand")] if guards else []
        primary_ready = all(sum(r["product"] is not None for r in responses(db, case).values()) == args.people
                            for case in baseline_cases)
        if guard_cases and args.workers >= 4 and not primary_ready:
            guard_workers = max(1, args.workers // 3)
            baseline, checks = await asyncio.gather(sequence(baseline_cases, args.workers - guard_workers),
                                                    sequence(guard_cases, guard_workers))
        else:
            baseline = await sequence(baseline_cases, args.workers)
            checks = await sequence(guard_cases, args.workers)
        first = baseline[0]
        report = dev_report(*baseline)
        if checks:
            *batches, brand = checks
            plan, _ = make_plan("dev-first", args.people, args.per_cell)
            familiar = {v["방문"] for v in plan.visits
                        if BRAND_CHECK["brand"] in plan.plain.get("purchase_habits", {}).get(v["uuid"], {}).get("brands", ())}
            own = {p.key for p in catalog.current() if p.shelf == method.SHELF and p.is_own}
            report["neutral_direction"] = paired_neutral(batches)
            report["brand_transfer"] = {"name": BRAND_CHECK["name"], **brand_transfers(first, brand, familiar, own),
                                        "usage": cost(list(brand.values()))}
            if funnel := journey_funnel(brand):
                report["brand_transfer"]["journey"] = funnel
        report["total_usage"] = cost([row for batch in (*baseline, *checks) for row in batch.values()])
        tmp = folder / "report.tmp"
        tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        tmp.replace(path)
        print(json.dumps(report, ensure_ascii=False), flush=True)


def reference_digest(metric):
    files = {1: (), 2: ("survey_ratings", "survey_summary"), 3: ("population", "pos_clean"),
             4: ("population", "survey_summary")}
    digest = hashlib.sha256()
    for name in files[metric]:
        with (onsite.directory() / onsite.FILENAMES[name]).open("rb") as source:
            digest.update(hashlib.file_digest(source, "sha256").digest())
    return digest.hexdigest()


def save_score(path, config, metric):
    with (path.parent / ".work" / path.stem / "score.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _save_score(path, config, metric)


def _save_score(path, config, metric):
    board = (json.loads(path.read_text()) if path.exists() else
             {"version": path.stem, "llm": "codex", "models": {"shopper": f"{config['model']}/{config['effort']}"},
              "conditions": config, "metrics": [], "caveats": [
                  "제공 자료는 대회용 가상 자료다.",
                  "가상 선택률, 편의점 판매 비중, 조사 구매의향은 서로 다른 관측값이다.",
                  "비용은 직접 API에 같은 입력을 보내고 캐시 할인을 받지 않는다는 가정의 추정치다."]})
    if board["conditions"] != config:
        raise ValueError("같은 판의 점수표에 다른 조건의 결과를 넣을 수 없습니다.")
    order = ["retest", "direction", "sales_rank", "survey_match"]
    metrics = {m["id"]: m for m in board["metrics"]}
    old = metrics.get(metric["id"], {}).get("detail", {}).get("reference_digest")
    if old and old != metric["detail"]["reference_digest"]:
        raise ValueError("참조 조사 또는 판매 자료가 바뀌었습니다. 새 판으로 측정하세요.")
    metrics[metric["id"]] = metric
    board["metrics"] = [metrics[k] for k in order if k in metrics]
    work = path.parent / ".work" / path.stem
    for key, subdir in (("checks", "checks"), ("neutral_direction", "neutral")):
        checked = work / f"{key}.json"
        if checked.exists():
            response_path = work / subdir / "responses.sqlite"
            with closing(sqlite3.connect(response_path.as_uri() + "?mode=ro", uri=True)) as saved:
                supplemental_config = json.loads(saved.execute("SELECT settings FROM manifest").fetchone()[0])
            if any(supplemental_config.get(k) != config.get(k) for k in METHOD_KEYS):
                raise ValueError("점수표와 보조 측정의 방법이 다릅니다. 새 판이 필요합니다.")
            board[key] = json.loads(checked.read_text())
    board["measured_at"] = datetime.fromtimestamp(max(board.get("last_call_epoch", 0), metric["detail"]["last_call_epoch"]), timezone.utc).isoformat()
    board["last_call_epoch"] = datetime.fromisoformat(board["measured_at"]).timestamp()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(board, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    tmp.replace(path)


def save_supplement(folder, key, value, config):
    with (folder / "score.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = OUT / f"{folder.name}.json"
        board = json.loads(path.read_text()) if path.exists() else None
        if board and any(board["conditions"].get(k) != config.get(k) for k in METHOD_KEYS):
            raise ValueError("다른 방법으로 잰 보조 측정은 새 판에 저장하세요.")
        tmp = folder / f"{key}.tmp"
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        tmp.replace(folder / f"{key}.json")
        if board:
            board[key] = value
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(board, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
            tmp.replace(path)


def benchmark_summary(case, rows):
    valid = [r for r in rows if r["selected"] is not None]
    missed = [r for r in valid if not r["selected"]]
    barriers = Counter(reason for r in missed for reason in r.get("barriers", []))
    return {"condition": case, "n": len(valid), "picked": len(valid)-len(missed),
            "non_picks": len(missed), "barrier_responses": sum("barriers" in r for r in missed),
            "with_barrier": sum(bool(r.get("barriers")) for r in missed),
            "barriers": dict(barriers.most_common()), "usage": cost(list(rows))}


async def diagnostics(args, config, folder):
    config = {**config, "people": 100}
    with records(folder / "checks", config) as db:
        summaries = []
        for case in CHECKS:
            rows = (await collect(db, case, 100, args.per_cell, args.workers)).values()
            summary = benchmark_summary(case, rows)
            summaries.append(summary)
            save_supplement(folder, "checks", summaries, config)
            print(json.dumps(summary, ensure_ascii=False), flush=True)
        # ②와 같은 사람·상황의 앞 100명. 이미 유효한 행사 응답이 있으면 다시 묻지 않는다.
        plan, _ = make_plan("promo", 100, args.per_cell)
        ids = [v["방문"] for v in plan.visits]
        official = {}
        if (folder / "responses.sqlite").exists():
            with closing(sqlite3.connect((folder / "responses.sqlite").as_uri() + "?mode=ro", uri=True)) as saved:
                previous = json.loads(saved.execute("SELECT settings FROM manifest").fetchone()[0])
                if all(previous.get(k) == config.get(k) for k in METHOD_KEYS):
                    official = responses(saved, "promo")
        if all(k in official and official[k]["selected"] is not None for k in ids):
            promo = [official[k] for k in ids]
            source = "direction"
        else:
            promo = list((await collect(db, "promo", 100, args.per_cell, args.workers)).values())
            source = "diagnostics"
        summary = {**benchmark_summary("check-promo", promo), "source": source}
        summaries.append(summary)
        save_supplement(folder, "checks", summaries, config)
        print(json.dumps(summary, ensure_ascii=False), flush=True)


async def neutral_direction(args, config, folder):
    config = {**config, "people": 100}
    with records(folder / "neutral", config) as db:
        batches = [await collect(db, case, 100, args.per_cell, args.workers) for case in NEUTRAL_CASES]
        result = paired_neutral(batches)
        save_supplement(folder, "neutral_direction", result, config)
        print(json.dumps(result, ensure_ascii=False), flush=True)


async def main(args):
    if getattr(args, "dev_study", None):
        await dev_study(args)
        return
    if os.environ.setdefault("AX_LLM", "codex") != "codex":
        raise ValueError("실제 측정은 AX_LLM=codex에서만 실행합니다.")
    config = settings(args)
    folder = OUT / ".work" / args.version
    if getattr(args, "neutral_direction", False):
        await neutral_direction(args, config, folder)
        return
    if getattr(args, "diagnostics", False):
        await diagnostics(args, config, folder)
        return
    with records(folder, config) as db:
        notes_file = folder / "notes.json"
        notes = json.loads(notes_file.read_text()) if notes_file.exists() else {}
        for metric in dict.fromkeys(args.only):
            reference = reference_digest(metric)
            batches = [await collect(db, c, args.people, args.per_cell, args.workers) for c in conditions(metric)]
            result = score(metric, batches)
            if result["id"] in notes:
                result["detail"]["run_notes"] = notes[result["id"]]
            if reference_digest(metric) != reference:
                raise ValueError("측정 도중 조사·판매 자료가 바뀌었습니다. 새 판이 필요합니다.")
            result["detail"]["reference_digest"] = reference
            result["detail"]["last_call_epoch"] = max(r["end"] for batch in batches for r in batch.values())
            save_score(OUT / f"{args.version}.json", config, result)
            print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main(arguments()))
