"""사전 측정: 가상 손님 100명에게 같은 매대를 3번 보여주고, 한 가지를 바꾼 매대를 1번 보여준다.

실행:
    uv run --with duckdb python scripts/pilot.py visits                 # 방문 만들기(손님에게 상황 배정)
    uv run --with duckdb python scripts/pilot.py show 음료              # 가상 손님이 받는 글 한 건 보기
    uv run --with duckdb python scripts/pilot.py run 음료 --responder needs    # 모델 없이 욕구 점수로 고르기(흐름 점검, 견줄 기준)
    uv run --with duckdb --with anthropic --with pydantic python scripts/pilot.py run 음료 --responder claude
    uv run --with duckdb python scripts/pilot.py run 음료 --responder cli      # API 키 없이 Claude Code 명령줄(요금제 로그인)로 부르기
    uv run --with duckdb python scripts/pilot.py analyze 음료 --responder claude

재는 것 (docs/simulation.md 1절):
    재검사 흔들림  같은 손님이 같은 매대(기준)에서 답을 바꾸는 비율
    엇갈림 비율    매대를 바꿨을 때(변형) 답이 달라지는 비율. 본 실험의 방문 수를 이 값으로 정한다
함께 보는 것:
    방향성        행사를 뗀 제품의 선택이 줄어드는가
    기존 시장 재현 고른 음료 종류의 비율이 국민건강영양조사의 상황별 비율과 닮았는가
    순서 쏠림      매대 앞쪽 번호를 더 고르는가(진열 순서는 부를 때마다 섞는다)
    획일화        가장 많이 고른 제품 하나에 몰리는가
    모순          이유로 든 욕구를 고른 제품이 채우지 못하거나 거스르는가

조건:
    기준  지금의 매대 그대로. 3번 반복.
    변형  우리 제품 하나의 행사 표시를 뗀 매대. 1번. (지어낸 신제품을 쓰지 않고 있는 제품의 판매조건만 바꾼다.)

가상 손님에게 보여주는 것: 생활 서술, 조사에서 입힌 평소 습관, 오늘의 상황, 매대에서 보이는 것(이름, 용량, 가격, 행사).
보여주지 않는 것: 손님의 욕구 세기, 채워준다 연결, 상황이 바꾸는 욕구. 답을 받은 뒤 검사에만 쓴다.

결과: data/experiments/pilot/<매대>_<응답자>.csv  (한 줄이 한 번의 선택. 이어서 돌릴 수 있다)
"""

