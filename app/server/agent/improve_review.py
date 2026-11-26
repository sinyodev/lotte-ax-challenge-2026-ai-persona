"""대화와 작업대에서 같은 후보를 펼치고, 확인한 뒤에만 테스트한다."""
from __future__ import annotations

import json
import re

from agent import improve, improve_suggestions, phrases as P
from events import Actions, Choices, Option, Stage
from tools.consumer import josa

PICK = "compare-candidate"
RUN = "try-candidate"
MENU = "choose-candidate"
OLD_PROMPT = "비교할 개선안을 골라 주세요. 바꿀 조건과 근거를 확인한 뒤 같은 손님에게 다시 테스트할 수 있어요."


def label(item):
    kind = improve.KIND_NAMES.get(item.get("kind") or improve.kind_of(item.get("values", {})), "").removesuffix(" 변경안")
    return f"{kind} · {item['after']}" if item.get("after") else item["change"]


def overview(n, view):
    from agent import machine

    plan = n.improve
    items = plan["items"]
    if not items:
        return machine._end(n, "지금 매대 결과로 제안할 변경안을 찾지 못했어요.", machine.result_offer(n))
    chosen = first_candidate(items, view["result"], plan.get("focus_id") or machine._survey_focus(n) or plan.get("adopted_item_id"))
    plan["focus_id"] = chosen["id"]
    return machine._end(n, brief(view["result"], chosen), actions(n, chosen))


def first_candidate(items, result, focus):
    counts = {b["label"]: b["count"] for b in result.get("barriers", [])}
    return next((it for it in items if it["id"] == focus), None) or max(
        items, key=lambda it: counts.get(improve_suggestions.BARRIERS.get(it.get("kind")), 0))


# 매대 설문의 응답 항목을 말로 읽을 때만 풀어 쓴다.
_REASONS = {
    improve.FIRST_SEEN: "처음 보는 제품이라 망설인",
    improve.PRICEY: "가격이 비싸다고 답한",
    improve.PACK: "용량이나 용기가 맞지 않는다고 답한",
    improve_suggestions.TASTE: "맛이 끌리지 않는다고 답한",
    improve_suggestions.SITUATION: "마시려던 상황에 맞지 않는다고 답한",
    improve_suggestions.UNCLEAR: "어떤 제품인지 모르겠다고 답한",
}


def brief(result, chosen):
    counts = {b["label"]: b["count"] for b in result.get("barriers", []) if b["count"]}
    top = max(counts, key=counts.get) if counts else None
    def reason(key):
        return _REASONS.get(key) or f"‘{key}’{josa(key, '을/를')} 고른"

    if top:
        most = "으로 가장 많았어요" if sum(v == counts[top] for v in counts.values()) == 1 else "이었어요"
        insight = f"{reason(top)} 손님이 {counts[top]:,}명{most}."
    else:
        insight = f"매대에서 {result['n']:,}명 중 {result['picked']:,}명이 이 제품을 골랐어요."
    secondary = improve_suggestions.BARRIERS.get(chosen.get("kind"))
    if secondary in counts and secondary != top:
        if secondary == improve_suggestions.TASTE:
            insight += f" {counts[secondary]:,}명은 맛이 끌리지 않아 지나쳤어요."
        else:
            insight += f" {reason(secondary)} 손님도 {counts[secondary]:,}명 있었어요."
    return f"{insight}\n\n{next_question(chosen)}"


def next_question(item):
    kind, value = item.get("kind"), item.get("after")
    if item.get("run_id"):
        return "이 안의 매대 결과를 볼까요?"
    if item.get("price_sweep"):
        return "가격을 낮춘 안과 높인 안을 같은 손님에게 보여줄까요?"
    if not value:
        return f"‘{item['change']}’ 안으로 다시 물어볼까요?"
    if kind == "flavor" and value.startswith("향을 줄인 "):
        flavor = value.removeprefix("향을 줄인 ").removesuffix("맛").strip()
        if flavor:
            return f"{flavor} 향을 줄인 안을 같은 손님에게 보여줄까요?"
    if kind == "form" and value == "무탄산":
        return "탄산을 빼면 같은 손님들이 더 많이 고를지 확인해 볼까요?"
    kind_name = improve.KIND_NAMES.get(kind, "조건").removesuffix(" 변경안")
    return f"{kind_name}{josa(kind_name, '을/를')} ‘{value}’{josa(value, '으로/로')} 바꿔서 다시 물어볼까요?"


