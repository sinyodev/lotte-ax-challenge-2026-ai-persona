"""칠성이 1부(컨셉 기획)의 열린 대화 (지시서 09, docs/chilseong-part1.md 0절).

한 차례의 네 걸음
  읽기(모델): 기획자의 말 → 할 일 1~3개와 찾아볼 것 0~3개      agent/steps.py read
  찾기(코드): 고른 도구를 돌린다. 숫자는 여기서만 나온다          agent/find.py
  하기(모델과 코드): 노트를 고치고, 아이디어·컨셉을 내거나 고친다  이 파일 + agent/steps.py
  말하기(모델): 받아 준 것, 찾아본 것 하나, 보탤 것 하나          agent/voice.py

- 횟수가 아니라 문턱만 코드가 쥔다. 문턱은 둘: 컨셉 보드를 만드는 것, 확정하는 것. 둘 다 기획자가 말했을 때만 넘는다
  (읽기가 골라도 기획자의 말에 그 뜻이 없으면 넘지 않고 권하기만 한다).
- 기획자의 생각(방향)은 노트에 쌓고 뒤의 아이디어와 컨셉에 계속 싣는다.
- 대화마다의 노트는 대화 id로 메모리에 둔다. 서버가 다시 떠서 메모리에 없으면 대화 파일의 노트로 이어 간다(main.py, 지시서 11).
  파일도 없을 때만 끊겼다고 말한다. 멈춘 차례는 차례를 시작할 때의 노트로 되돌린다(snapshot, restore).
- 넓은 말("건강음료", "아침에 마시는 거")도 기획의 출발점이다. 제품 칸이 비어 있어도 아이디어를 낸다(지시서 11의 3절).
  정말 아무 실마리도 없을 때만 무엇을 생각하는지 묻고, 그때도 추천받기를 함께 내민다.
- 칠성이는 약속(app/contract/README.md 2절, v1.3)의 이벤트만 낸다. 한 차례에 고르는 묶음(choices, actions, confirm)은 하나다.
"""

from __future__ import annotations

import asyncio
import copy
import os
import re
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from agent import find, idea_spec, research, steps, voice
from agent import phrases as P
from agent.find import Found
from agent.note import IDEA_FIELDS, Note, Slot, summary
from agent.steps import NONE, ReadTask, StepFailed
from agent.voice import Addition, Bit
from onsite import concepts as task_concepts
from events import (ActionItem, Actions, Activity, Card, Choices, Confirm, ConfirmButton, ConfirmRow, Option, Say,
                    Speaker, Stage, Summary)
from tools import consumer, shelf, spoken, web
from tools.consumer import MIN_FOUND, Group, josa
from tools.occasion_display import show as show_occasion

CONVS: dict[str, Note] = {}

# 문턱의 말: 기획자의 말에 이 뜻이 있어야 넘는다
CONCEPT_CUES = ("컨셉", "콘셉트", "보드")
CONFIRM_CUES = ("확정", "이대로", "결정", "정할게", "정하자", "이걸로 가", "그걸로 가")
FIXED_TASKS = {"not_ready", "out_of_scope", "download", "report"}


def reset() -> None:
    CONVS.clear()


def has(conv_id: str) -> bool:
    return conv_id in CONVS


def adopt(conv_id: str, note: Note) -> None:
    """파일에서 되살린 노트로 이어 간다."""
    CONVS[conv_id] = note


def forget(conv_id: str) -> None:
    CONVS.pop(conv_id, None)


def snapshot(conv_id: str) -> Note | None:
    """차례를 시작할 때의 노트(멈추면 이것으로 되돌린다)."""
    n = CONVS.get(conv_id)
    return copy.deepcopy(n) if n is not None else None


def restore(conv_id: str, note: Note | None) -> None:
    if note is None:
        CONVS.pop(conv_id, None)
    else:
        CONVS[conv_id] = note


# 추천받기를 글로 쳤을 때(첫 화면의 칩 "칠성이에게 추천받기" 포함): 읽기를 거치지 않고 추천으로 간다
RECOMMEND_CUE = "추천받"
RECOMMEND_MAX_CHARS = 15


def wants_recommend(text: str) -> bool:
    t = text.replace(" ", "")
    return RECOMMEND_CUE in t and len(t) <= RECOMMEND_MAX_CHARS


# 칠성이가 무엇을 하는지 묻는 말(첫 화면의 칩 포함): 읽기를 거치지 않고 고정된 소개로 답한다
ABOUT_CUES = ("무엇을할수있", "뭘할수있", "뭐할수있", "어떤일을하", "무슨일을하")
ABOUT_MAX_CHARS = 25


def wants_about(text: str) -> bool:
    t = text.replace(" ", "")
    return len(t) <= ABOUT_MAX_CHARS and any(c in t for c in ABOUT_CUES)


def about_choices(n: Note, shown: str) -> Choices:
    """소개 뒤의 칩: 아직 안 본 물음들과 추천받기."""
    options = [Option(id=i, label=label) for i, label in P.ABOUT_CHIPS if i != shown]
    return Choices(id=n.next_id("about"), kind="single", options=[*options, Option(id="recommend", label=P.CHIP_RECOMMEND)])


def has_clue(n: Note) -> bool:
    """기획의 실마리가 하나라도 있는가(제품, 타깃, 상황, 바라는 것, 기획자의 생각, 아이디어)."""
    return bool(n.product.value or n.target.value or n.occasion.value or n.need.value or n.thoughts or n.ideas)


# ---------- 한 차례에 모으는 것 ----------


@dataclass
class TurnLog:
    text: str
    ids: list[str]
    conv_id: str = ""
    received: list[Bit] = field(default_factory=list)
    founds: list[Found] = field(default_factory=list)  # 이번에 찾은 것(읽기가 고른 차례대로)
    addition: Addition | None = None
    answer_to: str | None = None
    fixed: list[str] = field(default_factory=list)  # 모델 없이 하는 고정된 말
    offer: Any = None  # 이번 차례에 내밀 묶음
    stop: bool = False  # 고르는 차례나 실패로 말하기를 건너뛴다
    failed: str | None = None  # 하다가 막힌 일
    product_new: bool = False
    ideas_changed: bool = False
    ideas_again: bool = False  # 이미 있던 보드에 아이디어를 새로 냈다(다른 아이디어 보기)
    concepts_changed: bool = False
    note_changed: list[str] = field(default_factory=list)  # 아이디어가 있는데 바뀐 칸
    thought_added: bool = False
    confirmed: bool = False
    suggest_concepts: bool = False  # 문턱을 넘지 않고 권하기만 했다


# ---------- 카드 ----------


def brief_card(n: Note) -> Card:
    fields = []
    values = {"product": n.product, "channel": Slot(P.channel(n.shelf), None), "target": n.target,
              "occasion": n.occasion, "need": n.need}
    for key, label in P.FIELD_LABELS.items():
        s = values[key]
        f: dict[str, Any] = {"key": key, "label": label, "value": s.value, "state": "set" if s.value else "empty"}
        if key == "channel":
            f["note"] = P.CHANNEL_NOTE
        elif s.value and s.by == "chilseong":
            f["note"] = P.BY_CHILSEONG
        fields.append(f)
    payload: dict[str, Any] = {"fields": fields}
    if n.thoughts:
        payload["thoughts"] = list(n.thoughts)
    return Card(id="brief", stage="idea", kind="brief", title=P.CARD_BRIEF, status="ready", payload=payload)


def evidence_card(n: Note, status: str = "ready") -> Card:
    return Card(id="evidence", stage="idea", kind="evidence", title=P.CARD_EVIDENCE, status=status,
                payload={"items": n.evidence} if status == "ready" else None)


def ideas_card(n: Note, status: str = "ready") -> Card:
    payload = None
    if status == "ready":
        payload = {"basis": P.ideas_basis(n.target.value, n.occasion.value, n.thoughts,
                                          sum(1 for e in n.evidence if e["origin"] == "web"),
                                          n.product.value or None),
                   "items": [_idea_public(i) for i in n.ideas]}
    return Card(id="ideas", stage="idea", kind="ideas", title=P.CARD_IDEAS, status=status, payload=payload,
                origin="suggestion")


def concepts_card(n: Note, status: str = "ready") -> Card:
    payload = {"items": [concept_public(n, c) for c in n.concepts]} if status == "ready" else None
    if payload is not None and len(n.concepts) > 1:  # 확정한 보드에 표시(보드가 둘 이상일 때만 뜻이 있다)
        ok = {c["id"] for c in confirmed_concepts(n)}
        for item in payload["items"]:
            if item["id"] in ok:
                item["confirmed"] = True
    if payload is not None and n.confirmed:
        payload["locked"] = True  # 확정한 뒤에는 규격을 고를 수 없다(지시서 33 후속)
    return Card(id="concepts", stage="concept", kind="concepts", title=P.CARD_CONCEPTS, status=status,
                payload=payload, origin="suggestion")


def _public(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if not k.startswith("_") and v is not None}


def _idea_public(d: dict[str, Any]) -> dict[str, Any]:
    """아이디어 카드의 한 칸. 제품 사양(지시서 33)은 값이 있는 것만 화면의 형식으로 보낸다."""
    out = {k: v for k, v in _public(d).items() if k not in idea_spec.SPEC_KEYS}
    out.update(idea_spec.public(d))
    return out


# ----- 컨셉 카드(약속 v1.4, 지시서 12): 위쪽 예시 시안과 아래쪽 제품 특징 -----

CONCEPT_TOP = ("id", "name", "headline", "benefit", "points", "price", "pack")
ZERO_WORDS = ("제로", "무설탕", "당 0", "무당")


def product_type(n: Note) -> str | None:
    """제품 유형: 노트의 제품과 종류. 제품의 이름에 종류가 이미 들었으면 제품만."""
    product, kind = n.product.value, n.kind_name or n.shelf_kind
    if product and kind and kind not in product and product not in kind:
        return f"{product} ({kind})"
    return product or kind


def concept_spec(n: Note, c: dict[str, Any]) -> list[dict[str, str]]:
    """제품 특징의 줄(이 순서). 값이 없는 줄은 내지 않는다. 경쟁 제품이 없으면 차별점도 내지 않는다."""
    carb = c.get("_carb")
    on = idea_spec.shelf_variant(c)  # 규격의 표가 있으면 용기와 용량, 가격(같으면), 채널의 줄은 표가 대신한다(지시서 33)
    values = {
        "type": product_type(n),
        "flavor": c.get("_flavor"),
        "pack": None if on else c.get("pack"),
        "sugar_caffeine": c.get("_sugar"),
        "carbonation": carb if carb and carb != NONE else None,
        "storage": c.get("storage"),
        "target": n.target.value,
        "occasion": show_occasion(c.get("_occasion") or n.occasion.value or ""),
        "channel": None if c.get("channels") else P.spec_channel(n.shelf),
        "price": None if on and on.get("price") and _price_won(c.get("price")) == on["price"] else c.get("price"),
        "rivals": "\n".join(c.get("_rivals") or []),
        "own": c.get("_own"),
        "pod": c.get("_pod") if c.get("_rivals") else None,
    }
    return [{"key": k, "label": label, "value": v.strip()} for k, label in P.SPEC_LABELS.items()
            if (v := values[k]) and v.strip()]