import argparse
import csv
import hashlib
import math
import random
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OURS = ROOT / "data" / "ours"
OUT = ROOT / "data" / "experiments" / "pilot"
PERSONAS = ROOT / "data" / "clean" / "personas_8000.parquet"
SEED = "pilot-2026-11-17"
VISITS_PER_SHELF = 100
REPEATS = 3
# 변형 조건에서 바꾸는 것. 1차는 우리 제품의 행사를 뗐는데 원래 고르는 손님이 거의 없어 효과를 볼 수 없었다.
# 2차는 1차에서 가장 많이 고른 제품을 바꾼다. 음료는 행사를 떼고, 주류는 행사가 없는 제품이라 가격을 올린다(1,900원 -> 2,300원).
VARIANTS = {
    # 0차: 관계 없이 묻는 견줄 기준. 손님의 생활 서술과 매대만 준다. 조사에서 입힌 습관과 오늘의 상황은 주지 않는다. 매대와 변형은 3차와 같다.
    0: {"음료": ("롯데)더하다보리차P500ml", None), "주류": ("참이슬 후레쉬(360ml)", 2300)},
    1: {"음료": ("롯데)칠성사이다제로P500", None), "주류": ("롯데)클라우드500ml캔", None)},
    2: {"음료": ("롯데)더하다보리차P500ml", None), "주류": ("참이슬 후레쉬(360ml)", 2300)},
    3: {"음료": ("롯데)더하다보리차P500ml", None), "주류": ("참이슬 후레쉬(360ml)", 2300)},  # 2차와 같은 조건. 음료 매대에 우유류 10개와 생수 2개를 보강한 뒤 다시 잰다
    4: {"음료": ("롯데)더하다보리차P500ml", None), "주류": ("참이슬 후레쉬(360ml)", 2300)},  # 3차와 같고 상품명만 손님이 보는 이름으로 바꾼다
    5: {"음료": ("롯데)더하다보리차P500ml", None), "주류": ("참이슬 후레쉬(360ml)", 2300)},  # 4차에서 행사 표시를 모두 뗀다(행사 탓인지 가리는 진단)
    6: {"음료": ("롯데)더하다보리차P500ml", None), "주류": ("참이슬 후레쉬(360ml)", 2300)},  # 방문 달·월평균 기온
    7: {"음료": ("롯데)더하다보리차P500ml", None), "주류": ("참이슬 후레쉬(360ml)", 2300)},  # 6차에 평소 선호 순위와 행사 뜻을 명시
}
VARIANTS[10] = VARIANTS[8] = VARIANTS[9] = VARIANTS[7]  # 7차와 같은 매대, 조사·판매로 배정한 평소 구매 습관만 추가
TEXT = {0: 2, 1: 1, 2: 2, 3: 2, 4: 2, 5: 2, 6: 2, 7: 2, 8: 2, 9: 2, 10: 2}
DISPLAY_FROM = 4  # 이 차수부터 전산 표기 대신 손님이 보는 이름을 보여준다(data/ours/shelf_display_names.csv)
NO_PROMO = {5}    # 행사 표시를 모두 떼는 차수
_display = {}  # 차수마다 쓰는 글의 판
ROUND = 4  # 실행할 때 --round로 바꾼다
# 1차는 "마실 것을 사러 편의점에 들렀습니다"라고 적어 800번 모두 무언가를 샀다. 2차는 살지 말지도 손님이 정한다.
SITUATION_END = {
    1: "그때 마실 것을 사러 편의점에 들렀습니다.",
    2: "이럴 때 마실 것을 지금 편의점에서 살지, 집에 있는 것이나 그 자리(음식점, 카페, 일터)에서 나오는 것으로 해결할지는 당신이 정합니다. 지금 편의점 매대 앞에 서 있습니다.",
}
BUY_RULE = {
    1: "- 꼭 사야 하는 것은 아닙니다. 살 것이 없으면 0번(사지 않음)을 고르세요.",
    2: "- 꼭 사야 하는 것은 아닙니다. 이 사람이 이 상황에서 편의점에서 사지 않을 것 같거나 마음에 드는 것이 없으면 0번(사지 않음)을 고르고, 이유 문장에 왜 사지 않는지 적으세요.",
}
# aT 식품산업통계정보의 품목을 우리 매대의 종류로 옮긴다.
FIS_KIND = {"탄산음료": "탄산", "과채음료": "주스", "액상차": "차", "액상커피": "커피", "두유": "우유·단백", "단백질음료": "우유·단백",
            "우유": "우유·단백", "발효유": "우유·단백", "탁주": "막걸리", "맥주": "맥주", "소주": "소주"}
DEGREE = {"잘 채움": 2, "조금 채움": 1, "못 채움": 0, "거스름": -1}

SYSTEM = """당신은 한국의 편의점에 들른 손님 한 사람입니다. 아래에 주어지는 사람이 되어, 그 사람이라면 지금 이 매대에서 무엇을 살지 정하세요.

지킬 것
- 주어진 사람의 형편, 습관, 지금의 상황에 맞게 고르세요. 가장 좋은 제품을 추천하는 것이 아니라 그 사람이 실제로 집을 것을 고릅니다.
- 매대에 적힌 것만 보고 판단하세요. 적히지 않은 정보를 지어내지 마세요.
{buy_rule}
- 번호의 순서에는 뜻이 없습니다.
- 이유는 아래 목록에서 1~3개 고르고, 목록에 없는 이유는 따로 적으세요.
- 이유 문장은 그 사람이 직접 말하듯 한두 문장으로 쓰세요.

이유 목록
{needs}"""


def read(name: str) -> list:
    return list(csv.DictReader(open(OURS / name, encoding="utf-8")))


def unit(*parts) -> float:
    """md5로 만든 0~1 사이의 수. 같은 입력에는 늘 같은 값이 나온다."""
    return int(hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()[:12], 16) / 16 ** 12


def load_shelf(shelf: str) -> list:
    return [p for p in read("shelf_products.csv") if p["매대"] == shelf]