def compared_text(item, paired):
    value = item.get("after")
    changed = f"‘{value}’ 안" if value else "바꾼 안"
    verdict = {
        "more": f"{changed}을 더 많이 골랐어요.",
        "less": f"원래 제품을 {changed}보다 더 많이 골랐어요.",
        "unclear": P.IMPROVE_UNCLEAR,
    }
    if not paired["gained"] and not paired["lost"]:
        return f"두 매대에서 이 제품을 고른 손님은 같았어요. {verdict[paired['verdict']]}"
    return (f"{verdict[paired['verdict']]} 바꾼 안에서 {paired['gained']:,}명이 새로 골랐고, "
            f"원래 고르던 {paired['lost']:,}명은 지나쳤어요.")


def selection_text(item, paired=None):
    if paired and paired["n"]:
        return compared_text(item, paired)
    quote = next((e["text"] for e in item.get("evidence", []) if e.get("quote_id")), None)
    if quote:
        return f"인터뷰에서 이런 말이 나왔어요. “{quote}”\n\n{next_question(item)}"
    basis = item.get("reason", "")
    # 저장된 매대 근거에 응답 항목과 인원수가 모두 있을 때 그 사실만 읽어 준다.
    for entry in item.get("evidence", []):
        found = re.fullmatch(r"원래 안 매대 테스트에서 응답한 [\d,]+명 중 ([\d,]+)명이 ‘([^’]+)’을 골랐어요\.", entry["text"])
        if entry["origin"] == "record" and found and found[2] in _REASONS:
            basis = f"{_REASONS[found[2]]} 손님이 {found[1]}명 있었어요."
            break
    return " ".join(filter(None, (basis, next_question(item))))


def actions(n, item):
    from agent import machine
    from shelftest import store

    plan = n.improve
    base = plan["base_run"]
    status = (store.load_meta(item["run_id"]) or {}).get("status") if item.get("run_id") else None
    if status in ("running", "done"):
        primary = (machine.IMPROVE_COMPARE, P.BTN_IMPROVE_COMPARE)
    else:
        test_label = "이 안으로 테스트하기"
        if item.get("price_sweep"):
            prices = [it["after"] for it in plan["items"] if it.get("price_sweep") and it.get("after")]
            if len(prices) > 1:
                test_label = f"{' · '.join(prices)} 함께 테스트하기"
        primary = (f"{RUN}:{base}:{item['id']}", test_label)
    options = [primary]
    if len(plan["items"]) > 1:
        options.append((f"{MENU}:{base}", "다른 후보 보기"))
    options.append((machine.REPORT, P.BTN_REPORT))
    return machine._actions(n, "compare-plans", options)


def typed_reply(n, text):
    """후보를 보는 차례에 값이나 종류로 고른다. 같은 종류가 여럿이면 다시 고르게 한다."""
    offer = n.last_offer
    if not isinstance(offer, (Actions, Choices)) or not offer.id.startswith(("compare-plans-", PICK + ":")):
        return None
    plan = n.improve or {}
    if not plan.get("items"):
        return None
    words = re.sub(r"[\s,’‘'“”·.!?]", "", text).lower()
    if isinstance(offer, Actions) and words in ("테스트", "테스트하기", "테스트해줘", "이안으로테스트해줘", "이걸로테스트해줘"):
        command = offer.actions[0].id
        if command.startswith(RUN + ":"):
            return offer.id, [command]
    subject = re.sub(r"(?:후보|안)?(?:으?로|을|를)?(?:볼게요?|볼래요?|보여줘|비교해줘|살펴볼게요|보고싶어(?:요)?)$", "", words)
    if not subject:
        return None
    matches = []
    for item in plan["items"]:
        kind = improve.KIND_NAMES.get(item.get("kind") or improve.kind_of(item.get("values", {})), "")
        names = (item.get("after") or "", label(item), kind, kind.removesuffix(" 변경안"))
        if any(subject == re.sub(r"[\s,·]", "", name).lower() for name in names if name):
            matches.append(item["id"])
    base = plan["base_run"]
    if len(matches) == 1:
        return f"{PICK}:{base}", matches
    if matches:
        return offer.id, [f"{MENU}:{base}"]
    return None