def concept_public(n: Note, c: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {k: c.get(k) or ("" if k != "points" else []) for k in CONCEPT_TOP}
    out["spec"] = concept_spec(n, c)
    if c.get("insight"):  # 소비자 인식 한 문장(11-25, 옛 컨셉에는 없다)
        out["insight"] = c["insight"]
    out.update(idea_spec.public(c))
    if c.get("changed"):
        out["changed"] = c["changed"]
    return out


def concept_values(n: Note, c: dict[str, Any]) -> dict[str, Any]:
    """고쳐진 칸을 찾는 데 쓰는 값: 예시 시안의 글과 제품 특징의 줄."""
    vals: dict[str, Any] = {k: c.get(k) for k in ("headline", "name", "benefit", "insight", "points", "pack", "price")}
    vals.update({r["key"]: r["value"] for r in concept_spec(n, c)})
    return vals


def _is_zero(n: Note, texts: list[str]) -> bool:
    text = " ".join([n.product.value or "", *texts])
    return n.kind == "탄산음료(저칼로리)" or any(w in text for w in ZERO_WORDS)


def _line(p: shelf.Product) -> str:
    return P.rival_line(p.name, p.price, p.promo if shelf.has_promo(p) else None)


def concept_input(n: Note, cid: str, idea: dict[str, Any], container: str, volume: int, zero: bool,
                  has_price: bool) -> steps.ConceptInput:
    """경쟁 제품(다른 회사)과 자사 유사 제품은 코드가 매대 자료에서 고른다(이름은 화면용 이름, 가격과 행사는 매대 자료의 값)."""
    found = shelf.rivals(n.shelf_kind, container, volume, zero)
    own = shelf.own_similar(n.shelf_kind, container, volume, zero)
    fizz = shelf.kind_fizz(n.shelf_kind) if n.shelf_kind else None
    return steps.ConceptInput(id=cid, idea=idea, rivals=[_line(p) for p in found], has_price=has_price, zero=zero,
                              fizz=fizz, own=_line(own) if own else None, rival_names=[p.name for p in found],
                              own_name=own.name if own else None)


# 컨셉에 적은 매대 제품(경쟁 제품, 자사 유사 제품)의 판. 이보다 옛것이면 대화를 열 때 코드가 다시 고른다(지시서 14)
SHELF_V = 4


def put_shelf(c: dict[str, Any], ci: steps.ConceptInput) -> None:
    """컨셉에 매대에서 고른 제품을 적는다. 글(_rivals, _own)과 함께 화면용 이름도 둔다(제안서가 칸을 다시 읽는다)."""
    c["_rivals"], c["_rival_names"] = list(ci.rivals), list(ci.rival_names)
    c["_own"], c["_own_name"] = ci.own, ci.own_name
    c["_shelf_v"] = SHELF_V
    if not ci.rivals:
        c["_pod"] = ""


def concept_zero(n: Note, c: dict[str, Any]) -> bool:
    return _is_zero(n, [c.get("name", ""), c.get("_flavor", ""), c.get("_sugar", ""), *(c.get("points") or [])])


def reselect_shelf(n: Note, c: dict[str, Any]) -> None:
    """옛 컨셉(경쟁 제품에 자사 제품이 섞였거나 자사 유사 제품이 없던 때)의 매대 제품을 지금 규칙으로 다시 고른다.
    모델을 부르지 않는다. 차별점은 그대로 둔다(경쟁 제품이 없어지면 비운다)."""
    ci = concept_input(n, c.get("id", ""), c, c.get("_container") or "", int(c.get("_volume") or 0),
                       concept_zero(n, c), True)
    put_shelf(c, ci)


def add_evidence(n: Note, founds: list[Found]) -> bool:
    seen = {(e["text"], e["source"]) for e in n.evidence}
    added = False
    for f in founds:
        if (f.text, f.source) in seen:
            continue
        n.evidence.append(f.evidence(len(n.evidence) + 1))
        seen.add((f.text, f.source))
        added = True
    return added


# ---------- 묶음(칩과 버튼) ----------


def _actions(n: Note, prefix: str, items: list[tuple[str, str]]) -> Actions:
    return Actions(id=n.next_id(prefix), actions=[ActionItem(id=i, label=l, primary=(k == 0) or None)
                                                   for k, (i, l) in enumerate(items[:3])])


def pick_choices(n: Note) -> Choices:
    names = [i["name"] for i in n.ideas]

    def label(i: dict[str, Any]) -> str:
        """이름이 같은 카드(규격별로 나눈 아이디어)는 규격을 붙여 가른다: '밀키스 화채 PET 500ml'."""
        if names.count(i["name"]) < 2:
            return i["name"]
        on = idea_spec.shelf_variant(i)
        return f'{i["name"]} {idea_spec.label(on) if on else i.get("pack") or ""}'.strip()

    return Choices(id=n.next_id("pick-ideas"), kind="multi", on_card="ideas",
                   options=[Option(id=i["id"], label=label(i)) for i in n.ideas])


def product_choices(n: Note) -> Choices:
    return Choices(id=n.next_id("ask-product"), kind="single", options=[Option(id="recommend", label=P.CHIP_RECOMMEND)])


def default_offer(n: Note, log: TurnLog) -> Any:
    if n.last_run and n.concepts and (n.confirmed or n.stage == "concept"):
        # 테스트를 한 대화(지시서 18의 D): 결과와 결과 보고서로 바로 갈 수 있게 한다
        return _actions(n, "next", [(SHOW_RESULT, P.BTN_RESULT), ("go-shelf", P.BTN_SHELF), (REPORT, P.BTN_REPORT)])
    if n.confirmed:
        return _actions(n, "next", [("go-shelf", P.BTN_SHELF), ("download", P.BTN_DOWNLOAD)])
    if n.stage == "concept" and n.concepts:
        return _actions(n, "concept-board", [("confirm-concepts", P.BTN_CONFIRM), ("more-ideas", P.BTN_MORE_IDEAS)])
    if n.ideas:
        if (log.note_changed or log.thought_added) and not log.ideas_changed:
            label = P.BTN_IDEAS_THOUGHT if log.thought_added else P.BTN_IDEAS_AGAIN
            return _actions(n, "ideas-again", [("ideas-again", label), ("make-concepts", P.BTN_MAKE_CONCEPTS)])
        # 아이디어가 둘 이상이면 카드에서 고르게 한다("두 규격 모두…"는 끼워 맞춘 이름이라 뺐다. 참가자의 검수 11-25)
        label = P.BTN_PICK_IDEAS if len(n.ideas) >= 2 else P.BTN_MAKE_CONCEPTS
        return _actions(n, "idea-board", [("make-concepts", label), ("more-ideas", P.BTN_MORE_IDEAS)])
    if has_clue(n):
        items = [("ideas", P.BTN_IDEAS_THOUGHT if n.thoughts else P.BTN_IDEAS)]
        who = next((f for f in log.founds if f.tool == "who" and "group" in f.extra), None)
        if who and not n.target.value:
            g = who.extra["group"]
            items.append((f"target:{g.id}", P.btn_target(g.label)))
        return _actions(n, "next-step", items)
    return product_choices(n)


def offer_lines(offer: Any) -> str:
    if offer is None:
        return "(없음)"
    if isinstance(offer, Confirm):  # 확인 카드(매대 테스트를 시작할지)에는 버튼 둘이 있다
        items = [offer.confirm, offer.cancel]
    else:
        items = offer.options if isinstance(offer, Choices) else offer.actions
    return ", ".join(f"'{x.label}'(id {x.id})" for x in items)


# ---------- 한 차례 ----------


async def turn(conv_id: str, text: str, reply_ids: list[str], n_user: int,
               today: date | None = None, trace: dict[str, Any] | None = None,
               reply_to: str | None = None) -> AsyncIterator[Any]:
    """_turn의 이벤트를 그대로 내되, 끝난 하는 일의 이름은 그 차례에 실제로 한 일의 과거형으로 바꾼다
    ("찾아보는 중" → 아이디어를 냈으면 "아이디어를 냈어요"). "~는 중"이 끝난 차례에 남지 않게 한다."""
    last: dict[str, str] = {}
    async for ev in _turn(conv_id, text, reply_ids, n_user, today, trace, reply_to):
        if isinstance(ev, Activity):
            if ev.status == "running":
                if ev.label != P.ACT_LOOK or last.get(ev.id) in (None, P.ACT_READ):
                    last[ev.id] = ev.label
            else:
                did = last.get(ev.id, ev.label) if ev.label == P.ACT_LOOK else ev.label
                ev = Activity(id=ev.id, label=P.act_done(did), status="done")
        yield ev


async def _turn(conv_id: str, text: str, reply_ids: list[str], n_user: int,
                today: date | None = None, trace: dict[str, Any] | None = None,
                reply_to: str | None = None) -> AsyncIterator[Any]:
    """기획자의 말 하나에 칠성이의 이벤트를 차례로 낸다. trace에는 읽기가 고른 일을 적는다(대화 파일에 남는다).
    reply_to: 칩이나 버튼의 답이면 그 묶음의 id(metadata.reply.to). 결과 카드의 "이 손님에게 묻기"는 "visitor"(지시서 17)."""
    trace = trace if trace is not None else {}
    if conv_id.startswith("w7-demo-") and os.environ.get("AX_LLM") == "fake":
        from agent.diagnose import demo_turn

        yield Stage(current="result")
        for event in demo_turn(text, reply_ids, n_user):
            yield event
        return
    n = CONVS.get(conv_id)
    if n is None:
        if n_user > 1:
            yield Say(text=P.SESSION_LOST)
            return
        n = CONVS[conv_id] = Note()
        yield Stage(current="idea")
    for i in n.ideas:
        i.pop("changed", None)
    for c in n.concepts:
        c.pop("changed", None)

    from agent import diagnose

    picked = diagnose.pick_ids(reply_ids)  # 확정 차례의 대화 버튼: 분석 카드의 버튼과 같은 길(읽기를 거치지 않는다)
    if picked is not None:
        reply_to, reply_ids = diagnose.REPLY_TO, picked
    if reply_to == diagnose.REPLY_TO:
        trace["read"] = {"skipped": "컨셉 보드 분석의 선택", "tasks": [], "lookups": []}
        for ev in diagnose.choose(n, conv_id, reply_ids):
            yield ev
        return

    from agent import improve_review

    if not reply_ids and (typed := improve_review.typed_reply(n, text)):
        reply_to, reply_ids = typed
    if reply_to and reply_to.startswith("edit-candidate:"):
        for ev in improve_review.edit(n, conv_id, reply_to.split(":", 1)[1], reply_ids):
            yield ev
        return
    if reply_to and reply_to.startswith(improve_review.PICK + ":") and len(reply_ids) == 1:
        for ev in improve_review.choose(n, conv_id, [reply_to.split(":", 1)[1], reply_ids[0]]):
            yield ev
        return
    if len(reply_ids) == 1 and reply_ids[0].startswith(improve_review.MENU + ":"):
        for ev in improve_review.choose(n, conv_id, [reply_ids[0].split(":", 1)[1]]):
            yield ev
        return

    if reply_to == "w7-adopt":
        trace["read"] = {"skipped": "개선안 채택", "tasks": [], "lookups": []}
        for ev in _adopt_improvement(n, conv_id, reply_ids):
            yield ev
        return

    from agent import followup  # 후속 개선(약속 v1.20): 읽기를 거치지 않는다

    if followup.wants(n, text, reply_ids, reply_to):
        trace["read"] = {"skipped": "후속 개선", "tasks": [], "lookups": []}
        async for ev in followup.handle(n, conv_id, reply_ids, text):
            yield ev
        return

    # 한 손님에게 묻기(지시서 17의 A): 부르는 것과 부른 동안의 말은 읽기를 거치지 않는다
    if not n.interview_plan and isinstance(n.last_offer, Choices) and n.last_offer.id == P.GROUP_TO and n.last_offer.options:
        from shelftest import group_flow
        previous = group_flow._route([n.last_offer.options[0].id])
        if len(previous) >= 5 and previous[0] == "start":
            n.interview_plan = {"run": previous[1], "question": previous[2]}
    if not reply_ids and isinstance(n.last_offer, Choices) and n.last_offer.id == P.GROUP_TO:
        picked = next((o for o in n.last_offer.options if o.label == text.strip()), None)
        if picked:
            reply_to, reply_ids = P.GROUP_TO, [picked.id]
    if not reply_ids and n.interview_plan and text.strip() != P.BTN_ASK_GROUP and text.strip() not in CARD_WORDS:
        from shelftest import group_flow
        if plan_ids := group_flow.typed_plan(n, text):
            reply_to, reply_ids = P.GROUP_TO, plan_ids
        elif not reply_to:
            yield Say(text="새 질문을 적거나 아래에서 인터뷰 방식을 골라 주세요.")
            if n.last_offer:
                yield n.last_offer
            return
    if len(reply_ids) == 1 and reply_ids[0].startswith(GROUP_OPEN + ":"):
        reply_to, reply_ids = P.GROUP_TO, ["edit", reply_ids[0].split(":", 1)[1]]
    elif not reply_ids and text.strip() == P.BTN_OTHER_INTERVIEW:
        options = getattr(n.last_offer, "actions", []) or getattr(n.last_offer, "options", [])
        restart = next((o.id for o in options if o.id.startswith(GROUP_OPEN + ":")), None)
        reply_to, reply_ids = P.GROUP_TO, ["edit", restart.split(":", 1)[1] if restart else n.last_run or ""]
    if reply_to == "w7-group" or GROUP_OPEN in reply_ids or (not reply_ids and text.strip() == P.BTN_ASK_GROUP):
        from shelftest import group_flow

        ids = reply_ids if reply_to == "w7-group" else ["open", n.last_run or ""]
        async for event in group_flow.handle(n, conv_id, ids, text):
            yield event
        return
    n.interview_plan = None
    if ASK_SHOPPER in reply_ids:  # 저장된 한 명 인터뷰 버튼도 같은 손님 호출로 이어진다.
        who = _shopper_to_ask(n, n.last_run)
        reply_to, reply_ids = P.INTERVIEW_TO, [n.last_run or "", who or ""]
    if reply_to == P.INTERVIEW_TO:
        trace["read"] = {"skipped": "손님 부르기", "tasks": [], "lookups": []}
        for ev in _call_visitor(n, conv_id, reply_ids):
            yield ev
        return
    if n.interview is not None:
        if _interview_continues(n, text, reply_ids):
            trace["read"] = {"skipped": "손님에게 묻기", "tasks": [], "lookups": []}
            async for ev in _interview_turn(n, conv_id, text, reply_ids):
                yield ev
            return
        n.interview = None  # 다른 버튼을 누르면 손님은 조용히 돌아간다

    about = next((i for i in reply_ids if i in P.ABOUT), None) or ("about" if not reply_ids and wants_about(text) else None)
    if about:
        trace["read"] = {"skipped": "칠성이 소개", "tasks": [], "lookups": []}
        for ev in _end(n, P.ABOUT[about], about_choices(n, about)):
            yield ev
        return

    # 추천받기: 모델 없이 코드가 고른다(지시서 05). 추천을 고르면 그 제품을 노트에 적는다.
    # 칩으로 눌러도, 글로 "추천받기"라고 쳐도(첫 화면의 칩도 글로 온다) 같은 길로 간다(지시서 11).
    if "recommend" in reply_ids or (not reply_ids and wants_recommend(text)):
        trace["read"] = {"skipped": "추천받기", "tasks": ["recommend"], "lookups": []}
        async for ev in _recommend(n, n.next_id("recommend")):
            yield ev
        return
    # 매대에 올릴 규격 바꾸기(지시서 33): "PET 500ml를 매대에 올릴 규격으로" 같은 말은 모델 없이 코드가 바꾼다
    switched = switch_variant(n, text, reply_ids, reply_to)
    if switched is not None:
        trace["read"] = {"skipped": "매대에 올릴 규격", "tasks": [], "lookups": []}
        for ev in switched:
            yield ev
        return
    rec = next((r for r in n.recs if r.id in reply_ids), None)
    shelf_task = _shelf_shortcut(n, text, reply_ids, reply_to)
    board_task = None if shelf_task is not None else _board_shortcut(n, reply_ids)

    act = n.next_id("work")
    log = TurnLog(text=text, ids=reply_ids, conv_id=conv_id)
    if board_task is not None:
        # 컨셉 보드 만들기·확정의 버튼(아이디어 id나 보드 id가 붙은 답): 읽지 않고 바로 한다(11-25)
        tasks = [board_task]
        read = steps.Read(tasks=tasks)
        log.ids = [("make-concepts" if board_task.do == "concepts" else "confirm-concepts"), *board_task.ids]
        trace["read"] = {"skipped": "컨셉 보드", "tasks": [t.model_dump(exclude_defaults=True) for t in tasks],
                         "lookups": []}
    elif shelf_task is not None:
        # 매대 테스트의 버튼과 확인(지시서 15): 읽기를 거치지 않는다
        tasks = [shelf_task]
        read = steps.Read(tasks=tasks)
        trace["read"] = {"skipped": "매대 테스트", "tasks": [t.model_dump(exclude_defaults=True) for t in tasks],
                         "lookups": []}
    elif "retry" in reply_ids and n.retry:
        tasks, read = n.retry
        n.retry = None
        trace["read"] = {"skipped": "다시 해 보기", "tasks": [t.model_dump(exclude_defaults=True) for t in tasks],
                         "lookups": []}
    elif rec is not None:
        tasks = [ReadTask(do="note", slot="product", value=rec.product)]
        read = steps.Read(tasks=tasks, lookups=[steps.Lookup(tool="who")], product_kind=rec.kind,
                          shelf_kind=rec.shelf_kind or NONE)
        n.recs = []
        trace["read"] = {"skipped": "추천 고름", "tasks": [t.model_dump(exclude_defaults=True) for t in tasks],
                         "lookups": [{"tool": "who"}]}
    else:
        yield Activity(id=act, label=P.ACT_READ, status="running")
        try:
            read = await steps.read(_read_context(n), _planner_line(n, text, reply_ids),
                                    list(consumer.all_occasions().values()))
        except StepFailed:
            yield Activity(id=act, label=P.ACT_READ, status="done")
            yield Say(text=P.MISREAD)
            if n.last_offer is not None:
                yield _again(n, n.last_offer)
            return
        tasks = read.tasks
        if idea_spec.pasted_task_spec(text) and any(t.do == "ideas" for t in tasks):
            # 과제 컨셉의 사양을 통째로 붙여 넣은 말은 방향이 아니라 기획자의 아이디어다(지시서 33 후속)
            tasks = [ReadTask(do="my_idea", text=text) if t.do == "ideas" else t for t in tasks]
            read = read.model_copy(update={"tasks": tasks})
        trace["read"] = {"tasks": [t.model_dump(exclude_defaults=True) for t in tasks],
                         "lookups": [lk.model_dump(exclude_defaults=True) for lk in read.lookups]}
        print("[read] " + "; ".join(f"{t.do}{'(' + t.slot + '=' + t.value + ')' if t.slot else ''}"
                                    f"{' ids=' + ','.join(t.ids) if t.ids else ''}{' text=' + t.text if t.text else ''}"
                                    for t in tasks)
              + " | 찾기: " + (", ".join(f"{lk.tool}{'(' + lk.arg + ')' if lk.arg else ''}" for lk in read.lookups) or "-"),
              file=sys.stderr, flush=True)

    if any(t.do == "recommend" for t in tasks):
        for t in tasks:  # 함께 받은 생각과 노트는 적어 둔다
            if t.do == "note":
                _note(n, log, t, read)
            elif t.do == "thought":
                _thought(n, log, t.text or t.value)
        yield Activity(id=act, label=P.ACT_READ, status="done")
        async for ev in _recommend(n, n.next_id("recommend")):
            yield ev
        return

    # 매대 테스트의 버튼은 찾아볼 것이 없다. "찾아보는 중"을 붙이지 않고, 실제로 하는 일(결과 정리 등)만 보인다
    quiet, open_label = shelf_task is not None, None
    async for ev in _do(n, log, act, tasks, read, today):
        if quiet and isinstance(ev, Activity):
            if ev.label == P.ACT_LOOK:
                if open_label is None:
                    continue
                ev = Activity(id=ev.id, label=open_label, status=ev.status)
            open_label = ev.label if ev.status == "running" else None
        yield ev
    if log.failed:
        yield Activity(id=act, label=P.ACT_LOOK, status="done")
        n.remember_say(P.FAILED[log.failed])
        yield Say(text=n.last_say)
        offer = _actions(n, "retry", [("retry", P.BTN_RETRY)])
        n.last_offer = offer
        yield offer
        return
    if log.stop:
        return

    # 말하기
    if log.fixed and not (log.received or log.founds or log.answer_to or log.addition):
        yield Activity(id=act, label=P.ACT_LOOK, status="done")
        n.remember_say(" ".join(dict.fromkeys(log.fixed)))
        yield Say(text=n.last_say)
    else:
        for f in log.fixed:
            log.received.append(Bit(fact=f"고정된 말: {f}", sentence=f))
        said = await _speak(n, log)
        yield Activity(id=act, label=P.ACT_LOOK, status="done")
        yield said
    offer = log.offer or default_offer(n, log)
    n.last_offer = offer
    yield offer


def _again(n: Note, offer: Any) -> Any:
    prefix = offer.id.rsplit("-", 1)[0]
    new = offer.model_copy(update={"id": n.next_id(prefix)})
    n.last_offer = new
    return new


def _read_context(n: Note) -> str:
    lines = [summary(n)]
    if n.evidence:
        lines.append("이미 찾아본 것: " + "; ".join(e["text"] for e in n.evidence[-6:]))
    if n.improve and n.improve.get("items"):
        from agent import improve

        items = n.improve["items"]
        lines.append("개선안 표(improve_rerun의 ids에는 이 id를 적는다. 기획자는 'A안'처럼 id로도, '가격 변경안'처럼 이름으로도 말한다)")
        lines += [f"- id {it['id']} ({improve.plan_name(items, it)}): {it['change']}"
                  + (" [테스트함]" if it.get("run_id") else " [아직 테스트 안 함]") for it in items]
    lines.append(f"칠성이가 방금 한 말: {n.last_say or '(없음. 대화의 첫 차례)'}")
    lines.append(f"칠성이가 방금 내민 칩: {offer_lines(n.last_offer)}")
    return "\n".join(lines)


def _planner_line(n: Note, text: str, ids: list[str]) -> str:
    if not ids:
        return text
    return f"{text}\n(기획자가 칩을 눌러 답했다. 누른 칩의 id: {', '.join(ids)})"


# ---------- 하기 ----------


async def _do(n: Note, log: TurnLog, act: str, tasks: list[ReadTask], read: Any,
              today: date | None) -> AsyncIterator[Any]:
    # 1) 노트와 생각을 먼저 적는다(찾아볼 것이 노트의 칸을 쓴다)
    for t in tasks:
        if t.do == "note":
            _note(n, log, t, read)
        elif t.do == "thought":
            _thought(n, log, t.text or t.value)

    topic = research.selected_topic(log.text) if n.stage in ("idea", "concept") and not n.confirmed else ""
    if topic and not n.product.value:
        _note(n, log, ReadTask(do="note", slot="product", value=topic), read)

    # 2) 찾기
    yield Activity(id=act, label=P.ACT_LOOK, status="running")
    lookups = [(lk.tool, lk.arg) for lk in read.lookups]
    if log.product_new and not lookups:
        lookups.append(("who", ""))
    for tool, arg in lookups:
        if tool == "news":
            continue
        log.founds += find.run(tool, arg, n)
    requested = next((arg.strip() for tool, arg in lookups if tool == "news" and arg.strip()), None)
    query = requested or topic or n.product.value
    if not query and not n.web_done and any(t.do in ("ideas", "concepts", "my_idea") for t in tasks):
        query = next(iter(n.thoughts), None) or next((idea["name"] for idea in n.ideas), None)
    if query and not n.confirmed and n.stage in ("idea", "concept") and (
        query not in n.web_done or any(tool == "news" for tool, _ in lookups)
    ):
        yield evidence_card(n, "loading")
        async for event in research.investigate(n, log, query, today, explicit=bool(topic or requested)):
            yield event
        yield Activity(id=act, label=P.ACT_LOOK, status="running")
    if add_evidence(n, log.founds) or log.product_new:
        yield evidence_card(n)

    # 3) 할 일을 차례로
    for t in tasks:
        if t.do in ("note", "thought"):
            continue
        handler = HANDLERS.get(t.do)
        if handler is None:
            continue
        async for ev in handler(n, log, act, t, today):
            yield ev
        if log.stop:
            return

    yield brief_card(n)
    if log.ideas_changed:
        yield ideas_card(n)
    if log.concepts_changed:
        yield concepts_card(n)
    if log.addition is None and not all(t.do in FIXED_TASKS for t in tasks):
        log.addition = _addition(n, log)


def _same(product: str, kind: str | None) -> bool:
    if not kind:
        return True
    norm = lambda s: s.replace(" ", "").removesuffix("음료")  # noqa: E731
    return norm(product) == norm(consumer.kind_name(kind))


def _note(n: Note, log: TurnLog, t: ReadTask, read: Any) -> None:
    slot, value = t.slot, t.value.strip()
    if slot not in ("product", "target", "occasion", "need") or not value:
        return
    if slot == "occasion":
        value = show_occasion(value)  # 옛 이름으로 말해도 화면에는 새 이름
    old = n.slot(slot).value
    setattr(n, slot, Slot(value, "planner"))
    if slot == "product":
        kind = None if read.product_kind == NONE else read.product_kind
        shelf_kind = None if read.shelf_kind == NONE else read.shelf_kind
        n.kind, n.shelf_kind = kind, shelf_kind
        n.shelf = (shelf.shelf_of_kind(shelf_kind) if shelf_kind else None) or consumer.shelf_of(kind)
        n.same_kind = _same(value, kind)
        if old != value:
            log.product_new = True
        log.received.append(Bit(fact=f"기획할 제품을 '{value}'{josa(value, '으로/로')} 받아 적었다",
                                sentence=f"{value}{josa(value, '으로/로')} 기획해 볼게요.", names=[value]))
    elif slot == "target":
        age = None if read.target_age == NONE else read.target_age
        sex = None if read.target_sex == NONE else read.target_sex
        n.group = Group(age=age, sex=sex, label=value) if (age or sex) else None
        log.received.append(Bit(fact=f"마실 사람을 '{value}'{josa(value, '으로/로')} 받았다"
                                     f"(말할 때는 \"{value}{josa(value, '이/가')} 마실\"처럼 풀어 쓴다)",
                                sentence=f"{value}{josa(value, '이/가')} 마실 음료로 할게요.", names=[value]))
    elif slot == "occasion":
        n.occasion_code = None if read.occasion_code == NONE else read.occasion_code
        n.occasion_code = n.occasion_code or consumer.occasion_code_of(value)
        when = P.when_phrase(None, value)
        log.received.append(Bit(fact=f"마시는 때를 '{value}'{josa(value, '으로/로')} 받았다(말할 때는 \"{when}\"처럼 풀어 쓴다)",
                                sentence=f"{when}{josa(when, '으로/로')} 할게요.", names=[value, when]))
    else:
        log.received.append(Bit(fact=f"마시는 사람이 가장 바라는 것을 '{value}'{josa(value, '으로/로')} 받았다",
                                sentence=f"가장 바라는 건 '{value}'{josa(value, '으로/로')} 할게요.", names=[value]))
    if n.ideas and old != value and slot != "need":
        log.note_changed.append(slot)


def _norm_thought(t: str) -> str:
    return re.sub(r"[\s.,!?~]", "", t)


def add_thought(thoughts: list[str], text: str) -> bool:
    """기획의 방향 하나를 쌓는다. 뜻이 같은 것(한쪽이 다른 쪽을 품으면)은 하나로 합치고, 새로 받은 것이면 참."""
    t = text.strip()
    key = _norm_thought(t)
    if not key:
        return False
    for i, old in enumerate(thoughts):
        ok = _norm_thought(old)
        if key == ok or key in ok:
            return False  # 이미 있는 방향
        if ok in key:
            thoughts[i] = t  # 더 자세히 말한 것으로 바꾼다
            return True
    thoughts.append(t)
    return True


def _thought(n: Note, log: TurnLog, text: str) -> None:
    t = text.strip()
    if not t or not add_thought(n.thoughts, t):
        return  # 이미 받은 방향은 다시 받아 주지 않는다(되풀이하지 않는다)
    log.thought_added = True
    log.received.append(Bit(fact=f"기획자가 말한 방향 '{t}'{josa(t, '을/를')} 받았다(꺾지 않고 이 방향으로 간다. "
                                 "말할 때는 '생각', '방향' 같은 이름표를 붙이지 않고 그 말을 문장에 녹인다)",
                            sentence=f"'{t}' 쪽으로 기획할게요.", names=[t]))


# ----- 아이디어 -----


def _fill_from_data(n: Note, log: TurnLog) -> None:
    """타깃이나 상황이 비어 있으면 찾아본 것으로 정하고 "칠성이가 정함"으로 적는다(기획자가 고칠 수 있다)."""
    bits = []
    if not n.target.value and n.kind:
        rows = consumer.top_groups(n.kind, 1)
        if rows and rows[0].n >= MIN_FOUND:
            g = rows[0].group
            n.target, n.group = Slot(g.label, "chilseong"), g
            bits.append(f"타깃은 {g.label}")
    if not n.occasion.value and n.kind:
        ranks = consumer.occasions(n.kind, n.group or Group(), n.shelf)
        if ranks:
            o = ranks[0].occasion
            n.occasion, n.occasion_code = Slot(o.name, "chilseong"), o.code
            bits.append(f"음용 상황은 '{o.name}'")
    if bits:
        when = P.when_phrase(n.target.value, n.occasion.value)
        log.received.append(Bit(fact=f"누가 언제 마실지는 칠성이가 정했다: \"{when}\"(기획자가 바꿀 수 있다)",
                                sentence=f"{when}{josa(when, '으로/로')} 잡았어요.",
                                names=[n.target.value or "", n.occasion.value or "", when]))


def _context_found(n: Note) -> tuple[list[str], list[str]]:
    facts = [f"{e['text']} ({e['source']})" for e in n.evidence if e["origin"] != "web"]
    claims = [f"{e['text']} (출처: {e['source']})" for e in n.evidence if e["origin"] == "web"]
    return facts, claims


def _task_to_add(n: Note, log: TurnLog, direction: str) -> dict[str, Any] | None:
    """기획 노트의 제품 이름이나 기획자의 말이 과제의 컨셉이고, 보드에 그 컨셉의 아이디어가 아직 없으면 그 컨셉(11-25)."""
    on_board = {i.get("_task_concept") for i in n.ideas}
    on_board |= {hit["id"] for i in n.ideas if (hit := task_concepts.match(i.get("name") or ""))}
    for text in (n.product.value, log.text, direction, *reversed(n.thoughts)):
        hit = task_concepts.match(text or "")
        if hit:
            return None if hit["id"] in on_board else hit
    return None


async def _ideas(n: Note, log: TurnLog, act: str, direction: str, today: date | None,
                 with_task: bool = False) -> AsyncIterator[Any]:
    had_ideas = bool(n.ideas)
    before = len(log.received)
    _fill_from_data(n, log)  # 제품 칸이 비어 있어도 아이디어를 낸다(지시서 11의 3절)
    filled = log.received[before:]
    keep = [i for i in n.ideas if i.get("kept") or i.get("by") == "planner"]
    total = min(5, max(3, len(keep) + 3))
    if len(idea_spec.same_spec_group(keep)) >= 2:  # 기획자의 아이디어를 규격별로 나눴으면 칠성이의 제안은 하나만(한 화면에 셋)
        total = min(5, len(keep) + 1)
    n_new = total - len(keep)
    if n_new <= 0:
        log.received.append(Bit(fact="아이디어 보드가 가득 차서(다섯 개) 새로 내지 않았다. 빼거나 남기기를 풀어 달라고 한다",
                                sentence="아이디어가 다섯 개로 꽉 찼어요. 하나를 빼 주시면 새로 낼게요."))
        return
    yield Activity(id=act, label=P.ACT_IDEAS, status="running")
    yield ideas_card(n, "loading")
    needs = [x.desc for x in consumer.needs(n.occasion_code)[:2] if x.desc] if n.occasion_code else []
    facts, claims = _context_found(n)
    avoid = [i["name"] for i in n.ideas if i not in keep]
    keep_lines = [f"{i['name']} (맛 {i['flavor']}, {i['pack']})" for i in keep]
    task = _task_to_add(n, log, direction) if with_task and n_new >= 2 else None
    # 과제의 컨셉은 규격마다 카드 하나로 올린다. 규격이 둘 이상이면 칠성이의 제안은 하나만 낸다(11-25)
    n_task = len(task.get("variants") or [None]) if task else 0
    n_model = max(1, n_new - n_task) if task else n_new
    if task:  # 과제의 컨셉은 칠성이가 다시 내지 않는다(겹치지 않게 그대로 둘 것에 적는다)
        keep_lines.append(f"{task['name']} (맛 {task.get('flavor') or '기본'}, 과제의 컨셉)")
    jobs = [steps.ideas(summary(n), n_model, direction, keep_lines, avoid, needs, facts, claims,
                        idea_spec.shelf_size_lines(n.shelf), today)]
    if task:  # 한 줄 설명과 특징은 기획자의 아이디어와 같은 길로, 아이디어 내기와 함께 돌린다
        jobs.append(steps.my_idea(summary(n), task["name"]))
    got = await asyncio.gather(*jobs, return_exceptions=True)
    ans = got[0]
    if isinstance(ans, BaseException):
        if not isinstance(ans, StepFailed):
            raise ans
        yield ideas_card(n, "error") if not n.ideas else ideas_card(n)
        _failed(n, log, "ideas", [ReadTask(do="ideas", text=direction)])
        return
    if not n.need.value or n.need.by == "chilseong":  # 칠성이가 정한 니즈는 새 방향에 맞춰 다시 정한다
        n.need = Slot(ans.need.strip(), "chilseong")
    first = []
    if task and not isinstance(got[1], BaseException):  # 실패하면 그 아이디어 없이 지금처럼 간다
        mine = got[1]
        mine.name = task["name"]
        first.extend(idea_spec.split(_idea_dict(n.new_idea_id(), mine, "planner", task["name"]), n.new_idea_id))
    new = []
    for it in ans.items[:n_model]:
        new.append(_idea_dict(n.new_idea_id(), it, "chilseong", shelf=n.shelf, today=today))
    n.ideas = first + keep + new
    if len(first) > 1:
        name, packs = first[0]["name"], ", ".join(idea_spec.label(i["variants"][0]) for i in first)
        log.received.append(Bit(fact=P.TASK_IDEA_SPLIT_FACT.format(name=name, packs=packs),
                                sentence=P.TASK_IDEA_SPLIT.format(name=name, jo=josa(name, "을/를")), names=[name]))
    elif first:
        name = first[0]["name"]
        log.received.append(Bit(fact=P.TASK_IDEA_FACT.format(name=name),
                                sentence=P.TASK_IDEA.format(name=name, jo=josa(name, "을/를")), names=[name]))
    log.ideas_changed = True
    if n.stage == "concept":
        n.stage = "idea"
        yield Stage(current="idea")
    count = spoken.count(len(new) + len(first))  # 함께 올린 과제의 컨셉(규격마다 하나)도 이번에 낸 아이디어로 센다
    for b in filled:  # 정한 것은 아이디어를 낸 말 안에 녹인다(결론 먼저)
        log.received.remove(b)
    log.ideas_again = had_ideas
    what = P.drink_phrase(n.target.value, n.occasion.value, n.thoughts, n.product.value or None)
    fact = (f"아이디어 {count} 개를 {'새로 ' if had_ideas else ''}냈다. 첫 문장은 이것(\"아이디어 {count} 개를 "
            f"{'새로 ' if had_ideas else ''}냈어요\"). 어떤 아이디어인지는 이 말로 한 문장: \"{what}\"")
    if filled:
        fact += " (누가 언제 마실지는 칠성이가 정했다. 기획자가 바꿀 수 있다)"
    if keep:
        fact += f". 남긴 것 {spoken.count(len(keep))} 개는 그대로 뒀다"
    sentence = f"아이디어 {count} 개를 {'새로 ' if had_ideas else ''}냈어요. {what}{josa(what, '이에요/예요')}."
    log.received.append(Bit(fact=fact, sentence=sentence, names=[what, *(nm for b in filled for nm in b.names)]))


def _idea_dict(idea_id: str, it: Any, by: str, said: str | None = None, old: dict[str, Any] | None = None, *,
               shelf: str = "음료", today: date | None = None) -> dict[str, Any]:
    """said(기획자의 말)가 있으면 제품 사양도 적는다(지시서 33): 과제의 컨셉이면 CONCEPTS, 그 위에 말한 칸.
    칠성이가 스스로 낸 아이디어(said 없음)는 제안한 사양을 코드가 매대의 규격과 범위로 다듬어 적는다(11-25)."""
    d = {"id": idea_id, "name": it.name, "flavor": it.flavor, "pack": f"{it.container} {it.volume_ml}ml",
         "features": list(it.features), "line": idea_spec.clean_meta(it.line),
         "diff": idea_spec.clean_meta(it.diff), "by": by,
         "_container": it.container, "_volume": it.volume_ml}
    if said is not None:
        had = bool(old and old.get("variants"))
        spec = idea_spec.planner_spec(it.name, it, said, idea_spec.spec_of(old) if had else None)
        idea_spec.apply(d, spec, move_shelf=not had)
        if had and d.get("variants"):
            # 용기·용량을 고쳤고 그것이 규격 가운데 하나면 그 규격을 매대에 올린다. 아니면 지금 것을 그대로 둔다
            hit = [k for k, v in enumerate(d["variants"])
                   if v.get("container") == d["_container"] and v.get("volume_ml") == d["_volume"]]
            d["_shelf_variant"] = hit[0] if hit else (old.get("_shelf_variant") or 0)
    elif by == "chilseong":
        idea_spec.apply(d, idea_spec.proposed_spec(it, shelf, today), move_shelf=True)
    return d


async def h_ideas(n: Note, log: TurnLog, act: str, t: ReadTask, today: date | None) -> AsyncIterator[Any]:
    async for ev in _ideas(n, log, act, t.text.strip(), today, with_task=True):
        yield ev


async def h_more(n: Note, log: TurnLog, act: str, t: ReadTask, today: date | None) -> AsyncIterator[Any]:
    if n.stage == "concept" and n.concepts:
        ids = [c["id"] for c in n.concepts if n.idea(c["id"])]
        async for ev in _make_concepts(n, log, act, ids, "지금 컨셉과 다른 방향으로"):
            yield ev
        return
    async for ev in _ideas(n, log, act, t.text.strip() or "지금 보드에 없는 다른 방향", today):
        yield ev


def _target_idea(n: Note, t: ReadTask) -> dict[str, Any] | None:
    for i in t.ids:
        idea = n.idea(i)
        if idea:
            return idea
    return n.ideas[0] if len(n.ideas) == 1 else None


async def h_edit_idea(n: Note, log: TurnLog, act: str, t: ReadTask, today: date | None) -> AsyncIterator[Any]:
    idea = _target_idea(n, t)
    if idea is None:
        log.addition = Addition(fact="어느 아이디어를 고칠지 묻는다", sentence="어느 아이디어를 고칠까요?", ask=True)
        return
    yield Activity(id=act, label=P.ACT_EDIT_IDEA, status="running")
    try:
        ans = await steps.edit_idea(summary(n), idea, t.text or log.text)
    except StepFailed:
        _failed(n, log, "edit_idea", [t])
        return
    new = _idea_dict(idea["id"], ans, idea.get("by") or "chilseong", t.text or log.text, idea)
    changed = [k for k in IDEA_FIELDS if new[k] != idea[k]]
    old_name = idea["name"]
    for k in (*IDEA_FIELDS, "diff", "_container", "_volume", *idea_spec.SPEC_KEYS):
        if k in new:
            idea[k] = new[k]
    if changed:
        idea["changed"] = changed
    if len(idea.get("variants") or []) > 1:  # 고치다 규격이 늘면 늘어난 규격은 새 카드로(11-25)
        keep_k = idea.get("_shelf_variant") or 0
        vs = idea["variants"]
        idea["variants"] = [vs[keep_k]] + [v for k, v in enumerate(vs) if k != keep_k]
        parts = idea_spec.split(idea, n.new_idea_id)
        at = n.ideas.index(idea)
        n.ideas[at:at + 1] = parts
        idea = parts[0]
    log.ideas_changed = True
    names = {"name": "이름", "flavor": "맛", "pack": "용기와 용량", "features": "특징", "line": "한 줄 설명"}
    what = ", ".join(names[c] for c in changed) or "말씀하신 곳"
    log.received.append(Bit(fact=f"'{old_name}' 아이디어를 말씀대로 고쳤다(바뀐 칸: {what}). 새 이름은 '{idea['name']}'",
                            sentence=f"'{old_name}'{josa(old_name, '은/는')} '{idea['name']}'{josa(idea['name'], '으로/로')} 고쳤어요.",
                            names=[old_name, idea["name"]]))


async def h_my_idea(n: Note, log: TurnLog, act: str, t: ReadTask, today: date | None) -> AsyncIterator[Any]:
    text = (t.text or t.value or log.text).strip()
    yield Activity(id=act, label=P.ACT_EDIT_IDEA, status="running")
    try:
        ans = await steps.my_idea(summary(n), text)
    except StepFailed:
        _failed(n, log, "my_idea", [t])
        return
    parts = idea_spec.split(_idea_dict(n.new_idea_id(), ans, "planner", text), n.new_idea_id)
    n.ideas.extend(parts)
    log.ideas_changed = True
    name = parts[0]["name"]
    if len(parts) > 1:  # 규격이 둘 이상이면 규격마다 카드 하나(11-25)
        packs = ", ".join(idea_spec.label(i["variants"][0]) for i in parts)
        log.received.append(Bit(fact=P.MY_IDEA_SPLIT_FACT.format(name=name, packs=packs),
                                sentence=P.MY_IDEA_SPLIT.format(name=name, jo=josa(name, "을/를")), names=[name]))
        return
    log.received.append(Bit(fact=f"기획자의 아이디어 '{name}'{josa(name, '을/를')} 보드에 올렸다",
                            sentence=f"'{name}'{josa(name, '을/를')} 보드에 올렸어요.", names=[name]))


async def h_keep(n: Note, log: TurnLog, act: str, t: ReadTask, today: date | None) -> AsyncIterator[Any]:
    picked = [n.idea(i) for i in t.ids if n.idea(i)]
    for idea in picked:
        idea["kept"] = True
    if picked:
        log.ideas_changed = True
        names = ", ".join(f"'{i['name']}'" for i in picked)
        log.received.append(Bit(fact=f"{names}{josa(names, '은/는')} 남기기로 했다(다시 낼 때 그대로 둔다)",
                                sentence=f"{names}{josa(names, '은/는')} 남겨 둘게요.", names=[i["name"] for i in picked]))
    return
    yield  # noqa: unreachable — 비동기 생성기로 만든다


async def h_drop(n: Note, log: TurnLog, act: str, t: ReadTask, today: date | None) -> AsyncIterator[Any]:
    picked = [n.idea(i) for i in t.ids if n.idea(i)]
    if picked:
        n.ideas = [i for i in n.ideas if i not in picked]
        log.ideas_changed = True
        names = ", ".join(f"'{i['name']}'" for i in picked)
        log.received.append(Bit(fact=f"{names}{josa(names, '을/를')} 보드에서 뺐다",
                                sentence=f"{names}{josa(names, '은/는')} 뺐어요.", names=[i["name"] for i in picked]))
    return
    yield  # noqa


# ----- 컨셉 -----


def _said_concepts(n: Note, log: TurnLog) -> bool:
    """문턱: 기획자가 컨셉 보드를 만들자고 말했는가(글, 칩, 또는 카드 안에서 고르는 차례의 답)."""
    if "make-concepts" in log.ids:
        return True
    picking = isinstance(n.last_offer, Choices) and n.last_offer.on_card == "ideas"
    if picking and log.ids and all(n.idea(i) for i in log.ids):
        return True
    if picking and ideas_named(n, log.text):  # 고르라는 물음에 아이디어의 이름으로 답했다("밀키스 화채로 만들어 줘")
        return True
    return any(c in log.text for c in CONCEPT_CUES)


def _said_confirm(log: TurnLog) -> bool:
    return "confirm-concepts" in log.ids or any(c in log.text for c in CONFIRM_CUES)


def ideas_named(n: Note, text: str) -> list[str]:
    """기획자의 말에 보드의 아이디어 이름이 그대로 들어 있으면 그 id들(읽기가 ids를 비워 보냈을 때의 안전망).
    공백을 무시하고, 가장 긴 이름부터 맞추며, 맞은 자리는 다시 쓰지 않는다."""
    rest = re.sub(r"\s+", "", text or "")
    out = []
    for idea in sorted(n.ideas, key=lambda i: len(re.sub(r"\s+", "", i.get("name") or "")), reverse=True):
        name = re.sub(r"\s+", "", idea.get("name") or "")
        if name and (name in rest or any(re.sub(r"\s+", "", n.idea(i).get("name") or "") == name for i in out)):
            out.append(idea["id"])  # 이름이 같은 카드(규격별로 나눈 아이디어)는 함께 고른다
            rest = rest.replace(name, "\u0000")
    return [i["id"] for i in n.ideas if i["id"] in out]


async def h_concepts(n: Note, log: TurnLog, act: str, t: ReadTask, today: date | None) -> AsyncIterator[Any]:
    if not _said_concepts(n, log):
        log.suggest_concepts = True
        log.addition = Addition(fact="컨셉 보드로 만들지 묻는다(기획자가 정한다)", sentence="이대로 컨셉 보드를 만들어 볼까요?",
                                ask=True)
        return
    if not n.ideas:
        log.fixed.append("컨셉 보드를 만들려면 아이디어가 먼저 있어야 해요.")
        return
    ids = [i for i in t.ids if n.idea(i)] or [i for i in log.ids if n.idea(i)] or ideas_named(n, log.text)
    if not ids and len(n.ideas) == 1:
        ids = [n.ideas[0]["id"]]  # 보드에 아이디어가 하나뿐이면 묻지 않고 그것으로 만든다
    if not ids:
        # 고를 아이디어를 말하지 않았다: 카드 안에서 고르는 차례를 내민다
        log.stop = True
        yield Activity(id=act, label=P.ACT_LOOK, status="done")
        yield brief_card(n)
        yield Say(text=P.PICK_IDEAS)
        offer = pick_choices(n)
        n.last_offer = offer
        n.remember_say(P.PICK_IDEAS)
        yield offer
        return
    async for ev in _make_concepts(n, log, act, ids, ""):
        yield ev


async def _make_concepts(n: Note, log: TurnLog, act: str, ids: list[str], direction: str) -> AsyncIterator[Any]:
    yield Stage(current="concept")
    n.stage = "concept"
    yield Activity(id=act, label=P.ACT_CONCEPTS, status="running")
    yield concepts_card(n, "loading")
    chosen: list[tuple[dict, Any, steps.ConceptInput]] = []
    for i in ids:
        idea = n.idea(i)
        sim = shelf.similar(n.shelf_kind, idea["_container"], idea["_volume"])
        zero = _is_zero(n, [idea["name"], idea["flavor"], *idea["features"]])
        on = idea_spec.shelf_variant(idea)
        has_price = sim is not None or bool(on and on.get("price"))
        chosen.append((idea, sim, concept_input(n, i, idea, idea["_container"], idea["_volume"], zero, has_price)))
    context = summary(n) + (f"\n\n이번에 받은 방향: {direction}" if direction else "")
    try:
        ans = await steps.concepts(context, [ci for _, _, ci in chosen], n.need.value or "")
    except StepFailed:
        yield concepts_card(n, "error") if not n.concepts else concepts_card(n)
        _failed(n, log, "concepts", [ReadTask(do="concepts", ids=ids)])
        return
    by_id = {a.idea_id: a for a in ans.items}
    # 있던 보드는 지우지 않는다. 같은 아이디어의 보드만 새로 쓰고, 새 보드는 더한다(11-25 참가자의 검수)
    if n.confirmed and not any(c.get("_confirmed") for c in n.concepts):
        for c in n.concepts:  # 옛 대화에서 확정한 보드는 보드를 더해도 확정한 것으로 남긴다
            c["_confirmed"] = True
    kept = [c for c in n.concepts if c["id"] not in by_id]
    made: list[dict[str, Any]] = []
    sims: dict[tuple, Any] = {}
    guessed: list[str] = []
    given: list[str] = []
    for idea, sim, ci in chosen:
        a = by_id[ci.id]
        on = idea_spec.shelf_variant(idea)
        if on and on.get("price"):  # 매대에 올릴 규격의 권장 소비자가(지시서 33)
            price = on["price"]
            given.append(idea["name"])
            if sim and idea.get("by") != "planner":  # 칠성이가 제안한 가격도 편의점의 비슷한 제품 가격대를 근거로 보인다(11-25)
                sims[(sim.kind, sim.container, sim.volume)] = sim
        elif sim:
            price = sim.middle
            sims[(sim.kind, sim.container, sim.volume)] = sim
        else:
            price = int(round((a.price_guess or 0) / 100) * 100)
            guessed.append(idea["name"])
        made.append({
            "id": ci.id, "name": a.name.strip(), "headline": a.headline.strip(), "benefit": a.benefit.strip(),
            "points": [x.strip() for x in a.points], "price": f"{price:,}원",
            "pack": P.pack(idea["_container"], idea["_volume"]),
            "_flavor": idea["flavor"], "_container": idea["_container"], "_volume": idea["_volume"],
            "_price_by": (("planner" if idea.get("by") == "planner" else "idea") if idea["name"] in given
                          else "shelf" if sim else "guess"), "_sugar": a.sugar_caffeine.strip(), "_carb": a.carbonation,
            "_occasion": a.occasion.strip(), "_pod": a.pod.strip() if ci.rivals else "",
        })
        if (a.insight or "").strip():  # 소비자 인식 한 문장(없어도 된다)
            made[-1]["insight"] = a.insight.strip()
        if idea.get("_task_concept"):  # 과제의 컨셉: 제품명은 아이디어의 이름 그대로(헤드라인·혜택은 모델의 것)
            made[-1]["name"] = idea["name"]
            made[-1]["_task_concept"] = idea["_task_concept"]
        if idea.get("variants"):  # 아이디어의 규격(이제 하나)과 그 값을 물려받는다. 옛 아이디어는 규격이 여럿일 수 있다
            idea_spec.apply(made[-1], idea_spec.spec_of(idea), move_shelf=False)
            made[-1]["_shelf_variant"] = idea.get("_shelf_variant") or 0
        put_shelf(made[-1], ci)
    order = {i["id"]: k for k, i in enumerate(n.ideas)}
    n.concepts = sorted(kept + made, key=lambda c: order.get(c["id"], len(order)))
    log.concepts_changed = True
    shelf_found = [_shelf_found(sim) for sim in sims.values()]
    if add_evidence(n, shelf_found):
        yield evidence_card(n)
    k = len(made)
    head = f"{spoken.count(k)} 개 다 컨셉 보드로 만들었어요." if k > 1 else "고르신 아이디어로 컨셉 보드를 만들었어요."
    fact = f"고른 아이디어 {spoken.count(k)} 개를 모두 컨셉 보드로 만들었다" if k > 1 else "고른 아이디어로 컨셉 보드를 만들었다"
    if kept:  # 있던 보드 옆에 더했다
        total = len(n.concepts)
        head = f"컨셉 보드를 더했어요. 이제 보드가 {spoken.count(total)} 장이에요."
        fact = f"있던 컨셉 보드는 그대로 두고 {spoken.count(k)} 장을 더했다. 이제 보드가 {spoken.count(total)} 장이다"
    log.received.append(Bit(fact=fact, sentence=head))
    if given and len(given) == k and all(c.get("_price_by") == "planner" for c in made):
        log.received.append(Bit(fact="가격은 기획자가 준 사양의 권장 소비자가로 했다(매대에 올릴 규격의 값)",
                                sentence="가격은 주신 사양의 권장 소비자가로 했어요."))
    elif given and len(given) == k:
        log.received.append(Bit(fact=P.IDEA_PRICE_FACT, sentence=P.IDEA_PRICE))
    elif guessed and len(guessed) == k:
        log.received.append(Bit(fact="편의점에 비슷한 제품이 없어서 가격은 칠성이가 어림했다",
                                sentence="편의점에 비슷한 제품이 없어서 가격은 제가 어림했어요."))
    else:
        tail = (f", {', '.join(guessed)}{josa(guessed[-1], '은/는')} 비슷한 제품이 없어서 칠성이가 어림했다" if guessed else "")
        log.received.append(Bit(fact="가격은 편의점에서 비슷한 제품이 팔리는 값에 맞췄다" + tail,
                                sentence="가격은 편의점에서 비슷한 제품이 팔리는 값에 맞췄어요.", names=guessed))


VARIANT_TO = "variant"  # 컨셉 보드의 규격 줄을 눌렀을 때의 metadata.reply.to(ids: [컨셉 id, 규격의 차례])


def _variant_target(n: Note, text: str, ids: list[str], to: str | None) -> tuple[dict[str, Any], int] | None:
    if to == VARIANT_TO and len(ids) == 2 and ids[1].isdigit():
        c = n.concept(ids[0])
        if c and 0 <= int(ids[1]) < len(c.get("variants") or []):
            return c, int(ids[1])
        return None
    if "규격" not in text or not n.concepts:
        return None
    key = re.sub(r"\s+", "", text).lower()
    hits = []
    for c in n.concepts:
        for k, v in enumerate(c.get("variants") or []):
            name = re.sub(r"\s+", "", idea_spec.label(v)).lower()
            if name and name in key:
                hits.append((c, k))
    if len({id(c) for c, _ in hits}) > 1:  # 여러 컨셉에 같은 규격이 있으면 컨셉 이름으로 가린다
        hits = [(c, k) for c, k in hits if re.sub(r"\s+", "", c.get("name", "")) in re.sub(r"\s+", "", text)] or []
    return hits[0] if len(hits) == 1 else None


def switch_variant(n: Note, text: str, ids: list[str], to: str | None) -> list[Any] | None:
    """매대에 올릴 규격을 바꾼다(모델을 부르지 않는다). 용기·용량과 가격(그 규격의 권장 소비자가)을 맞추고,
    경쟁 제품과 자사 유사 제품은 매대에서 다시 고른다. 바꿀 것이 아니면 None."""
    hit = _variant_target(n, text, ids, to)
    if hit is None:
        return None

    def jo(word: str, pair: str) -> str:  # "250ml"은 "밀리리터"로 읽는다
        return pair.split("/")[1] if word.lower().endswith("ml") else josa(word, pair)

    c, k = hit
    v = c["variants"][k]
    name = idea_spec.label(v)
    # 직전에 열려 있던 행동 묶음(예: 이 컨셉으로 확정하기)을 같은 동작으로 다시 낸다. 버튼은 마지막 메시지의 것만 보인다
    offer = _again(n, n.last_offer) if n.last_offer is not None else None
    if n.confirmed:
        return _end(n, "확정한 컨셉이라 매대에 올릴 규격은 바꿀 수 없어요.", offer)
    if (c.get("_shelf_variant") or 0) == k:
        return _end(n, f"{name}{jo(name, '은/는')} 이미 매대에 올릴 규격이에요.", offer)
    c["_shelf_variant"] = k
    c["_container"], c["_volume"] = v.get("container") or c.get("_container"), v.get("volume_ml") or c.get("_volume")
    c["pack"] = P.pack(c["_container"], c["_volume"])
    if v.get("price"):
        c["price"], c["_price_by"] = f"{v['price']:,}원", "planner"
    else:
        sim = shelf.similar(n.shelf_kind, c["_container"], c["_volume"])
        if sim:
            c["price"], c["_price_by"] = f"{sim.middle:,}원", "shelf"
    reselect_shelf(n, c)
    c["changed"] = ["variants"]
    price = c.get("price") or ""
    say = (f"{name}{jo(name, '을/를')} 매대에 올릴게요. 가격은 {price}{josa(price, '으로/로')} 테스트해요." if price
           else f"{name}{jo(name, '을/를')} 매대에 올릴게요.")
    return [concepts_card(n)] + _end(n, say, offer)


def _shelf_found(sim: Any) -> Found:
    pack = f"{sim.container} {sim.volume}ml" if sim.container else f"{sim.volume}ml"
    return Found(key=f"price:{sim.kind}:{pack}", tool="price", origin="shelf",
                 text=P.ev_shelf(sim.count, sim.low, sim.high),
                 source=shelf.SHELF_SOURCE, said_source="편의점 매대", fact="", sentence="")


PRICE_RE = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+)\s*원")


