"""편의점 방문의 탐색과 결정을 따로 묻는 실험용 10차 방법."""

from collections import Counter, defaultdict
from contextlib import nullcontext
from itertools import groupby
import time
import hashlib
import json

from llm.base import LLMError
import onsite
from shelftest import method
from tools import shelf_items
import pilot


VERSION = "offline-consideration-v1"
SCAN_SYSTEM = ("당신은 아래에 적힌 편의점 손님입니다. 진열을 훑어볼 때 눈에 들어오는 상품 번호를 noticed에, "
               "그중 집을지 실제로 살펴볼 상품 번호를 considered에 적으세요. 어느 상품도 없으면 빈 목록을 쓰세요. "
               "번호는 중복할 수 없습니다. 지금은 구매 결정을 묻지 않습니다.")
SCAN_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["noticed", "considered"],
               "properties": {key: {"type": "array", "items": {"type": "integer"}}
                              for key in ("noticed", "considered")}}


def patterns():
    # 방문 결과·메모·사후 유형은 모의 방문에 넘기지 않는다. 같은 방문의 시간과 비교 개수만 함께 센다.
    counts = Counter()
    for row in onsite.load("journeys_offline"):
        seconds, compared = row["seconds"], row["compared"]
        if row["store_type"] == "편의점" and seconds is not None and seconds >= 0 and compared is not None and compared >= 0:
            counts[int(seconds), int(compared)] += 1
    if not counts:
        raise ValueError("편의점의 비교 수와 소요 시간이 함께 있는 관찰 자료가 필요합니다.")
    return sorted(counts.items())


def signature(histogram):
    return hashlib.sha256(json.dumps([VERSION, histogram]).encode()).hexdigest()


def visit_pattern(histogram, uuid, occasion, month):
    point = pilot.unit(uuid, occasion, month, VERSION) * sum(count for _, count in histogram)
    for pair, count in histogram:
        if point < count:
            return pair
        point -= count
    return histogram[-1][0]


def stage_input(user, visit):
    return (user + f"\n\n이번 방문에서 매대에 쓰는 시간은 약 {visit['shelf_seconds']}초입니다. "
            f"실제로 비교할 제품은 최대 {visit['comparison_limit']}개입니다.")


def selections(raw, order, limit):
    if not isinstance(raw, dict):
        raise method.BadAnswer("탐색 응답이 객체가 아닙니다.")
    for key in ("noticed", "considered"):
        ids = raw.get(key)
        if (not isinstance(ids, list) or any(type(i) is not int or not 1 <= i <= len(order) for i in ids)
                or len(ids) != len(set(ids))):
            raise method.BadAnswer("탐색 응답에 잘못된 번호가 있습니다.")
    noticed, considered = raw["noticed"], raw["considered"]
    if len(considered) > limit or not set(considered) <= set(noticed):
        raise method.BadAnswer("비교 목록은 눈에 들어온 상품 중 방문의 비교 한도 안에서 정해야 합니다.")
    return noticed, considered


