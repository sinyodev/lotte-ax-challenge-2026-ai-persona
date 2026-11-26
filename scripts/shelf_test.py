"""매대 테스트의 시험: 새 컨셉 하나를 음료 매대에 넣고 가상 손님에게 묻는다(docs/shelf-test.md).

사전 측정(scripts/pilot.py)의 손님, 상황, 글을 그대로 쓴다. 다른 것은 매대에 컨셉 한 줄이 더 있다는 것뿐이다.
컨셉이 없는 매대의 답은 사전 측정 4차(data/experiments/pilot/음료_cli_r4.csv, 같은 손님 100명에게 3번)를 다시 쓴다.

실행:
    uv run --with duckdb python scripts/shelf_test.py run --name "모닝 유자생강 제로 페트 350ml" --price 2000 --limit 24
    uv run --with duckdb python scripts/shelf_test.py show --name "..." --price 2000      # 손님이 받는 글 한 건
    uv run --with duckdb python scripts/shelf_test.py report --name "..."

결과: data/experiments/shelf_test/<이름>.csv (한 줄이 한 번의 선택. 이어서 돌릴 수 있다)
"""

import argparse
import csv
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pilot

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "experiments" / "shelf_test"
BASE = ROOT / "data" / "experiments" / "pilot" / "음료_cli_r4.csv"
SHELF = "음료"
CONDITION = "컨셉"
BASELINE = "기준"
VIEWS = ["이번에 산다", "다음에 살 수도 있다", "관심 없다"]
BARRIERS = ["지금 상황에 안 맞음", "맛이 끌리지 않음", "가격이 비쌈", "처음 보는 제품이라 망설여짐", "용량이나 용기가 안 맞음",
            "늘 마시는 것이 있음", "어떤 제품인지 모르겠음", "기타"]
ASK = """

[하나 더]
매대의 {number}번 '{name}'은 이번에 새로 나온 제품입니다. 위에서 무엇을 골랐든, 이 제품을 보고 든 생각을 따로 답하세요(new_product).
고르는 일은 이 질문과 상관없이 평소대로 하세요."""
HEADER2 = ["새 제품을 보는 눈", "걸린 점", "새 제품에 대한 말"]
HEADER = ["방문", "조건", "uuid", "상황 번호", "고른 번호", "고른 제품", "이유 욕구", "기타 이유", "이유 문장", "유효", "모델과 프롬프트", "걸린 초"]


def slug(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "_", name).strip("_")