def label(p: dict, variant: bool, shelf: str) -> str:
    promo = p["행사"]
    amount = int(p["가격(원)"])
    target, new_price = VARIANTS[ROUND][shelf]
    if variant and p["상품명"] == target:
        if new_price:
            amount = new_price
        else:
            promo = "행사 없음"
    if ROUND in NO_PROMO and int(p["묶음 수량"]) == 1:
        promo = "행사 없음"
    name = p["상품명"]
    if ROUND >= DISPLAY_FROM:
        if not _display:
            _display.update({r["상품명"]: r["손님이 보는 이름"] for r in read("shelf_display_names.csv")})
        name = _display[name]
    pack = int(p["묶음 수량"])
    price = f"{amount:,}원"
    if pack > 1:
        note = f"{pack}개 묶음 {price}"
    elif promo.startswith("행사 없음"):
        note = price
    elif promo == "할인행사":
        note = f"{price}, 할인 행사 중"
    else:
        note = f"{price}, {promo} 행사"
    return f"{name} — {note}"


def build_visits() -> None:
    import duckdb

    needs = {r["uuid"]: r for r in read("persona_needs.csv")}
    weights = defaultdict(list)
    for r in read("occasion_weights.csv"):
        weights[(r["매대"], r["성별"], r["연령대"])].append((r["번호"], r["상황"], float(r["비중(%)"])))
    people = duckdb.sql(f"SELECT uuid, sex, age_band FROM '{PERSONAS.as_posix()}' WHERE pool = 'dev'").fetchall()
    people.sort(key=lambda p: unit(p[0], SEED))
    rows = []
    for shelf in ("음료", "주류"):
        picked = [p for p in people if shelf == "음료" or needs[p[0]]["술을 마심"] == "예"][:VISITS_PER_SHELF]
        for i, (uuid, sex, band) in enumerate(picked):
            point, running = unit(uuid, shelf, SEED) * 100, 0.0
            options = weights[(shelf, sex, band)]
            code, name = options[-1][:2]
            for c, n, w in options:
                running += w
                if point <= running:
                    code, name = c, n
                    break
            rows.append([f"{'D' if shelf == '음료' else 'L'}{i + 1:03d}", shelf, uuid, sex, band, code, name])
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OURS / "visits_pilot.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["방문", "매대", "uuid", "성별", "연령대", "상황 번호", "상황"])
        writer.writerows(rows)
    print(f"방문 {len(rows)}건 -> data/ours/visits_pilot.csv")
    for shelf in ("음료", "주류"):
        print(f"  {shelf}: " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(r[6] for r in rows if r[1] == shelf).items(), key=lambda x: -x[1])))


def context(shelf: str) -> dict:
    """한 매대의 실험에 필요한 것을 모두 읽는다."""
    import duckdb

    visits = [v for v in read("visits_pilot.csv") if v["매대"] == shelf]
    ids = ", ".join(f"'{v['uuid']}'" for v in visits)
    text = {u: (age, job, province, family, persona, culinary) for u, age, job, province, family, persona, culinary in duckdb.sql(
        f"SELECT uuid, age, occupation, province, family_type, persona, culinary_persona FROM '{PERSONAS.as_posix()}' WHERE uuid IN ({ids})").fetchall()}
    profiles = {r["uuid"]: r for r in read("persona_profiles.csv")}
    needs = [n for n in read("needs.csv") if n["상태"] != "보류" and n["범위"] in ("공통", shelf)]
    occasions = {o["번호"]: o for o in read("occasions.csv")}
    fulfills = defaultdict(dict)
    for r in read("fulfills.csv"):
        fulfills[r["상품명"]][r["욕구 번호"]] = r["정도"]
    shifts = defaultdict(dict)
    shift_sources = defaultdict(dict)
    for r in read("occasion_needs.csv"):
        shifts[r["번호"]][r["욕구 번호"]] = float(r["바뀌는 크기(-2~+2)"])
        shift_sources[r["번호"]][r["욕구 번호"]] = r["근거 종류"]
    return {"shelf": shelf, "visits": visits, "text": text, "profiles": profiles, "needs": needs, "occasions": occasions,
            "products": load_shelf(shelf), "fulfills": fulfills, "shifts": shifts, "shift_sources": shift_sources,
            "strength": {r["uuid"]: r for r in read("persona_needs.csv")}}


def shelf_order(products: list, visit: dict, condition: str, repeat: int, round_number: int) -> list:
    if round_number == 10:
        return sorted(products, key=lambda p: unit(visit["uuid"], "journey-order-v1", p["상품명"]))
    return sorted(products, key=lambda p: unit(visit["방문"], condition, repeat, p["상품명"], SEED))