async def answer(plan, visit, condition, ask):
    """ask는 단계 단위 재시도와 계측을 맡는다. 이미 얻은 탐색·구매 응답은 되묻지 않는다."""
    system, user, order = method.prompts(plan, visit, condition)
    limit = visit["comparison_limit"]
    noticed, considered = await ask(SCAN_SYSTEM, user, SCAN_SCHEMA,
                                    lambda raw: selections(raw, order, limit))
    candidates = [order[i - 1] for i in sorted(considered)]
    trace = {"source": "simulated", "channel": "편의점", "shelf_seconds": visit["shelf_seconds"],
             "comparison_limit": limit, "noticed": [order[i - 1]["상품명"] for i in noticed],
             "considered": [order[i - 1]["상품명"] for i in considered]}
    if not candidates:
        return {"number": 0, "product": method.NO_PURCHASE, "needs": [], "other": "", "sentence": "", "journey": trace}

    prefix, separator, _ = user.partition(f"[{method.SHELF} 매대]\n")
    if not separator:
        raise ValueError("비교 목록을 표시할 매대 구간이 없습니다.")
    labels = [f"{i}. {pilot.label(p, False, method.SHELF)}" for i, p in enumerate(candidates, 1)]
    decision = (prefix + "[비교한 상품]\n1+1은 한 개 값으로 두 개, 2+1은 두 개 값으로 세 개입니다.\n"
                + "0. 사지 않음\n" + "\n".join(labels))
    candidate_keys = [p["상품명"] for p in candidates]
    compared_new = condition == method.CONCEPT and plan.line in candidate_keys
    if compared_new:
        if plan.with_concept.get("concept_prompt_version"):
            decision += shelf_items.concept_prompt(plan, candidates)
        if plan.storage:
            decision += f"\n{candidate_keys.index(plan.line) + 1}번 제품은 {plan.storage} 코너에 있습니다."
    row = await ask(system, decision, method.schema(False), lambda raw: method.parse(raw, candidates, False))
    row["number"] = sorted(considered)[row["number"] - 1] if row["number"] else 0
    row["journey"] = trace
    if compared_new:
        feedback = method.schema(True)["properties"]["new_product"]
        question = (f"{decision}\n\n선택은 이미 끝났습니다. 고른 것은 {method.display(row['product'])}입니다. "
                    f"비교했던 {plan.line}에 대한 생각을 view, barriers, said에 적으세요.")

        def parse_feedback(raw):
            parsed = method.parse({"choice_number": 0, "new_product": raw}, candidates, True)
            if (parsed["view"] == "이번에 산다") != (row["product"] == plan.line):
                raise method.BadAnswer("소감과 이미 정한 선택이 다릅니다.")
            return {k: parsed[k] for k in ("view", "barriers", "said")}

        try:
            row.update(await ask("이미 끝난 구매 결정에 관해 편의점 손님으로서 답하세요.", question, feedback, parse_feedback))
        except (LLMError, method.BadAnswer):
            trace["feedback_missing"] = True
    return row


def funnel(rows, line):
    valid = [r for r in rows if r.get("product") is not None and r.get("journey")]
    seen = sum(line in r["journey"]["noticed"] for r in valid)
    compared = sum(line in r["journey"]["considered"] for r in valid)
    bought = sum(r["product"] == line for r in valid)
    return {"source": "simulated", "visits": len(valid), "noticed": seen, "considered": compared, "purchased": bought,
            "purchased_per_visit": bought / len(valid) if valid else None,
            "purchased_per_noticed": bought / seen if seen else None,
            "purchased_per_considered": bought / compared if compared else None,
            "feedback_missing": sum(bool(r["journey"].get("feedback_missing")) for r in valid)}


async def run(plan, visit, condition, model, measured, get_llm, retries, timeout):
    async def ask(system, user, schema, parse):
        for attempt in range(1 + retries):
            try:
                with measured.call() if measured is not None else nullcontext():
                    raw = await get_llm().ask("shopper", system, user, schema, timeout=timeout, model=model)
                return parse(raw)
            except (LLMError, method.BadAnswer):
                if attempt == retries:
                    raise

    started = time.monotonic()
    try:
        row = await answer(plan, visit, condition, ask)
    except (LLMError, method.BadAnswer) as exc:
        return None, type(exc).__name__
    row["sec"] = round(time.monotonic() - started, 1)
    return row, ""


def online_reference(rows):
    """세션 내 같은 상품이 순서대로 도달한 단계만 센다. 같은 시각은 한 단계만 인정한다."""
    stages = ("노출", "클릭", "상세보기", "장바구니", "구매")
    chains = defaultdict(list)
    for r in rows:
        if (r["is_bot"] is False and r["session"] is not None and r["sku"]
                and r["ts_kst"] and r["event"] in stages):
            chains[r["session"], r["sku"]].append((r["ts_kst"], r["event"]))
    reached = defaultdict(int)
    for (session, _), events in chains.items():
        depth = 0
        for _, same_time in groupby(sorted(events), key=lambda e: e[0]):
            if stages[depth] in {label for _, label in same_time}:
                depth += 1
                if depth == len(stages):
                    break
        reached[session] = max(reached[session], depth)
    counts = {stage: sum(depth > i for depth in reached.values()) for i, stage in enumerate(stages)}
    return {"source": "observed", "channel": "온라인", "sessions": len(reached), "stages": counts,
            "purchased_per_exposed": counts["구매"] / counts["노출"] if counts["노출"] else None}
