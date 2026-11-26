"""가짜 신제품(플라시보) 검사: 매대의 기존 제품 하나를 빼고 '컨셉'으로 다시 올려, 원래 받던 선택 수와 견준다.

컨셉을 보이는 방식이 공정하면 같은 손님에게서 비슷한 수가 나와야 한다. 몇 배로 나오면 보이는 방식이 부풀리는 것이다.
- 손님: 평가 패널 19~29세의 앞 N명(매대 테스트와 같은 차례), 방문 달은 5~9월(밀키스 화채와 같은 시즌).
- 기준: 컨셉이 없는 매대에서 그 제품을 고른 사람 수(같은 손님, 저장된 기준 답이 있으면 다시 쓴다).
- 검사: 그 제품을 매대에서 빼고 컨셉과 같은 길(concept_row + enrich_concept)로 다시 올린 매대.
  --method blind(지금 방식, 기본) 또는 marked(옛 방식: 같은 글에서 새_상품_번호를 짚고 묻는다).
- 합격: 검사의 수가 기준의 0.5~2배 안이고, 두 비율 차이의 95% 구간이 0을 품는다(같은 손님끼리 짝지은 비교).
모델은 Codex 워크스페이스(AX_LLM=codex)만 쓴다. 응답은 app/server/store/placebo/에 저장해 끊겨도 이어서 돈다(저장소에 올리지 않음).

실행: uv run --project app/server --no-env-file python scripts/placebo_check.py [--n 100] [--method blind|marked] [--workers 8]
"""

import argparse
import asyncio
import hashlib
import json
import os
from math import sqrt
from pathlib import Path
import sys

SERVER = Path(__file__).resolve().parents[1] / "app" / "server"
sys.path.insert(0, str(SERVER))
os.environ.update(AX_LLM="codex", AX_MODEL_SHOPPER="gpt-6-luna", AX_EFFORT_SHOPPER="low", AX_SHOPPER_ROUND="11")
os.chdir(SERVER)

from llm.models import model_for  # noqa: E402
from shelftest import catalog, method, runner, shopper_json, store  # noqa: E402
from tools import shelf_items  # noqa: E402

OUT = SERVER / "store" / "placebo"
DEFAULT_PRODUCT = "pos:CS01:칠성사이다 500mL PET"  # 20대 300명 기준 매대에서 20명(4번째)
SEASON = "5~9월 한정"


def plans(n: int, key: str, choice: str | None):
    product = next(p for p in catalog.current() if p.key == key)
    people = list(method.people("19-29", None)[:n])
    line = method.line_name(product.name.split(" ")[0], product.container, product.volume)
    plan = method.plan("19-29", None, None, n, line, product.price, None, participants=people, season=SEASON)
    plan.with_concept["products"] = [r for r in plan.with_concept["products"] if r["상품명"] != key]
    plan.with_concept["fulfills"] = {k: v for k, v in plan.with_concept["fulfills"].items() if k != key}
    row = product.row
    shelf_items.enrich_concept(plan, {"volume": product.volume, "container": product.container,
                                      "kind": row.get("종류"), "sugar_caffeine": row.get("당") or ""})
    plan.with_concept["concept_prompt_version"] = runner.CONCEPT_PROMPT_VERSION
    if choice:
        plan.with_concept["choice_method"] = choice
    return product, plan


async def ask_all(plan, cond, visits, path, workers):
    done = {}
    if path.exists():
        for line in path.open():
            r = json.loads(line)
            done[r["visit"]] = r
    model = model_for("shopper").model
    sem = asyncio.Semaphore(workers)

    async def one(v):
        async with sem:
            row, _ = await runner._ask(plan, v, cond, model)
        if row:
            rec = {"visit": v["방문"], "product": row["product"]}
            done[v["방문"]] = rec
            with path.open("a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    for _ in range(2):
        await asyncio.gather(*(one(v) for v in visits if v["방문"] not in done))
    return done


def paired_ci(pairs):
    """같은 손님의 (기준에서 골랐나, 검사에서 골랐나) 짝으로 비율 차이의 95% 구간(정규 근사, %p)."""
    n = len(pairs)
    d = [b - a for a, b in pairs]
    mean = sum(d) / n
    var = sum((x - mean) ** 2 for x in d) / max(n - 1, 1)
    half = 1.96 * sqrt(var / n)
    return round(100 * (mean - half), 1), round(100 * (mean + half), 1)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--product", default=DEFAULT_PRODUCT)
    ap.add_argument("--method", choices=("blind", "marked"), default="blind")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    choice = shopper_json.BLIND if a.method == "blind" else None
    product, plan = plans(a.n, a.product, choice)
    OUT.mkdir(parents=True, exist_ok=True)
    visits = plan.visits
    # 컨셉 쪽 글이 바뀌면 저장된 답을 다시 쓰지 않는다(첫 손님의 글로 지문을 만든다)
    system, user, _ = method.prompts(plan, visits[0], method.CONCEPT)
    mark = hashlib.sha256((system + user).encode()).hexdigest()[:8]
    tag = f"{method.shelf_v()}-{a.n}-{product.key.split(':')[1] if ':' in product.key else product.key}-{mark}"
    cache = store.baselines(method.shelf_v(), model_for("shopper").model)
    base = {}
    for v in visits:
        hit = cache.get((v["uuid"], method.baseline_occasion(v)))
        if hit:
            base[v["방문"]] = {"visit": v["방문"], "product": hit["product"]}
    missing = [v for v in visits if v["방문"] not in base]
    if missing:
        base.update(await ask_all(plan, method.BASELINE, missing, OUT / f"{tag}-base.jsonl", a.workers))
    test = await ask_all(plan, method.CONCEPT, visits, OUT / f"{tag}-{a.method}.jsonl", a.workers)
    both = [v["방문"] for v in visits if v["방문"] in base and v["방문"] in test]
    pairs = [(int(base[k]["product"] == product.key), int(test[k]["product"] == plan.line)) for k in both]
    before, after = sum(p[0] for p in pairs), sum(p[1] for p in pairs)
    low, high = paired_ci(pairs)
    ratio = after / before if before else None
    ok = before > 0 and 0.5 <= ratio <= 2 and low <= 0 <= high
    print(json.dumps({"product": product.name, "method": a.method, "n": len(pairs),
                      "baseline_picks": before, "placebo_picks": after,
                      "ratio": round(ratio, 2) if ratio else None, "diff_ci_pp": [low, high],
                      "pass": ok}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