def choose(n, conv_id, ids):
    from agent import machine

    plan = n.improve or {}
    base = ids[0] if ids else None
    if base != plan.get("base_run") or not machine._owned_improve_run(n, conv_id, base):
        return machine._end(n, "지금 비교하는 매대의 후보를 다시 골라 주세요.", None)
    if len(ids) == 1:
        opts = [Option(id=it["id"], label=label(it)) for it in plan["items"]]
        return machine._end(n, "어떤 안을 원래 제품과 비교해 볼까요?", Choices(id=f"{PICK}:{base}", kind="single", options=opts))
    item = next((it for it in plan["items"] if it["id"] == ids[1]), None)
    if item is None:
        return machine._end(n, "비교할 후보를 다시 골라 주세요.", None)
    plan["focus_id"] = item["id"]
    card = machine.improve_card(n)
    row = next(it for it in card.payload["items"] if it["id"] == item["id"])
    text = selection_text(item, row.get("paired"))
    return [Stage(current="improve"), card, *machine._end(n, text, actions(n, item))]


def edit(n, conv_id, base_id, ids):
    from agent import machine

    plan = n.improve or {}
    meta = machine._owned_improve_run(n, conv_id, base_id)
    if not meta or plan.get("base_run") != base_id or len(ids) != 2:
        return machine._end(n, "지금 비교하는 매대의 후보를 다시 골라 주세요.", None)
    source = next((it for it in plan["items"] if it["id"] == ids[0]), None)
    if not source:
        return machine._end(n, "수정할 후보를 다시 골라 주세요.", None)

    def invalid(message):
        return machine._end(n, message, actions(n, source))

    try:
        values = json.loads(ids[1])
    except ValueError:
        values = None
    if not isinstance(values, dict) or values.keys() != source["values"].keys():
        return invalid("지금 고른 후보에서 바꿀 값만 입력해 주세요.")
    for key, raw in values.items():
        if not isinstance(raw, str) or len(raw) > 100 or not raw.strip():
            return invalid("바꿀 값을 다시 적어 주세요.")
        value = raw.strip()
        if key in ("price", "volume"):
            digits = re.fullmatch(r"(\d{1,5}|\d{1,2},\d{3})\s*(?:원)?" if key == "price" else
                                  r"(\d{1,4}|\d,\d{3})\s*(?:ml)?", value, flags=re.I)
            if not digits:
                return invalid("가격은 원 단위로 입력해 주세요." if key == "price" else "용량은 mL 단위로 입력해 주세요.")
            values[key] = int(digits[1].replace(",", ""))
        else:
            values[key] = value
    base = improve.Base.of(meta["concept"])
    if why := improve.check_values(base, values, price_step=bool(meta.get("concept_prompt_version"))):
        return invalid("입력한 값을 확인해 주세요. " + " ".join(why))
    values = improve.diff(base, values)
    if not values:
        return invalid("원래 제품과 같은 값이에요. 비교할 값을 바꿔 주세요.")
    revised = next((it for it in plan["items"] if it["values"] == values), None)
    if revised is None:
        revised = machine._add_item(plan, base, values, "작업대에서 직접 정한 값이에요.")
        revised["evidence"] = []
    return choose(n, conv_id, [base_id, revised["id"]])