def planner_price(text: str) -> int | None:
    m = PRICE_RE.search(text)
    if not m:
        return None
    value = int(m.group(1).replace(",", ""))
    return value if 100 <= value <= 100000 else None


REL_PRICE_RE = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+)\s*원\s*(?:정도|쯤|씩|만)?\s*(?:더\s*)?(싸|저렴|낮|내려|내리|깎|비싸|높|올려|올리)")
REL_HINT_RE = re.compile(r"보다|더\s*(?:싸|비싸|저렴)|내려|내리|올려|올리|깎")
RIVAL_HINT_RE = re.compile(r"경쟁|타사|다른\s*(?:회사|제품)|비슷한\s*제품")


def relative_price(text: str, concept: dict[str, Any]) -> tuple[int, str] | None:
    """"경쟁사보다 200원 싸게", "300원 내려 줘"처럼 견줘 말한 가격. (값, 무엇에 견줬는지의 말) 또는 None.
    경쟁 제품에 견주면 싸게는 가장 싼 경쟁 제품에서, 비싸게는 가장 비싼 경쟁 제품에서 센다. 아니면 지금 가격에서."""
    m = REL_PRICE_RE.search(text)
    if not m:
        return None
    delta = int(m.group(1).replace(",", ""))
    down = m.group(2) in ("싸", "저렴", "낮", "내려", "내리", "깎")
    if RIVAL_HINT_RE.search(text):
        prices = [planner_price(r) for r in concept.get("_rivals") or []]
        prices = [x for x in prices if x]
        if not prices:
            return None
        base, what = (min(prices) if down else max(prices)), "경쟁 제품"
    else:
        base, what = _price_won(concept.get("price")), "지금 가격"
    value = base - delta if down else base + delta
    if not 100 <= value <= 100000:
        return None
    return value, f"{what}({base:,}원)보다 {delta:,}원 {'싼' if down else '비싼'}"