def shopper_system(needs: list, round_number: int) -> str:
    reasons = "\n".join(f"- {n['번호']}: {n['욕구']} ({n['풀어 쓴 설명']})" for n in needs)
    return SYSTEM.format(buy_rule=BUY_RULE[TEXT[round_number]], needs=reasons)


def prompts(ctx: dict, visit: dict, condition: str, repeat: int) -> tuple[str, str, list]:
    """가상 손님이 받는 글과, 이번에 섞은 매대 순서를 돌려준다."""
    shelf = ctx["shelf"]
    order = shelf_order(ctx["products"], visit, condition, repeat, ROUND)
    age, job, province, family, persona, culinary = ctx["text"][visit["uuid"]]
    h = ctx["profiles"][visit["uuid"]]
    occasion = ctx["occasions"][visit["상황 번호"]]
    system = shopper_system(ctx["needs"], ROUND)
    favorites = list(dict.fromkeys(x for x in (h["좋아하는 음료 1순위"], h["2순위"], h["3순위"]) if x))
    habits = [f"좋아하는 음료: {', '.join(favorites)}", f"제로 음료: {h['제로 음료 빈도']}"]
    if shelf == "주류":
        habits = [f"술: {h['음주 빈도']}, 가장 좋아하는 술은 {h['좋아하는 술']}", f"제로 주류: {h['제로 주류 빈도']}"]
    habits.append(f"다이어트 관심 {h['다이어트 관심(1~5)']}/5, 건강 관심 {h['건강 관심(1~5)']}/5, 규칙적 운동 {h['규칙적 운동']}")
    user = "\n".join([
        "[당신]",
        f"{visit['성별']}, {age}세, {province} 거주, 직업 {job}, 가구 {family}",
        persona or "",
        culinary or "",
        "",
        *(["지금 편의점 매대 앞에 서 있습니다. 살지 말지는 당신이 정합니다.", ""] if ROUND == 0 else [
            "[평소 습관]",
            *habits,
            "",
            "[지금의 상황]",
            f"{occasion['상황']}: {occasion['풀어 쓴 설명']}. {SITUATION_END[TEXT[ROUND]]}",
            "",
        ]),
        f"[{shelf} 매대]",
        "0. 사지 않음",
        *[f"{i + 1}. {label(p, condition == '변형', shelf)}" for i, p in enumerate(order)],
    ])
    if ROUND >= 6 and "visit_month" in visit:
        month = f"이번 방문은 {visit['visit_month']}월입니다."
        if visit.get("temp_c") is not None:
            month += f" 이 달의 평균 기온은 {visit['temp_c']:g}도입니다."
        user = user.replace("[지금의 상황]\n", f"[지금의 상황]\n{month}\n", 1)
    if ROUND in (7, 8, 9, 10) and shelf == "음료":
        ranked = (h["좋아하는 음료 1순위"], h["2순위"], h["3순위"])
        habits_first = " · ".join(f"{i}순위 {v}" for i, v in enumerate(ranked, 1) if v)
        user = user.replace(f"좋아하는 음료: {', '.join(favorites)}\n", "", 1)
        user = (f"[평소 음료 선호 순서]\n{habits_first}\n"
                "오늘 상황과 평소 고르는 방식에 따라 직접 결정하세요.\n\n" + user)
        user = user.replace(f"[{shelf} 매대]\n",
                            f"[{shelf} 매대]\n1+1은 한 개 값으로 두 개, 2+1은 두 개 값으로 세 개입니다.\n", 1)
        assigned = ctx.get("purchase_habits", {}).get(visit["uuid"], {})
        if assigned.get("lines"):
            user = user.replace("[평소 습관]\n", "[평소 습관]\n" + "\n".join(assigned["lines"]) + "\n", 1)
    return system, user, order


