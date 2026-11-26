"""시간을 줄이는 안의 시험: 손님 여러 명을 한 번에 물어도 한 명씩 물었을 때와 같은 답이 나오는가, 얼마나 빨라지는가.

같은 타깃 손님 100명(20대, 절반은 "집에서 혼자 오전에", 절반은 실제 상황 비중대로)에게 컨셉이 없는 같은 매대를 같은 순서로 묻는다.
한 번에 한 명씩이 아니라 5명(또는 10명)을 한 글에 차례로 넣어 묻고, 답도 한 번에 받는다. 손님마다 받는 글(서술, 습관, 상황, 매대 순서)은
한 명씩 물을 때와 한 글자도 다르지 않다.

처음의 답(한 명씩 물은 것)과 견준다. 한 명씩 다시 물었을 때 같은 제품 83/100, 같은 종류 90/100이었으므로(shelf_cost_test.py의 "문장 있음"),
묶어 물은 답이 그 근처면 써도 된다고 본다. 답이 서로 닮아지는지는 한 묶음 안에서 같은 제품을 고른 짝의 수로 본다.

실행: uv run --with duckdb python scripts/shelf_batch_test.py [--sizes 5 10] [--limit 100] [--workers 8]
결과: data/experiments/shelf_test/cost_batch.csv
"""

import argparse
import csv
import json
import subprocess
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations
from types import SimpleNamespace

import pilot
import shelf_test

FIRST = shelf_test.OUT / "모닝_유자생강_제로_페트_350ml_타깃_19-29_D3_섞음_물음.csv"
PATH = shelf_test.OUT / "cost_batch.csv"
RULE = """

[여러 손님]
아래에는 손님 {n}명이 [손님 1]부터 차례로 적혀 있습니다. 서로 모르는 다른 사람이고, 다른 날 다른 매장에 왔습니다.
손님마다 따로, 그 사람이 되어 위의 규칙대로 답하세요. 앞 손님의 선택이 뒤 손님의 선택에 영향을 주면 안 됩니다.
매대의 번호는 손님마다 다릅니다. 그 손님의 매대에 적힌 번호로 답하세요. 답은 answers에 손님 차례대로 {n}개를 넣으세요."""


def schema(n: int) -> dict:
    one = {"type": "object", "additionalProperties": False,
           "required": ["shopper", *pilot.CLI_SCHEMA["required"]],
           "properties": {"shopper": {"type": "integer", "description": "손님의 차례(1부터)"}, **pilot.CLI_SCHEMA["properties"]}}
    return {"type": "object", "additionalProperties": False, "required": ["answers"],
            "properties": {"answers": {"type": "array", "items": one, "minItems": n, "maxItems": n}}}


def ask(system: str, users: list[str]) -> tuple[list[dict], dict]:
    n = len(users)
    body = "\n\n".join(f"[손님 {i + 1}]\n{u}" for i, u in enumerate(users))
    start = time.time()
    done = subprocess.run(
        ["claude", "-p", "--model", pilot.CLI_MODEL, "--system-prompt", system + RULE.format(n=n), "--tools", "", "--setting-sources", "",
         "--strict-mcp-config", "--output-format", "json", "--json-schema", json.dumps(schema(n), ensure_ascii=False)],
        input=body, capture_output=True, text=True, timeout=900)
    took = time.time() - start
    events = json.loads(done.stdout)
    result = [e for e in (events if isinstance(events, list) else [events]) if e.get("type") == "result"][-1]
    answers = (result.get("structured_output") or {}).get("answers") or []
    by = {int(a.get("shopper", 0)): a for a in answers}
    usage = result.get("usage", {})
    return [by.get(i + 1, {}) for i in range(n)], {"out_tokens": usage.get("output_tokens", 0), "seconds": round(took, 1),
                                                    "api_seconds": round(result.get("duration_api_ms", 0) / 1000, 1)}