async def h_edit_concept(n: Note, log: TurnLog, act: str, t: ReadTask, today: date | None) -> AsyncIterator[Any]:
    concept = next((n.concept(i) for i in t.ids if n.concept(i)), None)
    if concept is None and len(n.concepts) == 1:
        concept = n.concepts[0]
    if concept is None:
        if not n.concepts:
            log.fixed.append("아직 컨셉 보드가 없어요.")
        else:
            log.addition = Addition(fact="어느 컨셉을 고칠지 묻는다", sentence="어느 컨셉을 고칠까요?", ask=True)
        return
    yield Activity(id=act, label=P.ACT_EDIT_CONCEPT, status="running")
    instruction = t.text or log.text
    zero = concept_zero(n, concept)
    ci = concept_input(n, concept["id"], concept, concept["_container"], concept["_volume"], zero, True)
    try:
        ans = await steps.edit_concept(summary(n), concept, instruction, ci)
    except StepFailed:
        _failed(n, log, "edit_concept", [t])
        return
    before = concept_values(n, concept)
    old_name = concept["name"]
    concept.update({"name": ans.name.strip(), "headline": ans.headline.strip(), "benefit": ans.benefit.strip(),
                    "points": [x.strip() for x in ans.points], "_flavor": ans.flavor.strip(),
                    "_sugar": ans.sugar_caffeine.strip(), "_carb": ans.carbonation, "_occasion": ans.occasion.strip()})
    if ans.insight.strip():
        concept["insight"] = ans.insight.strip()
    pack_changed = (ans.container, ans.volume_ml) != (concept["_container"], concept["_volume"])
    concept["_container"], concept["_volume"] = ans.container, ans.volume_ml
    concept["pack"] = P.pack(ans.container, ans.volume_ml)
    price_bits: list[Bit] = []
    # 견줘 말한 가격("경쟁사보다 200원 싸게")을 먼저 본다. 견준 말인데 셈할 수 없으면 그 숫자를 가격으로 쓰지 않는다
    rel = relative_price(instruction, concept) or relative_price(log.text, concept)
    is_relative = bool(REL_HINT_RE.search(instruction) or REL_HINT_RE.search(log.text))
    said_price = None if (rel or is_relative) else (planner_price(log.text) or planner_price(instruction))
    if rel:
        concept["price"], concept["_price_by"] = f"{rel[0]:,}원", "planner"
        price_bits.append(Bit(fact=f"가격은 {rel[1]} {concept['price']}{josa(concept['price'], '으로/로')} 했다",
                              sentence=f"가격은 {rel[1]} {concept['price']}{josa(concept['price'], '으로/로')} 했어요.",
                              names=[concept["price"]]))
    elif said_price:
        concept["price"], concept["_price_by"] = f"{said_price:,}원", "planner"
        price_bits.append(Bit(fact=f"가격은 기획자가 말한 {concept['price']}{josa(concept['price'], '으로/로')} 했다",
                              sentence=f"가격은 말씀하신 {concept['price']}{josa(concept['price'], '으로/로')} 했어요.",
                              names=[concept["price"]]))
    elif pack_changed and concept.get("_price_by") != "planner":
        sim = shelf.similar(n.shelf_kind, ans.container, ans.volume_ml)
        if sim:
            concept["price"], concept["_price_by"] = f"{sim.middle:,}원", "shelf"
            if add_evidence(n, [_shelf_found(sim)]):
                yield evidence_card(n)
        else:
            guess = int(round((ans.price_guess or 0) / 100) * 100)
            if guess >= 100:
                concept["price"], concept["_price_by"] = f"{guess:,}원", "guess"
        guessed = concept.get("_price_by") == "guess"
        price_bits.append(Bit(fact=f"용량이 바뀌어 가격을 {concept['price']}{josa(concept['price'], '으로/로')} 다시 잡았다"
                              + ("(편의점에 비슷한 용량의 제품이 없어서 칠성이가 어림했다)" if guessed else ""),
                              sentence=(f"편의점에 비슷한 용량이 없어서 가격은 {concept['price']}{josa(concept['price'], '으로/로')} 어림했어요."
                                        if guessed else
                                        f"용량이 바뀌어서 가격도 {concept['price']}{josa(concept['price'], '으로/로')} 다시 잡았어요."),
                              names=[concept["price"]]))
    # 아이디어에서 물려받은 매대 규격(칠성이가 제안한 한 규격)은 고친 용기·용량·가격을 따른다(11-25). 용량이 바뀌면 열량은 비운다
    on = idea_spec.shelf_variant(concept)
    if on is not None and len(concept.get("variants") or []) == 1 and not on.get("pack") and on.get("factory_price") is None:
        if pack_changed:
            on.update(container=ans.container, volume_ml=ans.volume_ml, kcal=None)
        on["price"] = _price_won(concept.get("price")) or on.get("price")
    # 용기나 용량이 바뀌면 경쟁 제품과 자사 유사 제품을 매대에서 다시 고르고, 경쟁 제품이 바뀌었으면 차별점도 다시 쓴다
    old_rivals = list(concept.get("_rivals") or [])
    if pack_changed:
        ci = concept_input(n, concept["id"], concept, ans.container, ans.volume_ml, zero, True)
    put_shelf(concept, ci)
    if not ci.rivals:
        concept["_pod"] = ""
    elif ci.rivals != old_rivals:
        try:
            concept["_pod"] = await steps.pod(summary(n), concept, ci)
        except StepFailed:
            concept["_pod"] = ans.pod.strip()
        price_bits.append(Bit(fact="용량이 바뀌어 경쟁 제품을 편의점 매대에서 다시 고르고 차별점도 다시 썼다",
                              sentence="경쟁 제품도 용량에 맞춰 다시 골랐어요."))
    else:
        concept["_pod"] = ans.pod.strip()
    after = concept_values(n, concept)
    changed = [k for k in after.keys() | before.keys() if after.get(k) != before.get(k)]
    order = ["headline", "name", "benefit", "insight", "points", *P.SPEC_LABELS]
    changed.sort(key=lambda k: order.index(k) if k in order else len(order))
    if changed:
        concept["changed"] = changed
    log.concepts_changed = True
    log.received.append(Bit(fact=f"'{old_name}' 컨셉을 말씀대로 고쳤다(바뀐 칸: {', '.join(changed) or '없음'})",
                            sentence=f"'{concept['name']}' 컨셉을 고쳤어요.", names=[old_name, concept["name"],
                                                                                    concept["pack"]]))
    log.received += price_bits