def answer_by_needs(ctx: dict, visit: dict, condition: str, repeat: int, order: list) -> dict:
    """모델 없이 욕구 점수로 고른다. 손님의 욕구 세기에 상황의 변화를 더하고, 제품이 채워주는 정도를 곱해 더한다."""
    strength = ctx["strength"][visit["uuid"]]
    shift = ctx["shifts"][visit["상황 번호"]]
    need_codes = [n["번호"] for n in ctx["needs"]]
    weight = {c: max(0.0, int(strength[c]) + shift.get(c, 0.0)) for c in need_codes}
    scores = []
    for p in order:
        fulfil = dict(ctx["fulfills"][p["상품명"]])
        if condition == "변형" and p["상품명"] == VARIANTS[ROUND][ctx["shelf"]][0] and not VARIANTS[ROUND][ctx["shelf"]][1]:
            fulfil["N03"] = "못 채움"
        scores.append(sum(weight[c] * DEGREE[fulfil.get(c, "못 채움")] for c in need_codes))
    top = max(scores)
    probs = [math.exp((s - top) / 3.0) for s in scores]
    pick = random.Random(f"{visit['방문']}|{condition}|{repeat}|{SEED}").choices(range(len(order)), probs)[0]
    fulfil = ctx["fulfills"][order[pick]["상품명"]]
    reasons = sorted(need_codes, key=lambda c: -weight[c] * DEGREE[fulfil.get(c, "못 채움")])[:2]
    return {"number": pick + 1, "needs": reasons, "other": "", "sentence": "(욕구 점수로 고름)", "tokens": (0, 0)}


def answer_by_claude(ctx: dict, visit: dict, condition: str, repeat: int, order: list, system: str, user: str) -> dict:
    sys.path.insert(0, str(ROOT / "scripts"))
    import llm

    parsed, usage = llm.ask(system, user)
    tokens = (usage["input_tokens"], usage["output_tokens"])
    if parsed is None:
        return {"number": -1, "needs": [], "other": "", "sentence": "", "tokens": tokens}
    return {"number": parsed.choice_number, "needs": parsed.reason_needs, "other": parsed.reason_other, "sentence": parsed.reason_sentence, "tokens": tokens}


DEFAULT_CLI_MODEL = "claude-opus-5-5"
CLI_MODEL = DEFAULT_CLI_MODEL  # 실행할 때 --model로 바꾼다(예: claude-haiku-5-5). 가상 손님 역할을 하는 모델이다
CLI_SCHEMA = {
    "type": "object",
    "properties": {
        "choice_number": {"type": "integer", "description": "고른 제품의 매대 번호. 아무것도 사지 않으면 0"},
        "reason_needs": {"type": "array", "items": {"type": "string"}, "description": "고른 이유에 해당하는 욕구 번호. 1~3개"},
        "reason_other": {"type": "string", "description": "목록에 없는 이유가 있으면 짧게. 없으면 빈 문자열"},
        "reason_sentence": {"type": "string", "description": "손님의 말투로 쓴 이유 한두 문장"},
    },
    "required": ["choice_number", "reason_needs", "reason_other", "reason_sentence"],
    "additionalProperties": False,
}


def answer_by_cli(system: str, user: str) -> dict:
    """Claude Code 명령줄(claude -p)로 부른다. API 키 없이 요금제 로그인으로 돈다.

    도구를 모두 끄고 시스템 프롬프트를 우리 것으로 바꿔 부른다. 다만 명령줄이 답의 형식을 받기 위한 도구 하나를
    덧붙이므로 API를 직접 부르는 것과 완전히 같지는 않다. 본선에서는 scripts/llm.py(API)로 다시 잰다.
    """
    import json
    import subprocess

    done = subprocess.run(
        ["claude", "-p", "--model", CLI_MODEL, "--system-prompt", system, "--tools", "", "--setting-sources", "",
         "--strict-mcp-config", "--output-format", "json", "--json-schema", json.dumps(CLI_SCHEMA, ensure_ascii=False)],
        input=user, capture_output=True, text=True, timeout=300,
    )
    events = json.loads(done.stdout)
    result = [e for e in (events if isinstance(events, list) else [events]) if e.get("type") == "result"][-1]
    usage = result.get("usage", {})
    tokens = (usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0) + usage.get("cache_read_input_tokens", 0), usage.get("output_tokens", 0))
    out = result.get("structured_output")
    if result.get("is_error") or not isinstance(out, dict):
        return {"number": -1, "needs": [], "other": "", "sentence": "", "tokens": tokens}
    return {"number": int(out["choice_number"]), "needs": list(out["reason_needs"]), "other": out["reason_other"], "sentence": out["reason_sentence"], "tokens": tokens}


def result_path(shelf: str, responder: str) -> Path:
    """1차 결과는 이름 그대로, 2차부터는 뒤에 _r2처럼 차수를 붙인다."""
    model = "" if CLI_MODEL == DEFAULT_CLI_MODEL else "_" + CLI_MODEL.replace("claude-", "")  # 기본 모델이 아니면 파일 이름에 모델을 붙인다
    return OUT / (f"{shelf}_{responder}{model}.csv" if ROUND == 1 else f"{shelf}_{responder}_r{ROUND}{model}.csv")