def main(sizes: list[int], limit: int, workers: int) -> None:
    args = SimpleNamespace(name="모닝 유자생강 제로 페트 350ml", price=2000, promo="", line="", band="19-29", occasion="D3", mix=True,
                           ask=True, limit=100)
    plain, _ = shelf_test.setup(args)
    visits = plain["visits"][:limit]
    done = {(r["방문"], r["갈래"]) for r in csv.DictReader(open(PATH, encoding="utf-8"))} if PATH.exists() else set()

    def one(job):
        arm, group = job
        built = [pilot.prompts(plain, v, shelf_test.BASELINE, 1) for v in group]  # 처음과 같은 글, 같은 매대 순서
        try:
            answers, meta = ask(built[0][0], [u for _, u, _ in built])
        except Exception as error:
            print(f"  실패 {group[0]['방문']}부터 {len(group)}명 {arm}: {type(error).__name__}: {error}")
            return []
        rows = []
        for v, (_, _, order), a in zip(group, built, answers):
            number = int(a.get("choice_number", -1))
            valid = 0 <= number <= len(order)
            product = order[number - 1]["상품명"] if valid and number > 0 else ("사지 않음" if number == 0 else "")
            rows.append([v["방문"], arm, group[0]["방문"], v["상황 번호"], product, "|".join(a.get("reason_needs") or []),
                         a.get("reason_sentence", ""), "예" if valid else "아니오", meta["out_tokens"], meta["seconds"], meta["api_seconds"]])
        return rows

    new = not PATH.exists()
    with open(PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if new:
            writer.writerow(["방문", "갈래", "묶음", "상황 번호", "고른 제품", "이유 욕구", "이유 문장", "유효", "묶음의 출력 토큰", "묶음이 걸린 초",
                             "모델이 쓴 초"])
        for size in sizes:
            arm = f"{size}명씩"
            todo = [v for v in visits if (v["방문"], arm) not in done]
            jobs = [(arm, todo[i:i + size]) for i in range(0, len(todo), size)]
            start = time.time()
            with ThreadPoolExecutor(max_workers=workers) as pool:
                rows = [r for group in pool.map(one, jobs) for r in group]
            writer.writerows(rows)
            f.flush()
            if jobs:
                print(f"{arm}: {len(rows)}건, 전체 {time.time() - start:.0f}초(동시에 {workers}묶음)")
    report()


def report() -> None:
    first = {r["방문"]: r for r in csv.DictReader(open(FIRST, encoding="utf-8")) if r["조건"] == shelf_test.BASELINE and r["유효"] == "예"}
    rows = [r for r in csv.DictReader(open(PATH, encoding="utf-8")) if r["유효"] == "예" and r["방문"] in first]
    kind = {p["상품명"]: p["종류"] for p in pilot.read("shelf_products.csv")}
    kind["사지 않음"] = "사지 않음"
    print()
    for arm in dict.fromkeys(r["갈래"] for r in rows):
        got = {r["방문"]: r for r in rows if r["갈래"] == arm}
        n = len(got)
        same = sum(first[v]["고른 제품"] == r["고른 제품"] for v, r in got.items())
        same_kind = sum(kind[first[v]["고른 제품"]] == kind[r["고른 제품"]] for v, r in got.items())
        groups: dict[str, list[str]] = {}
        for v, r in got.items():
            groups.setdefault(r["묶음"], []).append(v)
        pairs = [(a, b) for g in groups.values() for a, b in combinations(g, 2)]
        twin = sum(got[a]["고른 제품"] == got[b]["고른 제품"] for a, b in pairs)
        twin_first = sum(first[a]["고른 제품"] == first[b]["고른 제품"] for a, b in pairs)
        secs = sorted({(r["묶음"]): float(r["묶음이 걸린 초"]) for r in got.values()}.values())
        tokens = sum({r["묶음"]: int(r["묶음의 출력 토큰"]) for r in got.values()}.values())
        print(f"[{arm}] {n}명 | 처음과 같은 제품 {same}/{n} | 같은 종류 {same_kind}/{n} | 고른 제품의 가짓수 {len({r['고른 제품'] for r in got.values()})}"
              f"(처음 {len({first[v]['고른 제품'] for v in got})}) | 한 묶음 안에서 같은 제품을 고른 짝 {twin}/{len(pairs)}(처음 {twin_first})"
              f" | 묶음 하나에 가운데 {secs[len(secs) // 2]}초 | 한 명에 출력 토큰 {tokens / n:.0f}")
        print("   종류:", ", ".join(f"{k} {v}" for k, v in Counter(kind[r["고른 제품"]] for r in got.values()).most_common()))
        print("   처음의 종류:", ", ".join(f"{k} {v}" for k, v in Counter(kind[first[v]["고른 제품"]] for v in got).most_common()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", type=int, nargs="+", default=[5])
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--workers", type=int, default=8)
    a = parser.parse_args()
    main(a.sizes, a.limit, a.workers)
