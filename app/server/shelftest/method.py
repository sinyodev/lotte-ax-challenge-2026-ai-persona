"""매대 테스트의 방법 (지시서 15의 1절). 바꾸지 않는다.

손님이 받는 글은 scripts/pilot.py의 prompts()와 scripts/shelf_test.py의 ASK를, 답의 형식은
shelf_test.answer()의 형식을 쓴다. Claude의 글은 4차다. GPT의 비교 차수에는 방문 달과 기온(6차),
선호 순서와 행사 설명(7차), 조사·판매 집계로 배정한 평소 구매 습관(8·9차)을 차례로 더한다.
10차는 탐색과 결정을 나누어 묻고, 11차는 9차의 단일 선택에 손님·상황·상품의 욕구 관계를 JSON으로 제공한다.

- 손님: data/clean/personas_3000.parquet의 pool exp에서 타깃의 연령대(없으면 모든 연령대)와 성별(정했으면)에 맞는 사람.
  shelf_test.setup()과 같은 차례(pilot.unit(uuid, "shelf-test")).
- 상황: 겨냥한 상황이 있으면 앞의 절반(인원의 절반)은 그 상황, 뒤의 절반은 그 집단의 실제 비중대로. 없으면 모두 실제 비중대로.
- 한 손님에게 두 번 묻는다: 컨셉이 없는 매대("기준"), 컨셉을 올린 매대("컨셉", 새 제품에 대한 생각을 함께 받는다).
- 손님 서술(persona)은 모델에게 보내는 글에만 쓴다. 화면이나 통로로 내보내지 않는다. 이름은 말을 거르는 데만 쓴다.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
import hashlib
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Sequence

from shelftest import catalog  # scripts 경로를 추가한다
import pilot  # noqa: E402
import shelf_test  # noqa: E402
import onsite
from onsite.concepts import CONCEPTS, match as known_concept

SHELF = shelf_test.SHELF  # 음료
CONCEPT = shelf_test.CONDITION  # "컨셉"
BASELINE = shelf_test.BASELINE  # "기준"
VIEWS = list(shelf_test.VIEWS)
BARRIERS = list(shelf_test.BARRIERS)
ROUND = 4
GPT_ROUND = 11
NO_PURCHASE = "사지 않음"
NO_PROMO = "행사 없음"


# ---------- 매대와 손님 ----------


@lru_cache(maxsize=1)
def base_ctx() -> dict[str, Any]:
    """사전 측정 4차의 음료 매대 ctx(손님의 습관, 상황, 니즈, 매대). shelf_test.setup()의 앞부분과 같다."""
    pilot.ROUND = ROUND
    ctx = pilot.context(SHELF)
    pilot.label(ctx["products"][0], False, SHELF)
    return ctx


def display(name: str) -> str:
    if name.startswith("pos:") and name.count(":") >= 2:
        return name.split(":", 2)[2]
    return next((p.name for p in catalog.public() if p.key == name), name)


def shelf_v(round_number: int | None = None) -> str:
    """매대 자료의 판: 매대, 손님이 보는 이름, 글의 차수로 정한다. 컨셉이 없는 매대의 답을 다시 쓰는 열쇠."""
    if round_number is None:
        round_number = prompt_round()
    version = catalog.version(catalog.current(), round_number)
    if round_number in (8, 9, 10, 11):
        from calibrate import habits
        version = hashlib.sha256(f"{version}:{habits.reference().signature}".encode()).hexdigest()[:10]
    if round_number == 10:
        from shelftest import journey
        version = hashlib.sha256(f"{version}:{journey.signature(journey.patterns())}".encode()).hexdigest()[:10]
    if round_number == GPT_ROUND:
        from calibrate import novelty
        if mark := novelty.signature(novelty.mode()):
            version = hashlib.sha256(f"{version}:{mark}".encode()).hexdigest()[:10]
        from tools.shelf_items import concept_novelty
        if (relation := concept_novelty()) != "well":
            version = hashlib.sha256(f"{version}:concept-N08:{relation}".encode()).hexdigest()[:10]
    if os.getenv("AX_LLM") in ("codex", "openai"):
        from llm.models import model_for
        effort = model_for("shopper").effort
        if effort and effort != "low":
            return hashlib.sha256(f"{version}:{effort}".encode()).hexdigest()[:10]
    return version


def prompt_round() -> int:
    if os.getenv("AX_LLM") not in ("codex", "openai"):
        return ROUND
    value = int(os.getenv("AX_SHOPPER_ROUND", GPT_ROUND))
    if value not in (4, 6, 7, 8, 9, 10, 11):
        raise ValueError("가상 소비자 글의 차수는 4, 6, 7, 8, 9, 10, 11 중 하나여야 합니다.")
    return value


def sale_months(line: str, annual: bool = False, *, season: str | None = None, launch: str | None = None) -> list[int]:
    if annual:
        return list(range(1, 13))
    concept = known_concept(line) or {}
    season = concept.get("season") if season is None else season
    interval = re.search(r"(\d{1,2})월?\s*(?:[~–-]|부터)\s*(\d{1,2})월", season or "")
    if interval:
        start, end = map(int, interval.groups())
        if 1 <= start <= 12 and 1 <= end <= 12:
            return [(start - 1 + i) % 12 + 1 for i in range((end - start) % 12 + 1)]
    single = re.fullmatch(r"\s*(\d{1,2})월(?:\s*한정)?\s*", season or "")
    if single and 1 <= int(single[1]) <= 12:
        return [int(single[1])]
    launch = (concept.get("launch") if launch is None else launch) or ""
    iso = re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])(?:-\d{2})?", launch)
    start = int(iso[1]) if iso else 1
    return [(start - 1 + i) % 12 + 1 for i in range(12)]


def visit_calendar(training: bool) -> tuple[Counter, dict[int, float]]:
    try:
        sales = [r for r in onsite.load("pos_clean") if r["channel"] == "편의점"]
    except onsite.NoData:
        sales = []
    try:
        climate = onsite.load("temperature")
    except onsite.NoData:
        climate = []
    available = sorted({r["month"] for r in sales or climate})
    dates = set(available[:12] if training else available[-12:])
    units, degrees = Counter(), defaultdict(list)
    for r in sales:
        if r["month"] in dates:
            units[int(r["month"][5:7])] += r["units"]
    for r in climate:
        if r["month"] in dates and r["temp_c"] is not None:
            degrees[int(r["month"][5:7])].append(r["temp_c"])
    return units, {k: round(sum(v) / len(v), 1) for k, v in degrees.items()}


def assign_month(uuid: str, allowed: Sequence[int], units: dict[int, int]) -> int:
    weights = [max(units.get(m, 0), 0) for m in allowed]
    if not sum(weights):
        weights = [1] * len(allowed)
    point = pilot.unit(uuid, "shelf-visit-month-v1") * sum(weights)
    for month, weight in zip(allowed, weights):
        if point < weight:
            return month
        point -= weight
    return allowed[-1]


def baseline_occasion(visit: dict[str, Any]) -> str:
    key = visit["상황 번호"]
    if "visit_month" in visit:
        return f"{key}|{visit['visit_month']:02}|{visit.get('temp_c')}"
    return key


@dataclass(frozen=True)
class Person:
    uuid: str
    sex: str
    band: str
    age: int
    occupation: str
    text: tuple  # pilot.prompts가 쓰는 (나이, 직업, 지역, 가구, 서술, 식생활 서술)


@lru_cache(maxsize=16)
def people(band: str | None, sex: str | None, *, pool: str = "exp") -> tuple[Person, ...]:
    import duckdb

    ctx = base_ctx()
    if pool not in ("dev", "exp"):
        raise ValueError("개발 또는 평가 패널을 지정해야 합니다.")
    where = ["pool = ?"]
    params: list[Any] = [pool]
    if band:
        where.append("age_band = ?")
        params.append(band)
    if sex:
        where.append("sex = ?")
        params.append(sex)
    rows = duckdb.execute(
        "SELECT uuid, sex, age_band, age, occupation, province, family_type, persona, culinary_persona "
        f"FROM '{pilot.PERSONAS.as_posix()}' WHERE {' AND '.join(where)}", params).fetchall()
    rows = [p for p in rows if p[0] in ctx["profiles"] and p[0] in ctx["strength"]]
    rows.sort(key=lambda p: pilot.unit(p[0], "shelf-test"))
    return tuple(Person(p[0], p[1], p[2], int(p[3]), p[4] or "", tuple(p[3:])) for p in rows)


@lru_cache(maxsize=1)
def _weights() -> dict[tuple[str, str], list[tuple[str, float]]]:
    out: dict[tuple[str, str], list[tuple[str, float]]] = {}
    for r in pilot.read("occasion_weights.csv"):
        if r["매대"] == SHELF:
            out.setdefault((r["성별"], r["연령대"]), []).append((r["번호"], float(r["비중(%)"])))
    return out


def occasion_of(i: int, person: Person, occasion: str | None, half: int) -> str:
    """shelf_test.setup()의 occasion_of(--mix)와 같다: 앞의 절반은 겨냥한 상황, 뒤의 절반은 그 집단의 실제 상황 비중대로."""
    if occasion and i < half:
        return occasion
    point, running = pilot.unit(person.uuid, SHELF, "shelf-test") * 100, 0.0
    options = _weights()[(person.sex, person.band)]
    for code, w in options:
        running += w
        if point <= running:
            return code
    return options[-1][0]


def occasions() -> dict[str, dict[str, str]]:
    return base_ctx()["occasions"]


# ---------- 컨셉 한 줄 ----------


def line_name(name: str, container: str, volume: int) -> str:
    """매대에 올리는 이름: 컨셉의 이름 + 용기와 용량(예: "모닝 유자생강 제로 페트 350ml")."""
    return f"{name.strip()} {container} {volume}ml"


def concept_row(name: str, price: int, promo: str | None) -> dict[str, str]:
    """shelf_test.setup()의 concept과 같은 모양. name은 line_name()."""
    return {"매대": SHELF, "상품명": name, "가격(원)": str(price), "행사": promo or NO_PROMO, "묶음 수량": "1"}


def _storage(name: str, storage: str | None) -> str | None:
    if storage is not None:
        return storage.strip()
    name = " ".join(name.split())
    for concept in CONCEPTS:
        title = concept["name"]
        if name == title or name.startswith(f"{title} "):
            return concept["storage"]
    return None


def placement(name: str, storage: str | None = None) -> dict[str, str | float | None] | None:
    """냉장·냉동 진열 위치와 편의점 진열 가능 점포율(%)."""
    storage = _storage(name, storage)
    if storage not in ("냉장", "냉동"):
        return None
    return {"storage": storage, "store_rate": catalog.store_rate(storage)}


# ---------- 한 테스트의 계획 ----------


@dataclass
class Plan:
    visits: list[dict[str, Any]]
    plain: dict[str, Any]  # 컨셉이 없는 매대의 ctx
    with_concept: dict[str, Any]  # 컨셉을 올린 매대의 ctx
    line: str  # 매대에 올린 이름
    by_uuid: dict[str, Person]
    storage: str | None = None
    round_number: int = ROUND


def plan(band: str | None, sex: str | None, occasion: str | None, total: int, line: str, price: int,
         promo: str | None, *, participants: Sequence[Person] | None = None, storage: str | None = None,
         annual_months: bool = False, training: bool = False, season: str | None = None,
         launch: str | None = None, round_number: int | None = None) -> Plan:
    """선택해 둔 손님이 있으면 그 명단 순서로, 없으면 기존 방식대로 total명의 방문을 만든다."""
    ctx = base_ctx()
    selected = people(band, sex)[:total] if participants is None else participants
    half = (total if participants is None else len(selected)) // 2
    visits = []
    for i, p in enumerate(selected):
        code = occasion_of(i, p, occasion, half)
        visits.append({"방문": f"T{i + 1:03d}", "매대": SHELF, "uuid": p.uuid, "성별": p.sex, "연령대": p.band,
                       "상황 번호": code, "상황": ctx["occasions"][code]["상황"]})
    if round_number is None:
        round_number = prompt_round()
    if round_number >= 6:
        allowed = sale_months(line, annual_months, season=season, launch=launch)
        units, degrees = visit_calendar(training)
        for v in visits:
            month = assign_month(v["uuid"], allowed, units)
            v.update(visit_month=month, temp_c=degrees.get(month))
    if round_number == 10:
        from shelftest import journey

        histogram = journey.patterns()
        for v in visits:
            v["shelf_seconds"], v["comparison_limit"] = journey.visit_pattern(
                histogram, v["uuid"], v["상황 번호"], v["visit_month"])
    products = [p for p in catalog.current() if p.shelf == SHELF]
    plain = {**ctx, "visits": visits, "text": {p.uuid: p.text for p in selected},
             "products": [dict(p.row) for p in products], "display": {p.key: p.name for p in products},
             "fulfills": {p.key: dict(p.fulfills) for p in products}}
    if round_number in (8, 9, 10, 11):
        from calibrate import habits

        ref = habits.reference()
        plain["purchase_habits"] = {}
        for person in selected:
            profile = ctx["profiles"][person.uuid]
            favorites = [profile[k] for k in ("좋아하는 음료 1순위", "2순위", "3순위")]
            plain["purchase_habits"][person.uuid] = habits.assign(
                ref, person.uuid, person.band, person.sex, favorites, habits.COVERAGE[round_number])
    if round_number == GPT_ROUND:
        # 11차 글만 평소_욕구를 보낸다. 새로움 욕구(N08)를 조사 분포에 맞춘다(AX_NOVELTY, off면 그대로).
        from calibrate import novelty
        plain["strength"] = novelty.calibrated(ctx["strength"])
    with_concept = {**plain, "products": plain["products"] + [concept_row(line, price, promo)]}
    return Plan(visits, plain, with_concept, line, {p.uuid: p for p in selected},
                _storage(line, storage), round_number)


def prompts(p: Plan, visit: dict[str, Any], condition: str) -> tuple[str, str, list[dict[str, str]]]:
    """손님이 받는 글(시스템, 사용자)과 이번에 섞은 매대 순서. 컨셉 매대이면 새 제품에 대한 물음(ASK)을 붙인다."""
    if p.round_number == 11:
        from shelftest import shopper_json
        return shopper_json.prompts(p, visit, condition)
    ctx = p.with_concept if condition == CONCEPT else p.plain
    pilot.ROUND = p.round_number
    pilot._display.update(ctx["display"])
    pilot._display[p.line] = p.line
    system, user, order = pilot.prompts(ctx, visit, condition, 1)
    if p.round_number == 10:
        from shelftest import journey
        return system, journey.stage_input(user, visit), order
    if condition == CONCEPT:
        number = next(i + 1 for i, q in enumerate(order) if q["상품명"] == p.line)
        if p.storage in ("냉장", "냉동"):
            user += f"\n\n{number}번 새 제품은 편의점 {p.storage} 코너에 진열되어 있습니다."
        user += shelf_test.ASK.format(number=number, name=p.line)
    return system, user, order


# ---------- 답의 형식 ----------


def schema(asked: bool) -> dict[str, Any]:
    """shelf_test.answer()가 claude -p에 넘기는 형식과 같다(asked가 아니면 pilot.CLI_SCHEMA)."""
    out = json.loads(json.dumps(pilot.CLI_SCHEMA))
    if not asked:
        return out
    out["properties"]["new_product"] = {
        "type": "object", "additionalProperties": False, "required": ["view", "barriers", "said"],
        "properties": {
            "view": {"type": "string", "enum": VIEWS, "description": "새 제품을 보는 눈. 위에서 이 제품을 골랐으면 '이번에 산다'"},
            "barriers": {"type": "array", "items": {"type": "string", "enum": BARRIERS}, "description": "사지 않았다면 걸린 점 1~2개. 샀으면 빈 목록"},
            "said": {"type": "string", "description": "새 제품을 보고 든 생각을 손님의 말투로 한 문장"},
        }}
    out["required"] = out["required"] + ["new_product"]
    return out


class BadAnswer(ValueError):
    pass


def parse(raw: Any, order: list[dict[str, str]], asked: bool) -> dict[str, Any]:
    """모델의 답을 한 줄로. 번호가 매대 밖이거나 형식이 틀리면 BadAnswer(다시 묻는다)."""
    if not isinstance(raw, dict):
        raise BadAnswer("답이 객체가 아니에요")
    try:
        number = int(raw["choice_number"])
        needs = [str(x) for x in raw.get("reason_needs") or []]
        other = str(raw.get("reason_other") or "")
        sentence = str(raw.get("reason_sentence") or "")
    except (KeyError, TypeError, ValueError) as e:
        raise BadAnswer(f"형식: {e}") from e
    if not 0 <= number <= len(order):
        raise BadAnswer(f"매대에 없는 번호: {number}")
    row: dict[str, Any] = {
        "number": number, "product": order[number - 1]["상품명"] if number > 0 else NO_PURCHASE,
        "needs": needs, "other": other, "sentence": sentence.replace("\n", " "),
    }
    if asked:
        new = raw.get("new_product")
        if not isinstance(new, dict) or new.get("view") not in VIEWS:
            raise BadAnswer("새 제품에 대한 생각이 없어요")
        barriers = [b for b in new.get("barriers") or [] if b in BARRIERS]
        row.update({"view": new["view"], "barriers": barriers, "said": str(new.get("said") or "").replace("\n", " ")})
    return row


# ---------- 손님을 화면에 적는 말(이름은 내보내지 않는다) ----------

NAME_RE = re.compile(r"^\s*([가-힣]{2,4})\s*씨")


def name_words(person: Person) -> list[str]:
    """손님 서술 맨 앞의 이름(예: "홍길동 씨는 …")과 그 이름에서 성을 뺀 것. 말을 거르는 데만 쓴다."""
    persona = person.text[4] or ""
    m = NAME_RE.match(persona)
    if not m:
        return []
    full = m.group(1)
    return [full, full[1:]] if len(full) >= 3 else [full]


def who_line(person: Person) -> str:
    """"24세 여자, 대학생"처럼 나이·성별·직업만."""
    job = person.occupation.strip()
    return f"{person.age}세 {person.sex}" + (f", {job}" if job else "")