def run(shelf: str, responder: str, limit: int) -> None:
    ctx = context(shelf)
    path = result_path(shelf, responder)
    OUT.mkdir(parents=True, exist_ok=True)
    done = {(r["방문"], r["조건"], r["반복"]) for r in csv.DictReader(open(path, encoding="utf-8"))} if path.exists() else set()
    jobs = [(v, c, r) for v in ctx["visits"][:limit] for c, n in (("기준", REPEATS), ("변형", 1)) for r in range(1, n + 1)
            if (v["방문"], c, str(r)) not in done]
    version = "needs-1"
    if responder == "claude":
        sys.path.insert(0, str(ROOT / "scripts"))
        import llm
        version = f"{llm.MODEL}/pilot-{TEXT[ROUND]}/r{ROUND}"
    if responder == "cli":
        version = f"{CLI_MODEL}/claude -p/pilot-{TEXT[ROUND]}/r{ROUND}"

    def one(job):
        visit, condition, repeat = job
        system, user, order = prompts(ctx, visit, condition, repeat)
        try:
            if responder == "needs":
                a = answer_by_needs(ctx, visit, condition, repeat, order)
            elif responder == "cli":
                a = answer_by_cli(system, user)
            else:
                a = answer_by_claude(ctx, visit, condition, repeat, order, system, user)
        except Exception as error:  # 한 건이 실패해도 나머지는 계속한다. 다시 돌리면 빠진 것만 채운다.
            print(f"  실패 {visit['방문']} {condition} {repeat}: {type(error).__name__}: {error}")
            return None
        valid = 0 <= a["number"] <= len(order)
        product = order[a["number"] - 1]["상품명"] if valid and a["number"] > 0 else ("사지 않음" if a["number"] == 0 else "")
        return [visit["방문"], condition, repeat, visit["uuid"], visit["상황 번호"], a["number"], product, "|".join(a["needs"]), a["other"],
                a["sentence"].replace("\n", " "), "예" if valid else "아니오", version, a["tokens"][0], a["tokens"][1]]

    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=1 if responder == "needs" else 4) as pool:
        writer = csv.writer(f)
        if new:
            writer.writerow(["방문", "조건", "반복", "uuid", "상황 번호", "고른 번호", "고른 제품", "이유 욕구", "기타 이유", "이유 문장", "유효", "모델과 프롬프트", "입력 토큰", "출력 토큰"])
        count = 0
        for row in pool.map(one, jobs):
            if row:
                writer.writerow(row)
                f.flush()
                count += 1
    print(f"{count}건 기록 -> {path.relative_to(ROOT)} (이미 있던 것 {len(done)}건)")


