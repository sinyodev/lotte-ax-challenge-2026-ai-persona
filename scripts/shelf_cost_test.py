"""비용을 줄이는 안 B(말은 볼 때만 쓰기)의 시험: 이유 문장을 받지 않아도 손님의 선택이 같은가, 얼마나 줄어드는가.

같은 타깃 손님 100명(20대, 절반은 "집에서 혼자 오전에", 절반은 실제 상황 비중대로)에게 컨셉이 없는 같은 매대를 같은 순서로 다시 묻는다.
    문장 있음  지금처럼 이유의 번호, 기타 이유, 이유 문장을 받는다(다시 물었을 때 원래 얼마나 바뀌는지의 기준)
    문장 없음  고른 번호와 이유의 번호만 받는다
처음의 답(data/experiments/shelf_test/모닝_유자생강_…_섞음_물음.csv의 기준 조건)과 견준다.
문장 없음이 문장 있음만큼만 바뀌면, 문장을 빼도 선택은 달라지지 않는다고 본다.

실행: uv run --with duckdb python scripts/shelf_cost_test.py [--limit 100]
결과: data/experiments/shelf_test/cost_B.csv
"""

import argparse
import csv
import json
import subprocess
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pilot
import shelf_test

FIRST = shelf_test.OUT / "모닝_유자생강_제로_페트_350ml_타깃_19-29_D3_섞음_물음.csv"
PATH = shelf_test.OUT / "cost_B.csv"
ARMS = ("문장 있음", "문장 없음", "문장 있음, 생각 낮춤", "문장 없음, 생각 낮춤")
SENTENCE_RULE = "- 이유 문장은 그 사람이 직접 말하듯 한두 문장으로 쓰세요.\n"
SHORT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["choice_number", "reason_needs"],
    "properties": {k: pilot.CLI_SCHEMA["properties"][k] for k in ("choice_number", "reason_needs")},
}


def ask(system: str, user: str, short: bool, effort: str = "") -> dict:
    if short:
        assert SENTENCE_RULE in system
        system = system.replace(SENTENCE_RULE, "")
    schema = SHORT_SCHEMA if short else pilot.CLI_SCHEMA
    start = time.time()
    done = subprocess.run(
        ["claude", "-p", "--model", pilot.CLI_MODEL, "--system-prompt", system, "--tools", "", "--setting-sources", "",
         "--strict-mcp-config", "--output-format", "json", "--json-schema", json.dumps(schema, ensure_ascii=False), *(["--effort", effort] if effort else [])],
        input=user, capture_output=True, text=True, timeout=300)
    took = time.time() - start
    events = json.loads(done.stdout)
    result = [e for e in (events if isinstance(events, list) else [events]) if e.get("type") == "result"][-1]
    out = result.get("structured_output") or {}
    return {"number": int(out.get("choice_number", -1)), "needs": list(out.get("reason_needs") or []),
            "out_tokens": result.get("usage", {}).get("output_tokens", 0), "seconds": round(took, 1),
            "api_seconds": round(result.get("duration_api_ms", 0) / 1000, 1)}


def main(limit: int, workers: int) -> None:
    args = SimpleNamespace(name="모닝 유자생강 제로 페트 350ml", price=2000, promo="", line="", band="19-29", occasion="D3", mix=True,
                           ask=True, limit=100)
    plain, _ = shelf_test.setup(args)
    visits = plain["visits"][:limit]
    done = {(r["방문"], r["갈래"]) for r in csv.DictReader(open(PATH, encoding="utf-8"))} if PATH.exists() else set()

    def one(job):
        visit, arm = job
        system, user, order = pilot.prompts(plain, visit, shelf_test.BASELINE, 1)  # 처음과 같은 매대 순서
        try:
            a = ask(system, user, arm != "문장 있음", "low" if arm.endswith("낮춤") else "")
            if arm == "문장 있음, 생각 낮춤":
                a = ask(system, user, False, "low")
        except Exception as error:
            print(f"  실패 {visit['방문']} {arm}: {type(error).__name__}: {error}")
            return None
        valid = 0 <= a["number"] <= len(order)
        product = order[a["number"] - 1]["상품명"] if valid and a["number"] > 0 else ("사지 않음" if a["number"] == 0 else "")
        return [visit["방문"], arm, visit["상황 번호"], product, "|".join(a["needs"]), "예" if valid else "아니오", a["out_tokens"],
                a["seconds"], a["api_seconds"]]

    new = not PATH.exists()
    with open(PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if new:
            writer.writerow(["방문", "갈래", "상황 번호", "고른 제품", "이유 욕구", "유효", "출력 토큰", "걸린 초", "모델이 쓴 초"])
        for arm in ARMS:  # 갈래를 따로 돌려 걸린 시간을 같은 조건에서 잰다
            jobs = [(v, arm) for v in visits if (v["방문"], arm) not in done]
            start = time.time()
            with ThreadPoolExecutor(max_workers=workers) as pool:
                rows = [r for r in pool.map(one, jobs) if r]
            writer.writerows(rows)
            f.flush()
            if jobs:
                print(f"{arm}: {len(rows)}건, {time.time() - start:.0f}초(동시에 {workers}명)")
    report()


def report() -> None:
    first = {r["방문"]: r for r in csv.DictReader(open(FIRST, encoding="utf-8")) if r["조건"] == shelf_test.BASELINE and r["유효"] == "예"}
    rows = [r for r in csv.DictReader(open(PATH, encoding="utf-8")) if r["유효"] == "예" and r["방문"] in first]
    kind = {p["상품명"]: p["종류"] for p in pilot.read("shelf_products.csv")}
    kind["사지 않음"] = "사지 않음"
    arms = {a: {r["방문"]: r for r in rows if r["갈래"] == a} for a in ARMS}
    print()
    for arm, got in arms.items():
        n = len(got)
        same = sum(first[v]["고른 제품"] == r["고른 제품"] for v, r in got.items())
        same_kind = sum(kind[first[v]["고른 제품"]] == kind[r["고른 제품"]] for v, r in got.items())
        need = [len(set(first[v]["이유 욕구"].split("|")) & set(r["이유 욕구"].split("|"))) / max(len(set(first[v]["이유 욕구"].split("|")) | set(r["이유 욕구"].split("|"))), 1)
                for v, r in got.items()]
        tokens = sorted(int(r["출력 토큰"]) for r in got.values())
        secs = sorted(float(r["모델이 쓴 초"]) for r in got.values())
        print(f"[{arm}] {n}명 | 처음과 같은 제품 {same}/{n} | 같은 종류 {same_kind}/{n} | 이유의 겹침 {sum(need) / n:.2f}"
              f" | 출력 토큰 가운데 {tokens[n // 2]}, 평균 {sum(tokens) / n:.0f} | 한 번에 가운데 {secs[n // 2]}초, 평균 {sum(secs) / n:.1f}초")
        print("   종류:", ", ".join(f"{k} {v}" for k, v in Counter(kind[r["고른 제품"]] for r in got.values()).most_common()))
    both = set(arms["문장 있음"]) & set(arms["문장 없음"])
    print(f"두 갈래가 서로 같은 제품: {sum(arms['문장 있음'][v]['고른 제품'] == arms['문장 없음'][v]['고른 제품'] for v in both)}/{len(both)}")
    print("   처음의 종류:", ", ".join(f"{k} {v}" for k, v in Counter(kind[first[v]["고른 제품"]] for v in both).most_common()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--workers", type=int, default=8)
    a = parser.parse_args()
    main(a.limit, a.workers)