async def h_confirm(n: Note, log: TurnLog, act: str, t: ReadTask, today: date | None) -> AsyncIterator[Any]:
    if not _said_confirm(log):
        log.addition = Addition(fact="이대로 확정할지 묻는다(기획자가 정한다)", sentence="이대로 확정할까요?", ask=True)
        return
    if not n.concepts:
        log.received.append(Bit(fact="아직 컨셉 보드가 없어 확정할 것이 없다", sentence="아직 확정할 컨셉 보드가 없어요."))
        log.addition = Addition(fact="고른 아이디어로 컨셉 보드부터 만들자고 권한다",
                                sentence="마음에 드는 아이디어로 컨셉 보드부터 만들어 볼까요?")
        return
    picked = [n.concept(i) for i in (*t.ids, *log.ids) if n.concept(i)]
    picked = list({id(c): c for c in picked}.values())
    if len(n.concepts) > 1 and not picked:
        # 보드가 둘 이상이면 어느 보드를 확정할지 보드에서 고르게 한다(11-25)
        log.stop = True
        yield Activity(id=act, label=P.ACT_LOOK, status="done")
        names = board_names(n)
        offer = Choices(id=n.next_id(PICK_CONFIRM), kind="multi", on_card="concepts",
                        options=[Option(id=c["id"], label=names[c["id"]]) for c in n.concepts])
        for ev in _end(n, P.PICK_CONFIRM, offer):
            yield ev
        return
    chosen = picked or list(n.concepts)
    for c in n.concepts:
        if any(c is x for x in chosen):
            c["_confirmed"] = True
        else:
            c.pop("_confirmed", None)
    n.confirmed = True
    log.confirmed = True
    yield concepts_card(n)  # 규격 고르기를 잠근 컨셉 보드(지시서 33 후속)
    k = len(chosen)
    def named(c: dict[str, Any]) -> str:  # 보드가 둘 이상이면 규격까지(이름이 같은 규격별 보드를 가린다)
        on = idea_spec.shelf_variant(c)
        return f"{c['name']} {idea_spec.label(on)}" if on and len(n.concepts) > 1 else c["name"]

    value = ", ".join(named(c) for c in chosen)
    yield Summary(id=n.next_id("summary"), title=P.SUMMARY_TITLE, value=value,
                  note=P.summary_note(n.target.value, n.occasion.value) or None)
    from agent import diagnose

    boards = [diagnose.board(n, concept) for concept in chosen]
    # 분석이 한꺼번에 튀어나오지 않게, 무엇을 보고 있는지 차례로 알린다(참가자 11-25). 시험(fake)에서는 기다리지 않는다
    import asyncio as _asyncio
    import os as _os

    pace = 0 if _os.environ.get("AX_LLM") == "fake" else 1.6
    for label in P.ACT_ANALYSIS:
        yield Activity(id=act, label=label, status="running")
        if pace:
            await _asyncio.sleep(pace)
    for card in boards:
        yield card
    if k == 1 and n.shelf_kind:
        # 보드 하나(11-25 참가자 승인): 분석을 인사이트로 정리하고 매대 테스트를 제안한다. 버튼은 분석 카드의 버튼이 하던 일
        say, buttons = diagnose.confirm_turn(boards[0].payload)
        log.fixed.append(say)
        log.offer = _actions(n, "diagnose-pick", buttons)
        log.addition = None
        return
    log.received.append(Bit(fact=f"컨셉 {spoken.count(k)} 개로 정했다" if k > 1 else "이 컨셉으로 정했다",
                            sentence=f"{spoken.count(k)} 컨셉으로 정했어요." if k > 1 else "이 컨셉으로 정했어요."))
    flagged = max((sum(s["status"] == "flag" for s in card.payload["sections"]) for card in boards), default=0)
    if n.shelf_kind and flagged:
        priced = any(fix["values"].get("price") for card in boards for fix in card.payload["fixes"])
        pick = P.diagnosis_pick(priced, any(card.payload["fixes"] for card in boards))
        log.received.append(Bit(fact=f"컨셉 보드 분석에서 살펴볼 점이 {flagged}가지 나왔다. 컨셉 보드 분석을 보고 테스트할 안을 고르게 한다",
                                sentence=P.diagnosis_flags(spoken.count(flagged)) + " " + pick))
    elif n.shelf_kind:
        log.received.append(Bit(fact="다음에는 편의점 매대에 올려서 손님들이 구매하는지 볼 수 있다",
                                sentence="편의점 매대에 올려서 손님들이 구매하는지 볼 수 있어요."))
    else:
        log.received.append(Bit(fact="편의점 매대에 비슷한 제품이 없어서, 테스트하려면 견줄 제품을 넣어야 한다",
                                sentence="편의점 매대에 비슷한 제품이 없어서, 테스트하려면 견줄 제품을 넣어야 해요."))
    log.addition = None
    return
    yield  # noqa


async def h_download(n: Note, log: TurnLog, act: str, t: ReadTask, today: date | None) -> AsyncIterator[Any]:
    """내려받기(지시서 14의 3절): 확정하지 않았어도 컨셉 보드가 있으면 제안서 버튼을 낸다."""
    if not n.concepts:
        log.fixed.append(P.DOWNLOAD_NO_CONCEPTS)
        return
    log.fixed.append(P.DOWNLOAD_READY)
    log.offer = _actions(n, "download", [("download", P.BTN_DOWNLOAD)])
    return
    yield  # noqa


async def h_answer(n: Note, log: TurnLog, act: str, t: ReadTask, today: date | None) -> AsyncIterator[Any]:
    log.answer_to = (t.text or log.text).strip()
    return
    yield  # noqa


async def h_not_ready(n: Note, log: TurnLog, act: str, t: ReadTask, today: date | None) -> AsyncIterator[Any]:
    log.fixed.append(P.NOT_READY)
    return
    yield  # noqa


async def h_out_of_scope(n: Note, log: TurnLog, act: str, t: ReadTask, today: date | None) -> AsyncIterator[Any]:
    log.fixed.append(P.OUT_OF_SCOPE if not has_clue(n) else "저는 음료랑 식품 신제품만 도와드릴 수 있어요.")
    if not has_clue(n):
        log.offer = product_choices(n)
    return
    yield  # noqa


# ----- 2부 매대 테스트(지시서 15) -----

from agent import explore as shelf_explore

SHELF_START, SHELF_CANCEL = "shelf-start", "shelf-cancel"
SHOW_RESULT = "show-result"  # 테스트를 한 대화의 "결과 보기" 버튼(지시서 18의 D)
PICK_SHELF = "pick-shelf"


def _shelf_shortcut(n: Note, text: str, ids: list[str], reply_to: str | None = None) -> ReadTask | None:
    """매대 테스트의 버튼(go-shelf, 확인 카드, 컨셉 고르기)과 카드의 버튼이 보낸 말은 읽지 않고 바로 한다."""
    if shelf_explore.command(ids, text, n) or SHELF_START in ids or SHELF_CANCEL in ids or "go-shelf" in ids:
        return ReadTask(do="shelf_test")
    # 지시서 17: 개선안 보기, 다시 묻기, 결과 보고서
    if reply_to and reply_to.startswith(P.IMPROVE_RUN_TO + ":") and ids:
        return ReadTask(do="improve_rerun", ids=[reply_to.split(":", 1)[1], *ids])
    if reply_to == P.IMPROVE_RUN_TO and ids:
        return ReadTask(do="improve_rerun", ids=list(ids))
    from agent.improve_review import RUN
    if len(ids) == 1 and ids[0].startswith(RUN + ":"):
        return ReadTask(do="improve_rerun", ids=ids[0].split(":")[1:])
    if IMPROVE_ALL in ids:
        return ReadTask(do="improve_rerun")
    if len(ids) == 1 and ids[0].startswith(PREPARE_IMPROVE + ":"):
        return ReadTask(do="improve", ids=[ids[0].split(":", 1)[1]])
    if IMPROVE in ids:
        return ReadTask(do="improve")
    if IMPROVE_COMPARE in ids:
        return ReadTask(do="improve_result")
    if REPORT in ids:
        return ReadTask(do="report")
    if SHOW_RESULT in ids:
        return ReadTask(do="shelf_result")
    offer = n.last_offer
    if isinstance(offer, Choices) and offer.id.startswith(PICK_SHELF) and ids and all(n.concept(i) for i in ids):
        return ReadTask(do="shelf_test", ids=list(ids))
    said = text.strip()
    if not ids and said == P.BTN_SHELF:
        return ReadTask(do="shelf_test")
    if not ids and said in (P.BTN_EARLY_RESULT, P.BTN_RESULT, P.BTN_STOPPED_RESULT):
        return ReadTask(do="shelf_result")
    if not ids and said == P.BTN_IMPROVE:
        return ReadTask(do="improve")
    if not ids and said == P.BTN_IMPROVE_ALL:  # 개선안 카드의 "남은 안 모두 테스트하기"(지시서 19)
        return ReadTask(do="improve_rerun")
    if not ids and said == P.BTN_IMPROVE_COMPARE:
        return ReadTask(do="improve_result")
    if (not ids and n.last_run and any(word in said for word in ("맛을", "제형을", "탄산을", "무탄산", "소구점"))
            and re.search(r"(?:다시|같은\s*손님).*?(?:물어|돌려|테스트|비교)", said)):
        return ReadTask(do="improve_run", text=said)
    if not ids and said == P.BTN_REPORT:
        return ReadTask(do="report")
    return None



MAKE_ALL_SPECS = "make-concepts-specs"  # 규격별로 나눈 기획자의 아이디어를 모두 컨셉 보드로 만드는 버튼(11-25)
PICK_CONFIRM = "pick-confirm"  # 보드가 둘 이상일 때 확정할 보드를 고르는 차례


def _board_shortcut(n: Note, ids: list[str]) -> ReadTask | None:
    """컨셉 보드를 만드는 버튼(규격 모두, 카드의 '컨셉으로 만들기')과 확정할 보드를 고른 답. 아니면 None."""
    if MAKE_ALL_SPECS in ids:
        group = [i for i in idea_spec.same_spec_group(n.ideas) if not n.concept(i)] or idea_spec.same_spec_group(n.ideas)
        return ReadTask(do="concepts", ids=group) if group else None
    if ids and ids[0] == "make-concepts" and len(ids) > 1 and all(n.idea(i) for i in ids[1:]):
        return ReadTask(do="concepts", ids=list(ids[1:]))
    if ids == ["make-concepts"] and n.ideas:  # 고르지 않고 누름: 읽지 않고 카드에서 고르는 차례로(하나뿐이면 바로 만든다)
        return ReadTask(do="concepts", ids=[])
    offer = n.last_offer
    if (isinstance(offer, Choices) and offer.on_card == "ideas" and ids and all(n.idea(i) for i in ids)):
        return ReadTask(do="concepts", ids=list(ids))  # 카드에서 골라 보낸 답
    if (isinstance(offer, Choices) and offer.id.startswith(PICK_CONFIRM) and ids
            and all(n.concept(i) for i in ids)):
        return ReadTask(do="confirm", ids=list(ids))
    return None