def analyze(shelf: str, responder: str) -> None:
    ctx = context(shelf)
    rows = [r for r in csv.DictReader(open(result_path(shelf, responder), encoding="utf-8")) if r["유효"] == "예"]
    base = defaultdict(dict)
    variant = {}
    for r in rows:
        if r["조건"] == "기준":
            base[r["방문"]][int(r["반복"])] = r
        else:
            variant[r["방문"]] = r
    complete = [v for v in base if len(base[v]) == REPEATS]
    n = len(complete)
    lines = [f"# 사전 측정 결과: {shelf} 매대, 응답자 {responder}", "", f"- 방문 {n}건(기준 {REPEATS}번을 모두 답한 것), 모델과 프롬프트: {rows[0]['모델과 프롬프트']}",
             f"- 토큰: 입력 {sum(int(r['입력 토큰']) for r in rows):,}, 출력 {sum(int(r['출력 토큰']) for r in rows):,}", ""]

    # 재검사 흔들림
    pairs = [(base[v][a]["고른 제품"], base[v][b]["고른 제품"]) for v in complete for a, b in ((1, 2), (1, 3), (2, 3))]
    wobble = sum(x != y for x, y in pairs) / len(pairs)
    all_same = sum(len({base[v][k]["고른 제품"] for k in base[v]}) == 1 for v in complete) / n
    # 엇갈림 비율: 기준 1회차와 변형
    both = [v for v in complete if v in variant]
    discord = sum(base[v][1]["고른 제품"] != variant[v]["고른 제품"] for v in both) / len(both)
    target, new_price = VARIANTS[ROUND][shelf]
    change = f"가격을 {new_price:,}원으로 올린" if new_price else "행사를 뗀"
    befores = [sum(base[v][k]["고른 제품"] == target for v in both) for k in range(1, REPEATS + 1)]
    before = sum(befores) / REPEATS
    after = sum(variant[v]["고른 제품"] == target for v in both)
    lines += ["## 흔들림", "", "| 재는 것 | 값 | 뜻 |", "|---|---|---|",
              f"| 재검사 흔들림 | {100 * wobble:.1f}% | 같은 매대를 두 번 보여줬을 때 다른 제품을 고른 비율 |",
              f"| 세 번 모두 같은 제품 | {100 * all_same:.1f}% | |",
              f"| 엇갈림 비율 | {100 * discord:.1f}% | 기준과 변형에서 다른 제품을 고른 비율. 재검사 흔들림보다 얼마나 큰지가 조건의 효과다 |",
              f"| 방향성 | 평균 {before:.1f}건 ({', '.join(map(str, befores))}) -> {after}건 | {change} '{target}'을 고른 방문 수(기준 {REPEATS}번 각각 -> 변형). 변형이 기준 {REPEATS}번의 범위 밖이면 흔들림보다 큰 변화다 |", ""]

    # 종류 분포와 기준값
    kind = {p["상품명"]: p["종류"] for p in ctx["products"]}
    picks = [base[v][1]["고른 제품"] for v in complete]
    kinds = Counter(kind.get(p, "사지 않음") for p in picks)
    lines += ["## 고른 종류 (기준 1회차)", "", "| 종류 | 비율 |", "|---|---|"] + [f"| {k} | {100 * c / n:.0f}% |" for k, c in kinds.most_common()]
    lines += ["", "국민건강영양조사의 상황별 실제 비율은 `data/ours/occasion_drink_mix.csv`에 있다. 종류의 이름이 달라 사람이 견줘 읽는다.", ""]

    # 실제와 견주기: aT 식품산업통계정보 소매 POS의 편의점 매출(scripts/collect_fis_pos.py)
    fis_path = ROOT / "data" / "clean" / "fis_pos_2025_cvs.csv"
    if fis_path.exists():
        real = defaultdict(float)
        for r in csv.DictReader(open(fis_path, encoding="utf-8")):
            if r["매대"] == shelf:
                real[FIS_KIND[r["품목"]]] += float(r["편의점 매출(백만원, 곱한 값)"])
        price = {p["상품명"]: int(p["가격(원)"]) for p in ctx["products"]}
        all_picks = [base[v][k]["고른 제품"] for v in complete for k in base[v] if base[v][k]["고른 제품"] in kind]
        covered = [p for p in all_picks if kind[p] in real]
        count, money = Counter(kind[p] for p in covered), Counter()
        for p in covered:
            money[kind[p]] += price[p]
        lines += ["## 실제와 견주기 (기준 전체)", "",
                  f"실제 값은 2025년 소매 POS의 편의점 매출 비중이다(`data/clean/fis_pos_2025_cvs.csv`). 그 자료에 있는 종류끼리만 견준다. "
                  f"가상 손님이 고른 {len(all_picks)}번 가운데 {len(all_picks) - len(covered)}번은 그 자료에 없는 종류({'물, 탄산수, 이온음료, 에너지음료' if shelf == '음료' else '하이볼, 와인, 청주, 논알콜'})라 뺐다.", "",
                  "| 종류 | 실제 편의점 매출 비중 | 가상 손님(금액) | 가상 손님(횟수) | 금액 차이 |", "|---|---|---|---|---|"]
        gap = 0.0
        for k, v in sorted(real.items(), key=lambda x: -x[1]):
            r_share, m_share, c_share = 100 * v / sum(real.values()), 100 * money[k] / max(1, sum(money.values())), 100 * count[k] / max(1, len(covered))
            gap += abs(r_share - m_share)
            lines.append(f"| {k} | {r_share:.1f}% | {m_share:.1f}% | {c_share:.1f}% | {m_share - r_share:+.1f}%p |")
        lines += ["", f"어긋난 정도(금액 비중 차이의 절댓값을 더해 반으로 나눈 값): **{gap / 2:.1f}%p**. 0이면 실제와 같고 100이면 전혀 다르다.",
                  "가상 손님의 금액은 고른 제품의 표시 가격을 더한 것이다. 1+1의 덤은 금액에 넣지 않았다.", ""]

    # 순서 쏠림, 획일화, 모순
    size = len(ctx["products"])
    numbers = [int(r["고른 번호"]) for r in rows if int(r["고른 번호"]) > 0]
    front = sum(x <= size / 3 for x in numbers) / len(numbers)
    top_product, top_count = Counter(picks).most_common(1)[0]
    reasons = [(r["고른 제품"], c) for r in rows if r["고른 제품"] in kind for c in r["이유 욕구"].split("|") if c]
    contradictions = sum(DEGREE[ctx["fulfills"][p].get(c, "못 채움")] <= 0 for p, c in reasons)
    lines += ["## 점검", "", "| 재는 것 | 값 | 기준 |", "|---|---|---|",
              f"| 순서 쏠림 | 앞쪽 3분의 1 번호를 고른 비율 {100 * front:.1f}% | 쏠림이 없으면 33% 안팎 |",
              f"| 획일화 | 가장 많이 고른 제품 '{top_product}' {100 * top_count / n:.0f}%, 고른 제품 {len(set(picks))}종 | 한 제품에 몰리면 손님이 구별되지 않는 것 |",
              f"| 모순 | 이유로 든 욕구를 고른 제품이 채우지 못하거나 거스르는 경우 {100 * contradictions / max(1, len(reasons)):.1f}% ({contradictions}/{len(reasons)}) | 낮을수록 좋다. 높으면 채워준다 규칙이나 욕구 이름을 고친다 |",
              f"| 사지 않음 | {100 * sum(p == '사지 않음' for p in picks) / n:.0f}% | |", ""]
    by_occasion = defaultdict(list)
    for v in complete:
        for k in base[v]:
            by_occasion[base[v][k]["상황 번호"]].append(base[v][k]["고른 제품"] == "사지 않음")
    lines += ["## 상황별 사지 않음 (기준 전체)", "", "| 상황 | 사지 않은 비율 | 물은 횟수 |", "|---|---|---|"]
    lines += [f"| {o} {ctx['occasions'][o]['상황']} | {100 * sum(x) / len(x):.0f}% | {len(x)} |" for o, x in sorted(by_occasion.items())] + [""]

    # 필요한 방문 수 (짝지은 비교, 맥니마). 95% 신뢰, 검정력 80%.
    lines += ["## 본 실험에 필요한 방문 수", "", f"엇갈림 비율 {100 * discord:.1f}%를 넣어 계산했다(짝지은 비교, 95% 신뢰수준, 검정력 80%).", "", "| 구별하려는 차이 | 필요한 방문 수 |", "|---|---|"]
    for diff in (0.03, 0.05, 0.06, 0.08, 0.10):
        if discord > diff:
            need = (1.96 * math.sqrt(discord) + 0.8416 * math.sqrt(discord - diff ** 2)) ** 2 / diff ** 2
            lines.append(f"| {100 * diff:.0f}%p | {math.ceil(need):,} |")
    report = result_path(shelf, responder).with_name(result_path(shelf, responder).stem + "_report.md")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"-> {report.relative_to(ROOT)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=["visits", "show", "run", "analyze"])
    parser.add_argument("shelf", nargs="?", default="음료", choices=["음료", "주류"])
    parser.add_argument("--responder", default="needs", choices=["needs", "claude", "cli"])
    parser.add_argument("--limit", type=int, default=VISITS_PER_SHELF)
    parser.add_argument("--round", type=int, default=ROUND, choices=sorted(VARIANTS), help="1차(행사 뗀 우리 제품, 꼭 사는 손님) 또는 2차(많이 고른 제품을 바꿈, 사지 않아도 됨)")
    parser.add_argument("--model", default=DEFAULT_CLI_MODEL, help="--responder cli일 때 가상 손님 역할을 하는 모델")
    args = parser.parse_args()
    ROUND = args.round
    CLI_MODEL = args.model
    if args.step == "visits":
        build_visits()
    elif args.step == "show":
        ctx = context(args.shelf)
        system, user, _ = prompts(ctx, ctx["visits"][0], "기준", 1)
        print(system, "\n\n" + "=" * 40 + "\n", user)
    elif args.step == "run":
        run(args.shelf, args.responder, args.limit)
    else:
        analyze(args.shelf, args.responder)