def setup(args):
    """(컨셉이 없는 매대의 ctx, 컨셉을 올린 매대의 ctx). 타깃을 주면 손님을 그 집단에서 새로 뽑고 상황을 하나로 준다."""
    pilot.ROUND = 4
    ctx = pilot.context(SHELF)
    pilot.label(ctx["products"][0], False, SHELF)  # 손님이 보는 이름을 읽어 둔다
    pilot._display[args.name] = f"{args.name} ({args.line})" if args.line else args.name
    if args.band:
        import duckdb

        people = duckdb.sql(f"SELECT uuid, sex, age_band, age, occupation, province, family_type, persona, culinary_persona "
                            f"FROM '{pilot.PERSONAS.as_posix()}' WHERE pool = 'exp' AND age_band = '{args.band}'").fetchall()
        people = [p for p in people if p[0] in ctx["profiles"] and p[0] in ctx["strength"]]
        people.sort(key=lambda p: pilot.unit(p[0], "shelf-test"))
        weights = {}
        for r in pilot.read("occasion_weights.csv"):
            if r["매대"] == SHELF:
                weights.setdefault((r["성별"], r["연령대"]), []).append((r["번호"], float(r["비중(%)"])))

        def occasion_of(i, person):
            """앞의 절반은 컨셉이 겨냥한 상황, 뒤의 절반은 그 집단의 실제 상황 비중대로(args.mix일 때)."""
            if args.occasion and (not args.mix or i < args.limit // 2):
                return args.occasion
            point, running = pilot.unit(person[0], SHELF, "shelf-test") * 100, 0.0
            options = weights[(person[1], person[2])]
            for code, w in options:
                running += w
                if point <= running:
                    return code
            return options[-1][0]

        ctx["visits"] = []
        for i, p in enumerate(people):
            code = occasion_of(i, p)
            ctx["visits"].append({"방문": f"T{i + 1:03d}", "매대": SHELF, "uuid": p[0], "성별": p[1], "연령대": p[2], "상황 번호": code,
                                  "상황": ctx["occasions"][code]["상황"]})
        ctx["text"] = {p[0]: p[3:] for p in people}
    concept = {"매대": SHELF, "상품명": args.name, "가격(원)": str(args.price), "행사": args.promo or "행사 없음", "묶음 수량": "1"}
    return ctx, {**ctx, "products": ctx["products"] + [concept]}


def path_of(args) -> Path:
    tail = ("_문구" if args.line else "") + (f"_타깃_{args.band}_{args.occasion}" if args.band else "") + ("_섞음" if args.mix else "") + ("_물음" if args.ask else "") + (f"_{slug(args.promo)}" if args.promo else "")
    return OUT / f"{slug(args.name)}{tail}.csv"


def answer(system: str, user: str, asked: bool) -> dict:
    """pilot.answer_by_cli와 같되, asked이면 새 제품에 대한 생각(new_product)을 함께 받는다."""
    import json
    import subprocess

    if not asked:
        return pilot.answer_by_cli(system, user)
    schema = json.loads(json.dumps(pilot.CLI_SCHEMA))
    schema["properties"]["new_product"] = {
        "type": "object", "additionalProperties": False, "required": ["view", "barriers", "said"],
        "properties": {
            "view": {"type": "string", "enum": VIEWS, "description": "새 제품을 보는 눈. 위에서 이 제품을 골랐으면 '이번에 산다'"},
            "barriers": {"type": "array", "items": {"type": "string", "enum": BARRIERS}, "description": "사지 않았다면 걸린 점 1~2개. 샀으면 빈 목록"},
            "said": {"type": "string", "description": "새 제품을 보고 든 생각을 손님의 말투로 한 문장"},
        }}
    schema["required"] = schema["required"] + ["new_product"]
    done = subprocess.run(
        ["claude", "-p", "--model", pilot.CLI_MODEL, "--system-prompt", system, "--tools", "", "--setting-sources", "",
         "--strict-mcp-config", "--output-format", "json", "--json-schema", json.dumps(schema, ensure_ascii=False)],
        input=user, capture_output=True, text=True, timeout=300)
    events = json.loads(done.stdout)
    result = [e for e in (events if isinstance(events, list) else [events]) if e.get("type") == "result"][-1]
    out = result.get("structured_output")
    if result.get("is_error") or not isinstance(out, dict):
        return {"number": -1, "needs": [], "other": "", "sentence": "", "tokens": (0, 0)}
    new = out.get("new_product") or {}
    return {"number": int(out["choice_number"]), "needs": list(out["reason_needs"]), "other": out["reason_other"],
            "sentence": out["reason_sentence"], "tokens": (0, 0), "view": new.get("view", ""),
            "barriers": list(new.get("barriers") or []), "said": new.get("said", "")}


def run(args) -> None:
    plain, with_concept = setup(args)
    path = path_of(args)
    OUT.mkdir(parents=True, exist_ok=True)
    done = {(r["방문"], r["조건"]) for r in csv.DictReader(open(path, encoding="utf-8"))} if path.exists() else set()
    conditions = [BASELINE, CONDITION] if args.band else [CONDITION]  # 전체 손님의 컨셉 없는 매대는 사전 측정의 답을 쓴다
    jobs = [(v, c) for v in plain["visits"][: args.limit] for c in conditions if (v["방문"], c) not in done]
    version = f"{pilot.CLI_MODEL}/claude -p/pilot-2/r4+concept"

    def one(job):
        visit, condition = job
        system, user, order = pilot.prompts(with_concept if condition == CONDITION else plain, visit, condition, 1)
        asked = args.ask and condition == CONDITION
        if asked:
            number = next(i + 1 for i, p in enumerate(order) if p["상품명"] == args.name)
            user += ASK.format(number=number, name=pilot._display[args.name])
        start = time.time()
        try:
            a = answer(system, user, asked)
        except Exception as error:
            print(f"  실패 {visit['방문']} {condition}: {type(error).__name__}: {error}")
            return None
        valid = 0 <= a["number"] <= len(order)
        product = order[a["number"] - 1]["상품명"] if valid and a["number"] > 0 else ("사지 않음" if a["number"] == 0 else "")
        return [visit["방문"], condition, visit["uuid"], visit["상황 번호"], a["number"], product, "|".join(a["needs"]), a["other"],
                a["sentence"].replace("\n", " "), "예" if valid else "아니오", version, round(time.time() - start, 1),
                a.get("view", ""), "|".join(a.get("barriers", [])), a.get("said", "").replace("\n", " ")]

    new = not path.exists()
    start = time.time()
    with open(path, "a", newline="", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=args.workers) as pool:
        writer = csv.writer(f)
        if new:
            writer.writerow(HEADER + HEADER2)
        count = 0
        for row in pool.map(one, jobs):
            if row:
                writer.writerow(row)
                f.flush()
                count += 1
    took = time.time() - start
    print(f"{count}건 기록 -> {path.relative_to(ROOT)} (이미 있던 것 {len(done)}건), {took:.0f}초(동시에 {args.workers}명)")
    report(args)


def report(args) -> None:
    all_rows = [r for r in csv.DictReader(open(path_of(args), encoding="utf-8")) if r["유효"] == "예"]
    rows = [r for r in all_rows if r["조건"] == CONDITION]
    if args.band:
        base = {r["방문"]: r["고른 제품"] for r in all_rows if r["조건"] == BASELINE}
    else:
        base = {r["방문"]: r["고른 제품"] for r in csv.DictReader(open(BASE, encoding="utf-8"))
                if r["조건"] == "기준" and r["반복"] == "1" and r["유효"] == "예"}
    info = {p["상품명"]: p for p in pilot.read("shelf_products.csv")}
    rows = [r for r in rows if r["방문"] in base]
    n = len(rows)
    picked = [r for r in rows if r["고른 제품"] == args.name]
    who = f"타깃 손님({args.band}, 상황 {args.occasion})" if args.band else "전체 손님"
    print(f"\n[{who}] {n}명 가운데 {len(picked)}명이 '{args.name}'을 집음")
    counts = Counter(r["고른 제품"] for r in rows)
    ranked = [k for k, _ in counts.most_common() if k != "사지 않음"]
    if picked:
        print(f"매대의 제품 {len(info and [p for p in info.values() if p['매대'] == SHELF]) + 1}개 가운데 {ranked.index(args.name) + 1}번째로 많이 집음")
    print("컨셉을 올린 매대에서 많이 집은 것:", ", ".join(f"{k} {v}" for k, v in counts.most_common(10)))
    print("컨셉이 없는 매대에서 많이 집은 것:", ", ".join(f"{k} {v}" for k, v in Counter(base[r["방문"]] for r in rows).most_common(10)))
    kinds = Counter(info[base[r["방문"]]]["종류"] if base[r["방문"]] in info else "사지 않음" for r in rows)
    print("컨셉이 없는 매대에서 고른 종류:", ", ".join(f"{k} {v}" for k, v in kinds.most_common()))
    moved = Counter()
    for r in picked:
        before = base[r["방문"]]
        kind = "사지 않던 손님" if before == "사지 않음" else ("우리 제품" if info.get(before, {}).get("우리 제품") == "예" else "다른 회사 제품")
        moved[kind] += 1
        print(f"  {r['방문']} | 전에는: {before} | 이유 {r['이유 욕구']} {r['기타 이유']} | {r['이유 문장']}")
    print("컨셉을 집은 손님이 컨셉이 없던 매대에서 집던 것:", dict(moved))
    print(f"컨셉을 올리자 답이 바뀐 손님: {sum(base[r['방문']] != r['고른 제품'] for r in rows)}/{n}"
          " (같은 매대를 다시 물어도 음료는 다섯에 하나쯤 바뀐다. 사전 측정 18.7%)")
    reasons = Counter(c for r in picked for c in r["이유 욕구"].split("|") if c)
    print("컨셉을 집은 이유:", dict(reasons.most_common()))
    names = {c: o["상황"] for c, o in ((o["번호"], o) for o in pilot.read("occasions.csv"))}
    by_occ = Counter(r["상황 번호"] for r in rows)
    got = Counter(r["상황 번호"] for r in picked)
    print("상황마다:", ", ".join(f"{names[c]} {got[c]}/{k}" for c, k in by_occ.most_common()))
    if args.band:
        size = {}
        for r in pilot.read("occasion_weights.csv"):
            if r["매대"] == SHELF and r["연령대"] == args.band:
                size.setdefault(r["번호"], []).append(float(r["비중(%)"]))
        print(f"상황의 크기({args.band}의 음료 자리 가운데, 남녀 평균):", ", ".join(f"{names[c]} {sum(v) / len(v):.0f}%" for c, v in sorted(size.items())))
    if rows and rows[0].get("새 제품을 보는 눈") is not None and any(r.get("새 제품을 보는 눈") for r in rows):
        print("새 제품을 보는 눈:", dict(Counter(r["새 제품을 보는 눈"] for r in rows).most_common()))
        print("걸린 점:", dict(Counter(b for r in rows for b in r["걸린 점"].split("|") if b).most_common()))
        for c in by_occ:
            sub_rows = [r for r in rows if r["상황 번호"] == c]
            print(f"  {names[c]} {len(sub_rows)}명:", dict(Counter(r["새 제품을 보는 눈"] for r in sub_rows).most_common()))
        import random

        for r in random.Random(1).sample(rows, min(10, len(rows))):
            print(f"  · [{names[r['상황 번호']]}] {r['새 제품을 보는 눈']} / {r['걸린 점']} / {r['새 제품에 대한 말']} (집은 것: {r['고른 제품']})")


def show(args) -> None:
    _, ctx = setup(args)
    system, user, _ = pilot.prompts(ctx, ctx["visits"][0], CONDITION, 1)
    print(user)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=["run", "show", "report"])
    parser.add_argument("--name", required=True, help="매대에 적히는 이름(용기와 용량까지)")
    parser.add_argument("--price", type=int, default=2000)
    parser.add_argument("--promo", default="", help="예: 1+1")
    parser.add_argument("--line", default="", help="이름 옆에 적는 한 줄(가격표의 문구). 비우면 이름만")
    parser.add_argument("--band", default="", help="타깃의 연령대(예: 19-29). 주면 그 집단에서 손님을 새로 뽑아 컨셉이 없는 매대도 함께 묻는다")
    parser.add_argument("--occasion", default="", help="타깃 손님에게 주는 상황 번호(예: D3). --band와 함께. 비우면 모두 실제 상황 비중대로")
    parser.add_argument("--mix", action="store_true", help="타깃 손님의 절반은 겨냥한 상황, 절반은 그 집단의 실제 상황 비중대로")
    parser.add_argument("--ask", action="store_true", help="무엇을 고르든 새 제품에 대한 생각을 함께 받는다")
    parser.add_argument("--limit", type=int, default=24)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    {"run": run, "show": show, "report": report}[args.step](args)