def board_names(n: Note) -> dict[str, str]:
    """보드마다 고를 때 쓰는 이름(보드 1 슬림캔 250ml). 화면의 보드 번호와 같은 차례다."""
    out = {}
    for k, c in enumerate(n.concepts, 1):
        on = idea_spec.shelf_variant(c)
        out[c["id"]] = P.board_label(k, idea_spec.label(on) if on else c.get("pack") or "")
    return out


def confirmed_concepts(n: Note) -> list[dict[str, Any]]:
    """확정한 보드. 옛 대화(보드마다 표시가 없던 때)는 확정했으면 모두."""
    if not n.confirmed:
        return []
    marked = [c for c in n.concepts if c.get("_confirmed")]
    return marked or list(n.concepts)


def _end(n: Note, text: str, offer: Any | None) -> list[Any]:
    """고정된 말 한마디와 (있으면) 묶음 하나로 차례를 끝낸다."""
    n.remember_say(text)
    n.last_offer = offer
    return [Say(text=text)] + ([offer] if offer is not None else [])


def _price_won(text: str | None) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def _test_occasion(n: Note) -> str | None:
    """매대 테스트의 방문을 겨냥한 음용 상황 쪽으로 몰아 뽑을지. 기본은 몰지 않는다(그 집단의 평소 상황 비중대로).

    몰아 뽑으면(AX_TEST_OCCASION=focus) 방문의 절반 넘게가 겨냥한 상황이 되어 선택률이 그 상황의 값으로 올라간다.
    같은 집단의 탐색 결과나 판매 자료와 견줄 수 없게 되므로, 상황별 차이는 결과의 상황별 집계로 본다.
    """
    import os

    return n.occasion_code if os.environ.get("AX_TEST_OCCASION", "").strip().lower() == "focus" else None


def shelf_spec(conv_id: str, n: Note, c: dict[str, Any], *, board_target: bool = False) -> Any:
    from shelftest import runner, store
    from tools import shelf_items

    g = n.group
    spec = runner.Spec(chat_id=conv_id, concept_id=c["id"], name=c.get("name") or "", container=c.get("_container") or "",
                       volume=int(c.get("_volume") or 0), price=_price_won(c.get("price")), promo=c.get("_promo") or c.get("promo"),
                       age=g.age if g else None, sex=g.sex if g else None, occasion_code=_test_occasion(n),
                       total=runner.default_total(), storage=c.get("_storage") or c.get("storage"),
                       features=shelf_items.concept_features(c, n.shelf_kind), season=c.get("season"), launch=c.get("launch"))
    run_id = n.runs.get(c["id"])
    if run_id and not board_target:
        previous = store.load_meta(run_id)
        if previous and previous.get("explore_id"):
            spec.age, spec.sex = previous["target"]["age"], previous["target"]["sex"]
            spec.occasion_code = previous.get("occasion_code")
            spec.explore_id, spec.target_basis = previous["explore_id"], previous.get("target_basis")
    if board_target:
        from agent.diagnose import selected_spec

        return selected_spec(c, spec)
    return spec


def shelf_run_card(run_id: str, meta: dict[str, Any]) -> Card:
    from shelftest import runner

    c, t = meta["concept"], meta["target"]
    payload = {"run_id": run_id,
               "concept": {"name": c["name"], "pack": c["pack"], "container": c["container"], "volume": c["volume"],
                           "price": c["price"]},
               "who": runner.who_label(t.get("age"), t.get("sex"))}
    return Card(id=f"shelf-run-{run_id}", stage="shelf", kind="shelf-run", title=P.CARD_SHELF_RUN, status="ready",
                payload=payload)


def result_card(run_id: str) -> Card:
    return Card(id=f"result-{run_id}", stage="result", kind="result", title=P.CARD_RESULT, status="ready",
                payload={"run_id": run_id})


def _go_shelf(n: Note) -> Actions:
    return _actions(n, "go-shelf", [("go-shelf", P.BTN_SHELF)])


async def h_shelf_test(n: Note, log: TurnLog, act: str, t: ReadTask, today: date | None) -> AsyncIterator[Any]:
    """매대에 올려 보기: 컨셉을 고르고(둘 이상이면 묻는다), 누구에게 물을지 말하고 확인을 받은 뒤 테스트를 시작한다."""
    from shelftest import method, runner

    log.stop = True
    yield Activity(id=act, label=P.ACT_LOOK, status="done")
    if SHELF_CANCEL in log.ids:
        n.shelf_pending = None
        for ev in _end(n, P.SHELF_CANCELLED, default_offer(n, log)):
            yield ev
        return
    pending = n.concept(n.shelf_pending) if n.shelf_pending else None
    action = shelf_explore.command(log.ids, log.text, n)
    if action and pending is None:
        for ev in _end(n, "이 선택은 끝났어요. 매대 테스트를 다시 열어 주세요.", default_offer(n, log)):
            yield ev
        return
    step = (pending.get("_shelf_flow") or {}).get("step") if pending else None
    if ((SHELF_START in log.ids and step not in (None, "confirm"))
            or (action == shelf_explore.SKIP and step != "entry")):
        for ev in _end(n, "현재 매대 테스트의 선택지를 확인해 주세요.", n.last_offer):
            yield ev
        return
    if pending is not None and (SHELF_START in log.ids or action and action != shelf_explore.SKIP):
        spec = shelf_spec(log.conv_id, n, pending, board_target=True)
        if action:
            events = shelf_explore.respond(n, pending, spec, action, log.ids)
            if events is not None:
                for ev in events:
                    yield ev
                return
        else:
            spec.target_basis = "기획자가 지정한 컨셉 보드의 타깃으로 바로 테스트함"
        run_id = runner.create(spec)
        from shelftest import store

        meta = store.load_meta(run_id)
        n.runs[pending["id"]] = run_id
        n.last_run = run_id
        n.shelf_pending = None
        pending.pop("_shelf_flow", None)
        yield Stage(current="shelf")
        yield shelf_run_card(run_id, meta)
        from agent import diagnose

        outcome = diagnose.after_target(n, log.conv_id, pending, run_id)
        for ev in outcome or _end(n, P.shelf_started(int(meta["total"])), None):
            yield ev
        return
    if not n.concepts:
        offer = _actions(n, "concept-first", [("make-concepts", P.BTN_MAKE_CONCEPTS)]) if n.ideas else default_offer(n, log)
        for ev in _end(n, P.SHELF_NO_CONCEPTS, offer):
            yield ev
        return
    if n.shelf != method.SHELF:
        for ev in _end(n, P.SHELF_ONLY_DRINK, default_offer(n, log)):
            yield ev
        return
    ids = [i for i in (*t.ids, *log.ids) if n.concept(i)]
    sure = confirmed_concepts(n)  # 확정한 보드가 하나면 묻지 않고 그 보드(11-25)
    concept = pending if action == shelf_explore.SKIP else (
        n.concept(ids[0]) if ids else (n.concepts[0] if len(n.concepts) == 1 else sure[0] if len(sure) == 1 else None))
    if concept is None:
        names = board_names(n)
        dup = len({c["name"] for c in n.concepts}) < len(n.concepts)  # 이름이 같은 보드(규격별)면 보드 이름으로
        options = [Option(id=c["id"], label=names[c["id"]] if dup else c["name"]) for c in n.concepts]
        offer = Choices(id=n.next_id(PICK_SHELF), kind="single", options=options,
                        on_card="concepts" if len(options) > 3 else None)
        for ev in _end(n, P.SHELF_PICK, offer):
            yield ev
        return
    if action != shelf_explore.SKIP:
        for ev in shelf_explore.entry(n, concept):
            yield ev
        return
    concept["_shelf_flow"] = {"step": "confirm"}
    spec = shelf_spec(log.conv_id, n, concept, board_target=True)
    if spec.occasion_code and spec.occasion_code not in method.occasions():
        spec.occasion_code = None
    total = max(1, min(spec.total, len(method.people(spec.age, spec.sex))))
    who = runner.who_label(spec.age, spec.sex)
    group = consumer.default_label(Group(age=spec.age, sex=spec.sex))
    n.shelf_pending = concept["id"]
    # 두 줄만: 무엇을 올리는지, 누구에게 묻는지. 음용 상황을 반씩 나누는 방법은 화면에 내지 않는다(지시서 18의 A)
    rows = [ConfirmRow(label=P.SHELF_ROWS["concept"], value=concept["name"],
                       note=f"{spec.volume}ml {spec.container} · {spec.price:,}원"),
            ConfirmRow(label=P.SHELF_ROWS["who"], value=f"{who} {total:,}명")]
    confirm = Confirm(id=n.next_id("shelf-confirm"), title=P.SHELF_CONFIRM_TITLE, rows=rows,
                      confirm=ConfirmButton(id=SHELF_START, label=P.BTN_SHELF_START),
                      cancel=ConfirmButton(id=SHELF_CANCEL, label=P.BTN_SHELF_CANCEL))
    for ev in _end(n, P.shelf_confirm_say(who, total, group), confirm):
        yield ev


def _result_bits(v: dict[str, Any], eta_s: float | None = None) -> tuple[list[Bit], list[str], str]:
    """테스트 결과를 알리는 말의 사실(현황 → 알게 된 것), 그 차례를 검사할 구절, 끝에 붙일 다음 문장.
    도는 중: 몇 명이 답했고 언제 끝나는지 → 지금까지의 숫자. 끝난 뒤: 끝났다 → 결론 → 알게 된 것 둘. 숫자는 코드가 넣는다."""
    from agent import result_brief as RB

    r = v["result"]
    name = v["concept"]["name"]
    n_all, k, total = int(r["n"]), int(r["picked"]), int(v["total"])
    rank, products = r.get("rank"), int(r["products"])
    picked_s = f"{name}{josa(name, '을/를')}"
    if v["status"] == "running":
        asked = int(v["asked"])
        sentence = P.result_progress(asked, total)
        fact = f"{total}명에게 묻는 중이고 {asked}명이 답했다"
        order = [f"{asked:,}명"]
        if eta_s is not None:
            sentence += " " + P.result_eta(eta_s)
            fact += (". 1분 안에 끝난다" if eta_s < 60 else f". 약 {P.eta_minutes(eta_s)}분 뒤에 끝난다")
            order.append("1분" if eta_s < 60 else f"{P.eta_minutes(eta_s)}분")
        bits = [Bit(fact=fact + "(첫 문장은 이 현황)", sentence=sentence)]
        so_far = P.result_so_far(n_all, k, name, rank, products)
        bits.append(Bit(fact=("지금까지 " + (f"{n_all}명 중 {k}명이 {picked_s} 골랐고 {products}개 제품 가운데 {rank}위다"
                                          if k else f"{n_all}명 중 {picked_s} 고른 손님이 없다")
                              + "('지금까지는'으로 시작한다)"),
                        sentence=so_far, names=[name]))
        if k:
            order.append(f"{k:,}명")
        return bits, order, P.result_next_running(total)
    group = v["who"]["label"].removesuffix(" 손님").strip()
    stopped = v["status"] == "stopped"  # 멈춘 테스트: 멈춘 사실은 h_shelf_result가 첫머리에 붙인다(11-25)
    bits = [] if stopped else [Bit(fact="테스트가 끝났다(첫 문장)", sentence=P.RESULT_DONE)]
    line = P.result_done_line(group, n_all, k, name, rank, products)
    bits.append(Bit(fact=(f"{group} {n_all}명 중 {k}명이 {picked_s} 골랐고 {products}개 제품 가운데 {rank}위다" if k
                          else f"{group} {n_all}명 중 {picked_s} 고른 손님은 없었다"),
                    sentence=line, names=[name, group]))
    order = [f"{k:,}명" if k else f"{n_all:,}명"]
    if stopped and n_all < P.STOPPED_MIN_N:  # 답이 적으면 알게 된 것을 말하지 않는다
        return bits, order, P.FEW_ANSWERS
    occ = RB.top_occasion(r) if k else None
    bar = RB.top_barrier(r)
    # 고른 손님의 절반 이상이 자사 제품을 고르던 손님이면 걸린 점 대신 그것(자기잠식)을 말한다
    f = RB.inflow(r) if k else None
    own = (k, f["own"], f["own_top"][0]) if f and k >= 2 and f["own_top"] and f["own"] * 2 >= k else None
    insight = P.result_insight(occ, bar, own)
    if insight:
        facts = []
        if occ:
            facts.append(f"고른 비율이 가장 높은 때는 '{occ}'")
            order.append(occ)
        if own:
            facts.append(f"고른 {k}명 가운데 {own[1]}명은 원래 자사 제품을 고르던 손님이다(가장 많은 것은 {own[2]}). "
                         "새 손님을 데려온 것이 아니라 우리 제품의 손님을 옮겨 온 것이다")
            order.append(f"{own[1]:,}명")
        elif bar:
            facts.append(f"고르지 않은 손님이 가장 많이 든 까닭은 '{bar}'")
            order.append(bar)
        bits.append(Bit(fact=", ".join(facts) + "(작은따옴표 안의 말을 그대로 쓴다)", sentence=insight,
                        names=[x for x in (occ, bar if not own else own[2]) if x]))
    return bits, order, P.RESULT_NEXT_DONE if k else P.RESULT_NEXT_NONE


async def h_shelf_result(n: Note, log: TurnLog, act: str, t: ReadTask, today: date | None) -> AsyncIterator[Any]:
    """결과 보여 줘: 카드 result를 내고 결과에서 한두 가지를 말한다. 아직 100명이 안 됐으면 몇 명이 다녀갔는지만."""
    from shelftest import runner

    log.stop = True
    ids = [i for i in (*t.ids, *log.ids) if n.runs.get(i)]
    run_id = n.runs[ids[0]] if ids else n.last_run
    v = runner.view(run_id) if run_id else None
    if v is None:
        yield Activity(id=act, label=P.ACT_LOOK, status="done")
        for ev in _end(n, P.SHELF_GONE if run_id else P.SHELF_NO_RUN, _go_shelf(n) if n.concepts else None):
            yield ev
        return
    stopped = v["status"] == "stopped"
    if stopped and not v["asked"]:  # 멈췄는데 답한 손님이 없으면 결과 화면을 열지 않는다(11-25)
        yield Activity(id=act, label=P.ACT_LOOK, status="done")
        for ev in _end(n, P.STOPPED_EMPTY, None):
            yield ev
        return
    if v["status"] == "running" and v["asked"] < min(P.SHELF_EARLY_AT, v["total"]) or not v["result"]:
        yield Activity(id=act, label=P.ACT_LOOK, status="done")
        for ev in _end(n, P.shelf_waiting(v["asked"], v["total"]), None):
            yield ev
        return
    yield Activity(id=act, label=P.ACT_RESULT, status="running")
    yield Stage(current="result")
    yield result_card(run_id)
    from agent import result_brief as RB
    from shelftest import store

    eta = RB.eta_seconds(store.load_meta(run_id) or {}, store.answers(run_id)) if v["status"] == "running" else None
    bits, order, after = _result_bits(v, eta)
    turn = voice.result_turn(product=v["concept"]["name"], received=bits, order=order, said_before=n.said_before)
    out = await voice.speak(turn)
    yield Activity(id=act, label=P.ACT_RESULT, status="done")
    # 마지막은 다음: 도는 중이면 끝나면 바뀐다는 것, 끝났으면 할 수 있는 일(고정된 말)
    text = f"{out.text} {after}"
    if stopped:  # 멈춘 사실과 인원은 코드가 붙인다(11-25)
        text = f"{P.stopped_line(int(v['asked']), int(v['total']))} {text}"
    n.remember_say(text)
    yield Say(text=text)
    from shelftest import group_flow
    if group_flow.invitation(v, group_flow.plan_for(n, run_id, v["concept"]["id"]) or {"items": []}):
        offer = _actions(n, "after-result", [(f"{PREPARE_IMPROVE}:{run_id}", "개선안 테스트 준비하기"), (REPORT, P.BTN_REPORT)])
    else:
        offer = result_offer(n)
    n.last_offer = offer
    yield offer


# ----- 2부: 한 손님에게 묻기(지시서 17의 A) -----

IMPROVE, IMPROVE_ALL, IMPROVE_COMPARE, REPORT = "improve", "improve-all", "improve-compare", "report"
ASK_SHOPPER = "ask-shopper"
GROUP_OPEN = "group-questions"
PREPARE_IMPROVE = "prepare-improve"
CARD_WORDS = (P.BTN_EARLY_RESULT, P.BTN_RESULT, P.BTN_STOPPED_RESULT, P.BTN_SHELF, P.BTN_IMPROVE, P.BTN_IMPROVE_ALL, P.BTN_IMPROVE_COMPARE,
              P.BTN_REPORT)


def result_offer(n: Note, interview_run: str | None = None) -> Actions:
    items = [(IMPROVE, P.BTN_IMPROVE)]
    if interview_run and interview_run in n.runs.values():
        items.append((f"{GROUP_OPEN}:{interview_run}", P.BTN_OTHER_INTERVIEW))
    return _actions(n, "after-result", [*items, (REPORT, P.BTN_REPORT)])


def _shopper_pool(run_id: str) -> list[str]:
    """부를 손님의 차례: 결과의 집은 손님의 말 → 안 집은 손님의 말 → 테스트의 답에서 컨셉을 올린 매대의 답이 있는
    손님을 방문 차례대로(집은 손님 먼저). 같은 손님은 한 번만."""
    from shelftest import result, runner, store

    v = runner.view(run_id)
    q = (v or {}).get("result") and v["result"]["quotes"]
    pool = [x["visitor"] for x in (q["picked"] + q["passed"])] if q else []
    meta = store.load_meta(run_id) or {}
    pairs, _ = result.concept_visits(store.answers(run_id))
    line = meta.get("line")
    pool += [c["visit"] for _, c in pairs if c.get("product") == line]
    pool += [c["visit"] for _, c in pairs if c.get("product") != line]
    return list(dict.fromkeys(x for x in pool if x))


