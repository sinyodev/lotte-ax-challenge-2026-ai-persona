"""Luna 9차 구매 습관 입력을 바꾸고 저장한 대조군과 비교한다. --paired는 두 독립 실험을 동시에 실행한다."""

import argparse
import asyncio
from collections import Counter
from contextlib import closing
import hashlib
import json
import os
import sqlite3
from types import SimpleNamespace

import reliability4 as study
from calibrate import habits


def prepare_variant(plan, condition, saved_digest, variant, ref):
    digest = hashlib.sha256()
    changed = 0
    kinds = {product[0]: kind for kind, entries in ref.products.items() for product, _ in entries}
    assigned = Counter()
    old_assigned = Counter()
    for v in plan.visits:
        uid, key = v["uuid"], v["방문"]
        system, prompt, order = study.method.prompts(plan, v, condition)
        digest.update(json.dumps([uid, key, system, prompt], ensure_ascii=False).encode())
        original = plan.plain["purchase_habits"][uid]
        old_lines = original.get("lines", [])
        old_products = original.get("products", [])
        if variant == "without-usual-names":
            removed = [line for line in old_lines if line.startswith("평소 자주 사는 제품은 ")]
            if len(removed) != int(bool(old_products)):
                raise ValueError("기존 상품 이름의 배정과 문장이 일치하지 않습니다.")
            revised = {**original, "lines": [line for line in old_lines if line not in removed]}
        else:
            person = plan.plain["profiles"][uid]
            favorites = [person[k] for k in ("좋아하는 음료 1순위", "2순위", "3순위")]
            revised = habits.assign(ref, uid, v["연령대"], v["성별"], favorites, 1., variant=variant)
            new_products = revised.get("products", [])
            if len(old_products) != len(new_products):
                raise ValueError("방문별 평소 상품 배정 수가 바뀌었습니다.")
            if variant == "paired-lines" and any(original.get(k) != revised.get(k) for k in ("products", "brands")):
                raise ValueError("표현만 바꿔야 하는 조건의 배정 상품이 달라졌습니다.")
            if variant == "frequency-kinds":
                old_frequency = [s for s in old_lines if s.startswith("한 달에 보통 ")]
                new_frequency = [s for s in revised.get("lines", []) if s.startswith("한 달에 보통 ")]
                if old_frequency != new_frequency:
                    raise ValueError("종류만 바꿔야 하는 조건의 월 구매 횟수가 달라졌습니다.")
            old_assigned.update(kinds[p] for p in old_products)
            assigned.update(kinds[p] for p in new_products)
        new_lines = revised.get("lines", [])
        expected = prompt
        if old_lines != new_lines:
            prefix = "[평소 습관]\n"
            old = prefix + "".join(s + "\n" for s in old_lines)
            new = prefix + "".join(s + "\n" for s in new_lines)
            if prompt.count(old) != 1:
                raise ValueError("위치를 특정할 수 없는 구매 습관 입력입니다.")
            expected = prompt.replace(old, new, 1)
            changed += 1
        plan.plain["purchase_habits"][uid] = revised
        if study.method.prompts(plan, v, condition) != (system, expected, order):
            raise ValueError("구매 습관 외에 손님·매대·질문이 바뀌었습니다.")
    if digest.hexdigest() != saved_digest:
        raise ValueError("재구성한 대조군의 질문이 저장된 질문과 다릅니다.")
    audit = {"changed_prompts": changed}
    if variant != "without-usual-names":
        audit.update(control_assigned_kinds=dict(old_assigned), assigned_kinds=dict(assigned))
    return audit


def summarize_fit(batch):
    fit = study.period_fit(batch.values(), training=True)
    return {k: fit[k] for k in ("n", "bought", "matched_picks", "n_products", "rho", "gap", "kinds_matched", "pos_matched")}


async def run_trial(root, config, digest, control_fit, variant, prepared, audit, workers):
    folder = root / f"luna-low-r9-{variant}"
    with study.records(folder, {**config, "control_digest": digest, "variant": variant}) as db:
        trial = await study.collect(db, f"dev-{variant}", 100, 70, workers, prepared_plan=prepared)
        report = {"assigned": len(prepared[0].visits), **audit, "usage": study.cost(list(trial.values())),
                  "control": control_fit, "trial": summarize_fit(trial)}
        tmp = folder / "report.tmp"
        tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        tmp.replace(folder / "report.json")
        print(variant, json.dumps(report, ensure_ascii=False, allow_nan=False), flush=True)


async def main(paired=False):
    os.environ.update(AX_LLM="codex", AX_MODEL_SHOPPER="gpt-6-luna", AX_EFFORT_SHOPPER="low", AX_SHOPPER_ROUND="9")
    config = {**study.settings(SimpleNamespace(people=100, per_cell=70)), "round": 9, "backend": "codex"}
    root = study.OUT / ".dev"
    control_db = (root / "luna-low-r9" / "responses.sqlite").resolve()
    with closing(sqlite3.connect(control_db.as_uri() + "?mode=ro", uri=True)) as saved:
        if json.loads(saved.execute("SELECT settings FROM manifest").fetchone()[0]) != config:
            raise ValueError("대조군의 패널·매대·모델이 현재 조건과 다릅니다.")
        digest, = saved.execute("SELECT digest FROM plans WHERE scenario='dev-first'").fetchone()
        control = study.responses(saved, "dev-first")
    arms = [("frequency-kinds", 4), ("paired-lines", 3)] if paired else [("without-usual-names", 7)]
    plans = []
    ref = habits.reference()
    for variant, workers in arms:
        plan, condition = study.make_plan("dev-first", 100, 70)
        if set(control) != {v["방문"] for v in plan.visits} or any(r["product"] is None for r in control.values()):
            raise ValueError("대조군의 유효한 첫 응답 100건이 필요합니다.")
        audit = prepare_variant(plan, condition, digest, variant, ref)
        plans.append((variant, (plan, condition), audit, workers))
        print(f"{variant}: 대조군 입력 100건 확인, 질문이 바뀐 손님 {audit['changed_prompts']}명", flush=True)
    control_fit = summarize_fit(control)
    await asyncio.gather(*(run_trial(root, config, digest, control_fit, *args) for args in plans))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paired", action="store_true", help="구매 횟수에 따른 종류 배정과 종류별 문장을 각각 100명에게 시험")
    asyncio.run(main(parser.parse_args().paired))