def _shopper_to_ask(n: Note, run_id: str | None) -> str | None:
    """"손님 인터뷰하기"와 "다른 손님 인터뷰하기"가 부를 손님: 아직 안 부른 손님 가운데 차례대로(지시서 18의 C).
    모두 불렀으면 처음부터 다시 돈다."""
    from shelftest import store

    if not run_id or not store.valid_id(run_id):
        return None
    pool = _shopper_pool(run_id)
    if not pool:
        return None
    called = set(n.interviewed.get(run_id) or [])
    left = [x for x in pool if x not in called]
    if not left:
        n.interviewed[run_id] = []
        left = pool
    return left[0]


def interview_choices(n: Note) -> Choices:
    """아직 하지 않은 물음, "다른 손님 인터뷰하기", "인터뷰 마치기"."""
    asked = set((n.interview or {}).get("asked") or [])
    options = [Option(id=i, label=label) for i, label in P.INTERVIEW_ASKS if i not in asked]
    has_plan = bool((n.interview or {}).get("participant"))
    if has_plan:
        options = options[:2]
    options.append(Option(id=P.INTERVIEW_NEXT[0], label=P.INTERVIEW_NEXT[1]))
    if has_plan:
        run_id = n.interview["run_id"]
        options.append(Option(id=f"{GROUP_OPEN}:{run_id}", label=P.BTN_OTHER_INTERVIEW))
    options.append(Option(id=P.INTERVIEW_END[0], label=P.INTERVIEW_END[1]))
    return Choices(id=n.next_id("interview"), kind="single", options=options)


def _interview_continues(n: Note, text: str, ids: list[str]) -> bool:
    """손님을 부른 동안의 말인가. 다른 묶음의 버튼이나 카드의 버튼이 보낸 말이면 아니다."""
    own = {i for i, _ in P.INTERVIEW_ASKS} | {P.INTERVIEW_NEXT[0], P.INTERVIEW_END[0]}
    if ids:
        return all(i in own for i in ids)
    return text.strip() not in CARD_WORDS


def _call_visitor(n: Note, conv_id: str, ids: list[str]) -> list[Any]:
    from shelftest import interview, store

    run_id, visitor = (ids + ["", ""])[:2]
    meta = store.load_meta(run_id) if store.valid_id(run_id) else None
    v = interview.find(run_id, visitor) if meta and meta.get("chat_id") == conv_id else None
    out: list[Any] = []  # 찾아볼 것이 없으니 하는 일 표시를 붙이지 않는다
    if v is None:
        n.interview = None
        return out + _end(n, P.INTERVIEW_NOT_FOUND, result_offer(n) if n.last_run else None)
    n.interview = {"run_id": run_id, "visitor": visitor, "who": v.who, "asked": [], "qa": []}
    called = n.interviewed.setdefault(run_id, [])  # 카드의 "이 손님 인터뷰하기"로 부른 손님도 적는다
    if visitor not in called:
        called.append(visitor)
    offer = interview_choices(n)
    return out + _end(n, P.interview_called(v.called), offer)


async def _interview_turn(n: Note, conv_id: str, text: str, ids: list[str]) -> AsyncIterator[Any]:
    from shelftest import interview

    iv = n.interview or {}
    said = text.strip()
    if P.INTERVIEW_NEXT[0] in ids:  # 지금 손님을 보내고 다음 손님을 바로 부른다(읽기를 거치지 않는다)
        run_id = iv.get("run_id") or n.last_run or ""
        n.interview = None
        if iv.get("participant"):
            from shelftest import group_flow, group_setup
            setup = group_setup.prepare(run_id)
            next_guest = next((p for p in (setup or {}).get("candidates", [])
                               if p["id"] not in n.interviewed.get(run_id, [])), None)
            if next_guest:
                called = _call_visitor(n, conv_id, [run_id, next_guest["id"]])
                if n.interview:
                    n.interview.update(participant=next_guest, question=iv["question"], concept=iv["concept"])
                    yield group_flow.individual_card(n.interview)
                    for event in called:
                        if not isinstance(event, Choices):
                            yield event
                    async for event in _interview_turn(n, conv_id, iv["question"], []):
                        yield event
                    return
            for event in _end(n, P.INTERVIEW_BYE, result_offer(n, iv.get("run_id"))):
                yield event
            return
        for ev in _call_visitor(n, conv_id, [run_id, _shopper_to_ask(n, run_id) or ""]):
            yield ev
        return
    if P.INTERVIEW_END[0] in ids or (not ids and any(c in said.replace(" ", "") for c in
                                                       (x.replace(" ", "") for x in P.INTERVIEW_END_CUES))):
        n.interview = None
        for ev in _end(n, P.INTERVIEW_BYE, result_offer(n, iv.get("run_id"))):
            yield ev
        return
    act = n.next_id("work")
    v = interview.find(iv.get("run_id", ""), iv.get("visitor", ""))
    if v is None:
        n.interview = None
        yield Activity(id=act, label=P.ACT_LOOK, status="done")
        for ev in _end(n, P.INTERVIEW_NOT_FOUND, result_offer(n)):
            yield ev
        return
    yield Activity(id=act, label=P.ACT_INTERVIEW, status="running")
    qa = [list(x) for x in iv.get("qa") or []]
    reply, _ = await interview.answer(v, qa, said)
    iv["qa"] = qa + [[said, reply]]
    iv["asked"] = list(dict.fromkeys([*(iv.get("asked") or []), *(i for i in ids if i.startswith("ask-"))]))
    n.interview = iv
    yield Activity(id=act, label=P.ACT_INTERVIEW, status="done")
    if iv.get("participant"):
        from shelftest.group_flow import individual_card
        yield individual_card(iv)
    yield Say(text=reply, speaker=Speaker(kind="shopper", label=v.who))
    offer = interview_choices(n)
    n.last_offer = offer
    yield offer


# ----- 2부: 개선안 테스트(지시서 17의 B) -----


def _base_run(n: Note, t: ReadTask, log: TurnLog) -> str | None:
    """개선안의 처음 안이 되는 테스트: 말한 컨셉의 테스트, 아니면 개선안 표의 것, 아니면 마지막 테스트."""
    ids = [i for i in (*t.ids, *log.ids) if n.runs.get(i)]
    if ids:
        return n.runs[ids[0]]
    run_ids = set(n.runs.values())
    chosen = next((i for i in (*t.ids, *log.ids) if i in run_ids), None)
    if chosen:
        return chosen
    if n.improve and n.improve.get("base_run"):
        if n.last_run and n.last_run == n.runs.get(n.improve.get("concept_id")):
            return n.last_run
        return n.improve["base_run"]
    return n.last_run


def _survey_focus(n: Note) -> str | None:
    """마지막으로 올린 조사에서 나온 첫 안(약속 v1.20). 그 조사의 안을 이미 채택했으면 채택한 안이 먼저라 없다."""
    upload_id, imp = (n.followup or {}).get("upload_id"), n.improve or {}
    mine = [it["id"] for it in imp.get("items") or [] if upload_id and it.get("followup") == upload_id]
    return mine[0] if mine and imp.get("adopted_item_id") not in mine else None


def improve_card(n: Note) -> Card:
    """개선안 테스트 카드. 항목의 kind, before, after는 타일이 바꾼 값을 그리는 데 쓴다(약속 v1.11).
    옛 노트의 항목에 앞뒤 값이 없으면 kind만 값에서 정하고 앞뒤 값은 보내지 않는다(화면이 change를 가른다)."""
    from agent import improve, improve_compare
    from shelftest import store

    imp = n.improve or {}
    base_run = imp.get("base_run") or ""
    items = []
    for it in imp.get("items") or []:
        extra = {k: it[k] for k in ("before", "after", "hypothesis", "evidence", "run_id") if it.get(k)}
        if it.get("values"):
            extra["edit_values"] = it["values"]
        if it.get("run_id") and (paired := improve_compare.for_runs(base_run, it["run_id"])):
            extra["paired"] = paired
        items.append({"id": it["id"], "kind": it.get("kind") or improve.kind_of(it.get("values") or {}),
                      "change": it["change"], **extra, "reason": it["reason"]})
    payload: dict[str, Any] = {"base_run": base_run, "items": items}
    points = [(it["values"]["price"], it.get("run_id")) for it in imp.get("items", []) if it.get("price_sweep")]
    if len(points) == 2 and (original := store.load_meta(base_run)):
        payload["price_curve"] = improve_compare.price_curve(base_run, original["concept"]["price"], points)
    if imp.get("adopted_item_id"):
        payload["adopted_item_id"] = imp["adopted_item_id"]
    if focus := imp.get("focus_id") or _survey_focus(n):
        payload["focus_id"] = focus
    return Card(id="improve", stage="improve", kind="improve", title=P.CARD_IMPROVE, status="ready",
                payload=payload)


def _ready_view(run_id: str | None) -> dict[str, Any] | None:
    """결과를 말할 만한 테스트의 모양(100명 이상이 다녀갔거나 끝남). 아니면 None."""
    from shelftest import runner

    v = runner.view(run_id) if run_id else None
    if v is None or not v["result"]:
        return None
    if v["status"] == "running" and v["asked"] < min(P.SHELF_EARLY_AT, v["total"]):
        return None
    return v


def _improve_state(n: Note, base_run: str, concept_id: str) -> dict[str, Any]:
    if not n.improve or n.improve.get("base_run") != base_run:
        current = n.improve or {}
        boards = dict(current.get("boards", {}))
        if current.get("base_run"):
            boards[current["base_run"]] = {key: value for key, value in current.items() if key != "boards"}
        n.improve = boards.pop(base_run, {"base_run": base_run, "concept_id": concept_id, "items": []})
        if boards:
            n.improve["boards"] = boards
    return n.improve


def _add_item(imp: dict[str, Any], base: Any, values: dict[str, Any], reason: str,
              hypothesis: str | None = None, evidence: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """표에 안 한 줄을 더한다. base는 improve.Base(처음 안)."""
    from agent import improve, improve_suggestions

    item = {"id": improve.next_letter(imp["items"]), **improve.describe(base, values), "reason": reason,
            "values": dict(values), "hypothesis": hypothesis or improve_suggestions.hypothesis(values),
            "evidence": [dict(entry) for entry in evidence] if evidence else [{"origin": "suggestion", "text": reason}]}
    imp["items"].append(item)
    return item


def _owned_improve_run(n: Note, conv_id: str, run_id: str | None) -> dict[str, Any] | None:
    from shelftest import store

    meta = store.load_meta(run_id) if store.valid_id(run_id) else None
    if not meta or meta.get("chat_id") != conv_id or not n.concept(meta["concept_id"]):
        return None
    return meta


def _improve_original(n: Note, log: TurnLog, task: ReadTask) -> dict[str, Any] | None:
    meta = _owned_improve_run(n, log.conv_id, _base_run(n, task, log))
    if meta and meta.get("base_run_id"):
        return _owned_improve_run(n, log.conv_id, meta["base_run_id"])
    return meta if meta and meta.get("mode", "target") == "target" else None


def _start_rerun(n: Note, conv_id: str, base: dict[str, Any], item: dict[str, Any]) -> str | None:
    """고친 안을 같은 손님에게 다시 묻는다(POST /api/runs와 같은 길). 컨셉이 없는 매대의 답은 다시 쓴다."""
    from agent import improve, improve_compare
    from shelftest import runner

    meta = _owned_improve_run(n, conv_id, base["id"])
    item.pop("run_error", None)
    if meta is None or meta.get("mode", "target") != "target" or meta.get("change"):
        item["run_error"] = "원래 안 매대 테스트를 다시 열어 주세요."
        return None
    saved = _owned_improve_run(n, conv_id, item.get("run_id"))
    if saved and improve_compare.same_test(meta, saved) and saved.get("status") in ("running", "done"):
        runner.ensure_running(saved["id"])
        return saved["id"]
    original = improve.Base.of(meta["concept"])
    values = item["values"]
    if improve.check_values(original, values, price_step=True) or not improve.diff(original, values):
        item["run_error"] = "테스트할 새 조건을 확인해 주세요."
        return None
    changed = improve.applied(original, values)
    spec = runner.Spec(chat_id=conv_id, concept_id=meta["concept_id"], name=changed.name,
                       container=changed.container, volume=changed.volume, price=changed.price,
                       promo=changed.promo, age=meta["target"].get("age"), sex=meta["target"].get("sex"),
                       occasion_code=meta.get("occasion_code"), total=int(meta.get("requested") or meta["total"]),
                       mode="improve", base_run_id=base["id"], explore_id=meta.get("explore_id"),
                       target_basis=meta.get("target_basis"), storage=meta.get("storage"),
                       change=dict(values), features=changed.features)
    try:
        run_id = runner.create(spec)
    except ValueError as err:
        item["run_error"] = str(err)
        return None
    item["run_id"] = run_id
    return run_id


def _adopt_improvement(n: Note, conv_id: str, ids: list[str]) -> list[Any]:
    from agent import improve, improve_compare

    imp = n.improve or {}
    base_run, item_id = ids if len(ids) == 2 else ("", "")
    unavailable = "이 대화에서 채택할 수 있는 개선안을 다시 골라 주세요."
    if not item_id or base_run != imp.get("base_run"):
        return _end(n, unavailable, None)
    original = _owned_improve_run(n, conv_id, base_run)
    item = next((it for it in imp.get("items", []) if it["id"] == item_id), None)
    if not original or not item or original["concept_id"] != imp.get("concept_id"):
        return _end(n, unavailable, None)
    if imp.get("adopted_item_id") == item_id:
        return [improve_card(n), *_end(n, "이미 컨셉 보드에 반영한 개선안이에요.", _go_shelf(n))]
    if imp.get("adopted_item_id"):
        return _end(n, "이 테스트에서 이미 한 안을 채택했어요. 현재 컨셉 보드를 다시 테스트해 주세요.", _go_shelf(n))
    variant = _owned_improve_run(n, conv_id, item.get("run_id"))
    if (not variant or not improve_compare.for_runs(base_run, variant["id"])
            or not improve.matches_change(original["concept"], variant["concept"], item["values"])):
        return _end(n, "같은 손님의 비교 결과가 나온 개선안부터 채택할 수 있어요.", None)
    concept = n.concept(original["concept_id"])
    candidate = copy.deepcopy(concept)
    board_price = _price_won(candidate.get("price"))
    if board_price != original["concept"]["price"] and n.runs.get(concept["id"]) == base_run:
        selected = shelf_spec(conv_id, n, concept, board_target=True)
        if selected.price != board_price and selected.price == original["concept"]["price"]:
            candidate.update(price=improve.won(selected.price), _price_by="planner")
    if not improve.update_board(candidate, original["concept"], variant["concept"], item["values"]):
        return _end(n, "컨셉 보드의 조건이 달라졌어요. 현재 컨셉을 다시 테스트해 주세요.", _go_shelf(n))
    if candidate.get("price") != concept.get("price") and "price" not in candidate["changed"]:
        candidate["changed"].append("price")
    concept.update(candidate)
    imp["focus_id"] = item_id
    imp["adopted_item_id"] = item_id
    concept["_adopted_improvement"] = {
        "base_run": base_run, "run_id": variant["id"], "item_id": item_id,
        **{key: item[key] for key in ("reason", "hypothesis", "evidence") if key in item},
    }
    label = improve.plan_name(imp["items"], item)
    return [concepts_card(n), improve_card(n),
            *_end(n, f"{label}{josa(label, '을/를')} 컨셉 보드에 반영했어요.", _go_shelf(n))]


async def h_improve(n: Note, log: TurnLog, act: str, t: ReadTask, today: date | None) -> AsyncIterator[Any]:
    """개선안 만들어 줘: 결과에서 걸린 점을 보고 한 가지씩 바꾼 안을 둘이나 셋. 모델이 쓰고 코드가 검사한다."""
    from agent import improve
    from shelftest import group_flow

    log.stop = True
    origin = _improve_original(n, log, t)
    run_id = origin["id"] if origin else None
    v = _ready_view(run_id)
    if v is None:
        yield Activity(id=act, label=P.ACT_LOOK, status="done")
        from shelftest import runner

        raw = runner.view(run_id) if run_id else None
        text = P.shelf_waiting(raw["asked"], raw["total"]) if raw and raw["status"] == "running" else P.IMPROVE_NO_RESULT
        for ev in _end(n, text, None if raw and raw["status"] == "running" else (_go_shelf(n) if n.concepts else None)):
            yield ev
        return
    imp = _improve_state(n, run_id, v["concept"]["id"])
    # 매대 결과에서 처음 들어올 때만 추가 조사를 제안한다. 발언을 듣고 돌아오면 변경안을 연다.
    if f"{PREPARE_IMPROVE}:{run_id}" in log.ids:
        from shelftest import group
        invite = group_flow.invitation(v, imp)
        if invite and (setup := group.setup(run_id)):
            n.interview_plan = {"run": run_id, "question": None}
            yield Activity(id=act, label=P.ACT_LOOK, status="done")
            yield Stage(current="improve")
            yield group_flow._card(setup)
            for ev in _end(n, *invite):
                yield ev
            return
    from agent import improve_review

    if not imp.get("proposed") and not (imp["items"] and not origin.get("concept_prompt_version")):
        yield Activity(id=act, label=P.ACT_IMPROVE, status="running")
        base = improve.Base.of(origin["concept"])
        found, _ = await improve.propose(base, v["result"], v["who"]["label"],
                                                   base.features.get("kind") or n.shelf_kind,
                                                   enhanced=bool(origin.get("concept_prompt_version")))
        for f in found:
            item = next((it for it in imp["items"] if it["values"] == f["values"]), None)
            if item is None:
                item = _add_item(imp, base, f["values"], f["reason"], f["hypothesis"], f["evidence"])
            if f.get("price_sweep"):
                item["price_sweep"] = True
                current_evidence = item.setdefault("evidence", [])
                current_evidence.extend(ev for ev in f["evidence"] if ev not in current_evidence)
        imp["proposed"] = True
    response = improve_review.overview(n, v)
    yield Stage(current="improve")
    yield improve_card(n)
    yield Activity(id=act, label=P.ACT_IMPROVE, status="done")
    for event in response:
        yield event


async def h_improve_rerun(n: Note, log: TurnLog, act: str, t: ReadTask, today: date | None) -> AsyncIterator[Any]:
    """개선안 카드의 "테스트하기"(ids에 안의 id), 또는 "남은 안 모두 테스트하기"(ids가 비었음).
    읽기가 고를 수도 있다("A안으로 다시 물어봐", "가격 변경안으로 테스트해 줘": 읽기에 넘긴 개선안 표의 id)."""
    from agent import improve, improve_compare
    from shelftest import runner, store

    log.stop = True
    yield Activity(id=act, label=P.ACT_LOOK, status="done")
    imp = n.improve
    base = _owned_improve_run(n, log.conv_id, imp.get("base_run")) if imp else None
    ids = t.ids
    if ids and store.valid_id(ids[0]):
        if not base or ids[0] != base["id"] or len(ids) < 2:
            ids = ["?"]
        else:
            ids = ids[1:]
    candidates = (imp or {}).get("items", [])
    items = [it for it in candidates if not ids or it["id"] in ids]
    if imp is None or base is None or not items:
        for ev in _end(n, P.IMPROVE_NO_ITEM if t.ids else P.IMPROVE_NO_RESULT, result_offer(n) if n.last_run else None):
            yield ev
        return
    if ids and len(items) == 1:
        imp["focus_id"] = items[0]["id"]
    if any(it.get("price_sweep") for it in items):
        items = [it for it in candidates if it in items or it.get("price_sweep")]
    started, errors = [], []
    for it in items:
        saved = _owned_improve_run(n, log.conv_id, it.get("run_id"))
        if saved and improve_compare.same_test(base, saved) and saved["status"] in ("running", "done"):
            runner.ensure_running(saved["id"])
            continue
        if _start_rerun(n, log.conv_id, base, it):
            started.append(improve.plan_name(imp["items"], it))
        elif it.get("run_error"):
            errors.append(it["run_error"])
    yield Stage(current="improve")
    yield improve_card(n)
    text = P.improve_started(started) if started else P.IMPROVE_STILL_RUNNING
    if errors:
        text = " ".join([text, *dict.fromkeys(errors)]) if started else " ".join(dict.fromkeys(errors))
    # 도는 동안에는 버튼을 내지 않는다(결과가 나오기 전에 보고서로 넘어가면 흐름이 꼬인다)
    offer = _go_shelf(n) if errors and not started else None
    for ev in _end(n, text, offer):
        yield ev


async def h_improve_run(n: Note, log: TurnLog, act: str, t: ReadTask, today: date | None) -> AsyncIterator[Any]:
    """기획자가 직접 말한 안("1,500원으로 해서 다시 물어봐"): 바꿀 값을 뽑고 검사한 뒤 표에 한 줄을 더하고 바로 돌린다."""
    from agent import improve

    log.stop = True
    origin = _improve_original(n, log, t)
    run_id = origin["id"] if origin else None
    v = _ready_view(run_id)
    if v is None:
        yield Activity(id=act, label=P.ACT_LOOK, status="done")
        for ev in _end(n, P.IMPROVE_NO_RESULT, _go_shelf(n) if n.concepts else None):
            yield ev
        return
    yield Activity(id=act, label=P.ACT_IMPROVE_RUN, status="running")
    base = improve.Base.of(origin["concept"])
    values, _ = await improve.extract(base, t.text or log.text,
                                      allow_exact_price=bool(origin.get("concept_prompt_version")))
    yield Activity(id=act, label=P.ACT_IMPROVE_RUN, status="done")
    if not values:
        for ev in _end(n, P.IMPROVE_NOT_UNDERSTOOD, result_offer(n)):
            yield ev
        return
    imp = _improve_state(n, run_id, v["concept"]["id"])
    item = next((it for it in imp["items"] if it["values"] == values), None)
    if item is None:
        item = _add_item(imp, base, values, P.IMPROVE_REASON_PLANNER)
    imp["focus_id"] = item["id"]
    if not _start_rerun(n, log.conv_id, v, item):
        for ev in _end(n, item.get("run_error") or P.IMPROVE_NOT_UNDERSTOOD, _go_shelf(n)):
            yield ev
        return
    yield Stage(current="improve")
    yield improve_card(n)
    for ev in _end(n, P.improve_started([improve.plan_name(imp["items"], item)]), None):
        yield ev


async def h_improve_result(n: Note, log: TurnLog, act: str, t: ReadTask, today: date | None) -> AsyncIterator[Any]:
    """완료된 공통 방문에서 선택이 바뀐 방향을 말한다."""
    from agent import improve
    from shelftest import runner

    log.stop = True
    imp = n.improve
    ran = [it for it in (imp or {}).get("items") or [] if it.get("run_id")]
    origin = _owned_improve_run(n, log.conv_id, imp.get("base_run")) if imp else None
    base = runner.view(origin["id"]) if origin else None
    if not ran or base is None or not base["result"]:
        yield Activity(id=act, label=P.ACT_LOOK, status="done")
        offer = (_actions(n, "improve", [(IMPROVE_ALL, P.BTN_IMPROVE_ALL), (REPORT, P.BTN_REPORT)])
                 if imp and imp.get("items") else result_offer(n) if n.last_run else None)
        for ev in _end(n, P.IMPROVE_NOTHING_RAN, offer):
            yield ev
        return
    ready = []
    for it in ran:
        v = _ready_view(it["run_id"]) if _owned_improve_run(n, log.conv_id, it["run_id"]) else None
        if v is not None:
            ready.append((it, v))
    if not ready:
        yield Activity(id=act, label=P.ACT_LOOK, status="done")
        for ev in _end(n, P.IMPROVE_STILL_RUNNING, _actions(n, "improve-wait", [(REPORT, P.BTN_REPORT)])):
            yield ev
        return
    yield Activity(id=act, label=P.ACT_RESULT, status="running")
    yield Stage(current="improve")
    card = improve_card(n)
    comparisons = [it for it in card.payload["items"] if it.get("paired")]
    if comparisons:
        row = next((it for it in comparisons if it["id"] == card.payload.get("focus_id")), comparisons[0])
        card.payload["focus_id"] = imp["focus_id"] = row["id"]
    yield card
    if comparisons or origin.get("concept_prompt_version"):
        if comparisons:
            from agent.improve_review import compared_text
            text = compared_text(row, row["paired"])
        elif base["status"] == "running" or any(v["status"] == "running" for _, v in ready):
            text = "두 안의 테스트가 끝나면 같은 손님의 선택을 짝지어 볼게요."
        else:
            text = "두 안에 모두 응답한 같은 손님을 확인할 수 없어요."
        yield Activity(id=act, label=P.ACT_RESULT, status="done")
        for ev in _end(n, text, _actions(n, "after-improve", [(REPORT, P.BTN_REPORT)])):
            yield ev
        return
    r0 = base["result"]
    # 처음 안의 숫자는 한 번만 말한다(안마다 되풀이하지 않는다)
    first = improve.BASE_NAME
    bits = [Bit(fact=f"{first}은 {r0['n']}명 가운데 {r0['picked']}명이 구매했다",
                sentence=f"{first}은 {r0['n']}명 가운데 {r0['picked']}명이 구매했어요.", names=[first])]
    unclear = False
    for it, v in ready[:2]:
        r = v["result"]
        word = improve.verdict(r0, r)
        unclear = unclear or word == "unclear"
        label = improve.plan_name(imp["items"], it)
        # 폭이 겹칠 때의 말은 아래의 한 문장이 맡는다(여기서 또 말하면 되풀이가 된다)
        how = {"more": f". {first}보다 많이 구매했다", "less": f". {first}보다 적게 구매했다", "unclear": ""}[word]
        bits.append(Bit(fact=f"{label}({it['change']}){josa(label, '은/는')} {r['n']}명 가운데 {r['picked']}명이 구매했다{how}",
                        sentence=f"{label}{josa(label, '은/는')} {r['n']}명 가운데 {r['picked']}명이 구매했어요.",
                        names=[label, it["change"]]))
    if unclear:
        bits.append(Bit(fact="기존안과의 차이가 오차 범위 안이다(꼭 '오차 범위 안이라 어느 쪽이 낫다고 보기 어렵다'고 말한다)",
                        sentence=P.IMPROVE_UNCLEAR))
    turn = voice.open_turn(product=base["concept"]["name"], received=bits, found=None, addition=None, thoughts=[],
                           said_before=n.said_before)
    out = await voice.speak(turn)
    text = out.text
    if unclear and "오차 범위" not in text:
        text = turn.fallback  # 폭이 겹치면 꼭 그렇게 말한다(모델이 빠뜨리면 글틀)
        if "오차 범위" not in text:  # 글틀이 앞의 몇 문장만 쓸 때
            text = f"{text} {P.IMPROVE_UNCLEAR}"
    yield Activity(id=act, label=P.ACT_RESULT, status="done")
    for ev in _end(n, text, _actions(n, "after-improve", [(REPORT, P.BTN_REPORT)])):
        yield ev


# ----- 2부: 결과 보고서(지시서 17의 C) -----


async def h_report(n: Note, log: TurnLog, act: str, t: ReadTask, today: date | None) -> AsyncIterator[Any]:
    """결과 보고서 만들어 줘: 단계를 report로 옮기고 한 문장과 제안서 버튼. 테스트가 없으면 지금의 제안서와 같다."""
    if not n.concepts:
        log.fixed.append(P.DOWNLOAD_NO_CONCEPTS)
        return
    if n.runs:
        yield Stage(current="report")
        log.fixed.append(P.REPORT_READY)
    else:
        log.fixed.append(P.DOWNLOAD_READY)
    items = [("download", P.BTN_DOWNLOAD)]
    # 후속 개선은 조사를 마치고 다시 왔을 때의 일이다: 여기서는 말로만 안내하고 버튼은 내지 않는다
    log.offer = _actions(n, "download", items)


HANDLERS = {
    "ideas": h_ideas, "more": h_more, "edit_idea": h_edit_idea, "my_idea": h_my_idea, "keep": h_keep,
    "drop": h_drop, "concepts": h_concepts, "edit_concept": h_edit_concept, "confirm": h_confirm,
    "answer": h_answer, "not_ready": h_not_ready, "out_of_scope": h_out_of_scope, "download": h_download,
    "shelf_test": h_shelf_test, "shelf_result": h_shelf_result, "improve": h_improve, "improve_rerun": h_improve_rerun,
    "improve_run": h_improve_run, "improve_result": h_improve_result, "report": h_report,
}


def _failed(n: Note, log: TurnLog, task: str, retry_tasks: list[ReadTask]) -> None:
    n.retry = (retry_tasks, steps.Read(tasks=retry_tasks))
    log.stop = True
    log.failed = task


# ---------- 보탤 것 ----------


def _addition(n: Note, log: TurnLog) -> Addition | None:
    if log.confirmed:
        return None
    if log.answer_to:
        # 물음에 답하는 차례는 보태지 않는다. 다만 아무 실마리도 없으면("뭐 할 수 있어?") 무엇을 생각하는지 묻는다
        return None if has_clue(n) else Addition(fact="어떤 제품이나 방향을 생각하는지 묻는다", sentence=P.ASK_PRODUCT,
                                                  ask=True)
    if log.concepts_changed:
        return Addition(fact="고칠 점을 예(이름, 용량, 가격)와 함께 말해 주면 바꾸겠다고 한다(묻지 않는다. 확정은 기획자가 정한다)",
                        sentence="고칠 점(이름, 용량, 가격)을 말씀해 주시면 바꿀게요.")
    if log.note_changed and not log.ideas_changed:
        name = {"product": "제품", "target": "마실 사람", "occasion": "마시는 때"}[log.note_changed[0]]
        return Addition(fact=f"{name}{josa(name, '이/가')} 바뀌었으니 아이디어를 다시 낼지 닫힌 물음으로 묻는다",
                        sentence="바뀐 내용으로 아이디어를 다시 낼까요?", ask=True)
    if log.thought_added and not log.ideas_changed:
        return Addition(fact="이 방향으로 아이디어를 낼지 닫힌 물음으로 묻는다(\"이 방향으로 아이디어를 낼까요?\")",
                        sentence="이 방향으로 아이디어를 낼까요?", ask=True)
    if log.ideas_changed:
        if log.ideas_again:
            return Addition(fact="바꾸고 싶은 점을 예(맛, 용기, 가격)와 함께 말해 주면 고치겠다고 한다(묻지 않는다)",
                            sentence="바꾸고 싶은 점(맛, 용기, 가격)을 말씀해 주시면 고칠게요.")
        return Addition(fact="마음에 드는 것을 골라 컨셉으로 만들지 닫힌 물음으로 묻는다(\"마음에 드는 것을 골라 컨셉으로 만들어 볼까요?\")",
                        sentence="마음에 드는 것을 골라 컨셉으로 만들어 볼까요?", ask=True)
    if not has_clue(n):
        return Addition(fact="어떤 제품이나 방향을 생각하는지 묻는다", sentence=P.ASK_PRODUCT, ask=True)
    if not n.ideas:
        who = next((f for f in log.founds if f.tool == "who" and "group" in f.extra), None)
        if who and not n.target.value:
            g = who.extra["group"].label
            return Addition(fact=f"{g} 쪽으로 아이디어를 내 보자고 권한다(권하는 것이지 요구가 아니다)",
                            sentence=f"{g} 쪽으로 아이디어를 내 볼까요?", ask=True)
        return Addition(fact="아이디어를 내 보자고 권한다", sentence="아이디어부터 내 볼까요?", ask=True)
    return None


# ---------- 말하기 ----------


def _pick_found(n: Note, log: TurnLog) -> Found | None:
    """찾아본 것 가운데 말할 것 하나. 물음에 답할 때는 처음 찾은 것. 아니면 아직 말하지 않은 것 가운데
    기획자의 생각과 이어지는 것(시간대) 먼저, 그다음 읽기가 고른 차례. 웹 소식은 조사에서 찾은 것이 없을 때만."""
    cands = [f for f in log.founds if f.fact]
    warning = next((f for f in cands if f.tool == "research" and f.key not in n.said), None)
    if warning:
        return warning
    if log.answer_to:
        return cands[0] if cands else None
    fresh = [f for f in cands if f.key not in n.said]
    if not fresh:
        return None
    if n.thoughts:
        tied = [f for f in fresh if f.tool == "when" and ":" in f.key]
        if tied:
            return tied[0]
    record = [f for f in fresh if f.origin != "web"]
    if record:
        return record[0]
    claim = voice.pick_claim([web.Claim(f.text, f.source, f.url or "", f.date, f.note) for f in fresh])
    return next((f for f in fresh if claim and f.text == claim.text), None)


async def _speak(n: Note, log: TurnLog) -> Say:
    found = _pick_found(n, log)
    if log.ideas_changed and found is not None and found.tool != "research":
        found = None  # 아이디어를 낸 차례는 한 일과 다음 할 일만 말한다(찾아본 것은 카드에 있다)
    context = []
    if log.answer_to:
        context = [summary(n, with_board=True)] + [f"{e['text']} (출처: {e['source']})" for e in n.evidence]
        context += [f.fact for f in log.founds if f.fact]
    turn = voice.open_turn(product=n.product.value or "", received=log.received, found=found,
                           addition=log.addition, thoughts=n.thoughts, answer_to=log.answer_to, context=context,
                           said_before=n.said_before)
    out = await voice.speak(turn)
    if found is not None:
        n.said.add(found.key)
    text = out.text
    if found and found.tool == "research" and any(term not in text for term in found.extra["required"]):
        text = turn.fallback
    n.remember_say(text)
    return Say(text=text)


# ---------- 추천받기 ----------


async def _recommend(n: Note, act: str) -> AsyncIterator[Any]:
    yield Activity(id=act, label=P.ACT_LOOK, status="running")
    n.recs = consumer.recommend()
    seen = {(e["text"], e["source"]) for e in n.evidence}
    for r in n.recs:
        if (r.text, r.source) in seen:  # 추천받기를 다시 눌러도 같은 항목을 또 쌓지 않는다
            continue
        item = {"id": f"ev-{len(n.evidence) + 1}", "origin": r.origin, "text": r.text, "source": r.source}
        if r.note:
            item["note"] = r.note
        n.evidence.append(item)
    yield evidence_card(n)
    out = await voice.speak(voice.recommend_turn(n.recs))
    n.remember_say(out.text)
    yield Activity(id=act, label=P.ACT_LOOK, status="done")
    yield Say(text=out.text)
    offer = Choices(id=n.next_id("pick-start"), kind="single", options=[Option(id=r.id, label=r.product) for r in n.recs])
    n.last_offer = offer
    yield offer
