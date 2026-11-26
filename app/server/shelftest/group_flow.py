"""대화에 매대 테스트의 정성 인터뷰와 발언을 연결한다."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Any

from agent import improve, machine
from agent import phrases as P
from agent.improve_suggestions import hypothesis
from agent.note import Note
from events import Card, Choices, ChilseongEvent, Confirm, ConfirmButton, ConfirmRow, Option, Say, Stage
from shelftest import group, group_dialogue, group_setup, interview, store
from tools.shelf_items import carbonation

_METHODS = {"one": "1:1 인터뷰", "fgi": "집단 심층 인터뷰(FGI)", "fgd": "집단 토론(FGD)"}
_ROUTES = {"plans": (2,), "method": (4,), "confirm": (4,), "edit": (2,), "open": (2, 3), "one": (4,), "reopen": (3,), "quote": (4,), "condition": (5,)}
_CHOICE_PREFIX = f"{P.GROUP_TO}:"
_GROUP_SIZE = (5, 6)


def owned_target(n: Note, chat_id: str, run_id: str) -> dict | None:
    """대화 노트가 컨셉과 연결한 원래 타깃 테스트만 사용한다."""
    meta = store.load_meta(run_id) if store.valid_id(run_id) else None
    if not meta or meta.get("id") != run_id or meta.get("chat_id") != chat_id:
        return None
    cid = meta.get("concept_id")
    snapshot = meta.get("concept") or {}
    if (not cid or n.runs.get(cid) != run_id or not n.concept(cid) or snapshot.get("id") != cid
            or meta.get("mode", "target") != "target" or meta.get("change") or meta.get("base_run_id")):
        return None
    return meta


def _matches_board(n: Note, board: dict, meta: dict, *, selected: bool = True) -> bool:
    spec = machine.shelf_spec(meta["chat_id"], n, board, board_target=selected)
    saved = improve.Base.of(meta["concept"])
    features = spec.features if meta.get("concept_prompt_version") else saved.features
    return saved == improve.Base(spec.name.strip(), spec.container, spec.volume, spec.price, spec.promo or None, features)


def _latest_board(n: Note, meta: dict) -> bool:
    board = n.concept(meta["concept_id"])
    if _matches_board(n, board, meta):
        return True
    adopted = board.get("_adopted_improvement") or {}
    if adopted.get("base_run") != meta["id"] or not store.valid_id(adopted.get("run_id")):
        return False
    variant = store.load_meta(adopted["run_id"])
    return bool(variant and variant.get("base_run_id") == meta["id"] and variant.get("chat_id") == meta["chat_id"]
                and variant.get("concept_id") == meta["concept_id"] and variant.get("status") == "done"
                and _matches_board(n, board, variant, selected=False))


def _question(payload: dict, hint: str) -> dict | None:
    questions = payload["questions"]
    exact = group_setup.resolve_question(payload, hint)
    if exact:
        return exact
    label = hint.removeprefix("barrier:")
    if label and hint.startswith("barrier:"):
        return next((q for q in questions if label in q["basis"] or label in q["text"]), None)
    if hint == "own":
        return next((q for q in questions if "자사" in q["basis"] or "자사" in q["text"]), None)
    return None


def _card(payload: dict, *, question: dict | None = None, session: dict | None = None) -> Card:
    view = ("setup" if session is None else "conclusion" if session["status"] == "done" else "room")
    data = {**payload, "view": view, "demo": False}
    if session is not None:
        if session["mode"] == "fgi" and session["status"] == "done":
            session = {**session, "findings": {**session["findings"], "independent": group_dialogue.independent_answers(session["turns"])}}
        data.update(session=session, selected_question_id=session["question_id"])
    elif question:
        data["selected_question_id"] = question["id"]
    return Card(id=f"group-{payload['run_id']}", kind="group", stage="improve", title="인터뷰 준비" if view == "setup" else P.GROUP_TITLE,
                status="ready", payload=data)


def saved_turn(run_id: str, session: dict, turn_id: str, *,
               visitors: dict[str, interview.Visitor] | None = None) -> tuple[dict, dict] | None:
    """저장된 발언 ID와 화자가 해당 실행에 실제 동석한 방문과 일치해야 한다."""
    if session.get("status") != "done":
        return None
    turns = [turn for turn in session["turns"] if turn["id"] == turn_id]
    if len(turns) != 1:
        return None
    turn = turns[0]
    guests = [guest for guest in session["participants"] if guest["id"] == turn["person"]]
    if len(guests) != 1 or not (turn.get("text") or "").strip():
        return None
    visitor_id = guests[0]["id"]
    visitor = interview.find(run_id, visitor_id) if visitors is None else visitors.get(visitor_id)
    if visitor is None or visitor.who != guests[0]["who"] or interview.check(turn["text"], visitor):
        return None
    return turn, guests[0]


def plan_for(n: Note, run_id: str, concept_id: str) -> dict:
    current = n.improve or {}
    plan = current if current.get("base_run") == run_id else (current.get("boards") or {}).get(run_id) or {}
    return plan if plan.get("base_run") == run_id and plan.get("concept_id") == concept_id else {}


def _choice_id(*ids: str) -> str:
    return _CHOICE_PREFIX + json.dumps(ids, ensure_ascii=False, separators=(",", ":"))


def invitation(view: dict, plan: dict) -> tuple[str, Choices] | None:
    """원래 매대 결과가 뒷받침하는 인터뷰 질문만 대화에 제안한다."""
    if any(item.get("run_id") or any(e.get("quote_id") for e in item.get("evidence", []))
           for item in plan["items"]):
        return None
    reasons, options = [], []
    for action in (view.get("brief") or {}).get("actions", []):
        command = action["do"]
        if command.get("to") == P.GROUP_TO and action.get("reason"):
            label = "왜 자사 제품에서 옮겨 왔는지 묻기" if command["ids"][-1] == "own" else "왜 망설였는지 묻기"
            command_run = command["ids"][1]
            reasons.append(action["reason"])
            options.append(Option(id=_choice_id(*command["ids"]), label=label))
    if not options:
        return None
    options.append(Option(id=_choice_id("edit", command_run), label="질문 직접 쓰기"))
    options.append(Option(id=_choice_id("plans", command_run), label="매대 결과로 개선안 보기"))
    return " ".join(reasons) + "\n\n개선안을 시험하기 전에 가상 손님에게 무엇을 더 물어볼까요?", Choices(
        id=P.GROUP_TO, kind="single", options=options)


def _route(ids: list[str]) -> list[str]:
    if len(ids) == 1 and ids[0].startswith(_CHOICE_PREFIX):
        try:
            selected = json.loads(ids[0][len(_CHOICE_PREFIX):])
        except ValueError:
            return []
        if (isinstance(selected, list) and all(isinstance(i, str) for i in selected)
                and selected and selected[0] in ("reopen", "condition", "start", "open", "method", "confirm", "edit", "plans")):
            return selected
        return []
    return ids if not ids or ids[0] != "condition" else []


def _conditions(base: improve.Base, text: str, features_shown: bool) -> tuple[dict, list[str]]:
    """발언에 방향이 드러난 조건을 모으고, 질문이 필요하면 골라 볼 값을 만든다."""
    values = {
        "price": {"price": (base.price - 1) // 100 * 100},
        "larger": {"volume": base.volume + 50}, "smaller": {"volume": base.volume - 50},
        "promo": {"promo": "2+1" if base.promo == "1+1" else "1+1"},
    }
    for container in improve.CHANGE_CONTAINERS:
        values[f"container:{container}"] = {"container": container}
    if features_shown:
        form, flavor = base.features.get("form", ""), base.features.get("flavor", "")
        if carbonation(form) is True:
            values.update(still={"form": "무탄산"}, light_fizz={"form": "약함"})
        elif carbonation(form) is False:
            values["fizz"] = {"form": "탄산"}
        values["appeal"] = {"appeal": f"{flavor} · {base.volume}ml" if flavor else f"{base.volume}ml {base.container}"}
        if flavor:
            values.update(sweet={"flavor": f"단맛을 줄인 {flavor}"}, mild={"flavor": f"향을 줄인 {flavor}"})
    values = {key: value for key, value in values.items()
              if improve.diff(base, value) and not improve.check_values(base, value, price_step=True)}
    prices = re.findall(r"(?<![\d,])(\d+(?:,\d{3})*)\s*원\s*(?:대|이하|[이가]?(?:면|라면|이면| 정도| 좋))", text)
    if len(prices) == 1 and "price" in values:
        price = {"price": int(prices[0].replace(",", ""))}
        if price["price"] < base.price and not improve.check_values(base, price, price_step=True):
            values["price"] = price

    cues = {
        "price": r"비싸(?!지\s*않)|비쌌|가격.{0,12}(?:부담|낮|내리)|저렴|값.{0,10}(?:부담|낮)",
        "larger": r"용량.{0,8}(?:작|적|늘)|양이.{0,5}(?:적|작)|더 큰 (?:용량|병|캔)",
        "smaller": r"용량.{0,8}(?:크|많|줄)|양이.{0,5}(?:많|크)|(?:작은|적은) 용량",
        "promo": r"행사.{0,9}(?:있|하면|붙)|할인.{0,8}(?:있|하면|되)|1\+1|2\+1",
        "still": r"탄산(?:을)?\s*(?:빼|없애)|(?:무탄산|비탄산|탄산(?:이)?\s*없).{0,12}(?:좋|고르|집|낫|편|이라면|으면)",
        "light_fizz": r"탄산.{0,9}(?:세|강하|강한|강할|약하|줄)|톡.{0,4}쏘.{0,8}부담",
        "fizz": r"탄산(?:이)?\s*(?:있었으면|있으면|있다면|없어서 아쉽)|탄산을\s*넣",
        "sweet": r"(?:덜|너무)\s*달|단맛.{0,8}(?:줄|덜|강)|달 것 같.{0,12}(?:부담|고르지)",
        "mild": r"향.{0,8}(?:세|강하|강한|강할|줄)|(?:진한|강한) 향",
        "appeal": r"(?:어떤|무슨)\s*(?:제품|음료|맛)(?:인지|일지)\s*(?:잘\s*)?모르|표기.{0,8}(?:분명|모르|알기)",
    }
    for container in improve.CHANGE_CONTAINERS:
        cues[f"container:{container}"] = rf"{container}(?:이었|였|이|가|라면|면|로).{{0,10}}(?:좋|편|고르|집|낫)"
    matches = [key for key in values if key in cues and re.search(cues[key], text)]
    if prices and "price" in values and "price" not in matches:
        matches.append("price")
    return values, matches


def _choice_label(key: str) -> str:
    if key.startswith("container:"):
        return P.group_container_choice(key.split(":", 1)[1])
    return P.GROUP_CHANGE_CHOICES[key]


def _quote(n: Note, meta: dict, session: dict, turn_id: str, choice: str | None) -> list[ChilseongEvent]:
    run_id, cid = meta["id"], meta["concept_id"]
    found = saved_turn(run_id, session, turn_id)
    if found is None:
        return machine._end(n, P.GROUP_NO_SESSION, None)
    turn, guest = found
    evidence = {"origin": "record", "text": turn["text"], "session_id": session["id"], "quote_id": turn["id"]}
    plan = plan_for(n, run_id, cid)
    current = n.improve or {}
    if not plan and (current.get("base_run") == run_id or run_id in (current.get("boards") or {})):
        return machine._end(n, P.GROUP_NO_RUN, None)
    if any(evidence in item.get("evidence", []) for item in plan.get("items", [])):
        machine._improve_state(n, run_id, cid)
        return [Stage(current="improve"), machine.improve_card(n), *machine._end(n, P.GROUP_QUOTE_ALREADY, None)]
    if plan.get("adopted_item_id"):
        return machine._end(n, P.GROUP_QUOTE_CLOSED, None)

    base = improve.Base.of(meta["concept"])
    values, matches = _conditions(base, turn["text"], bool(meta.get("concept_prompt_version")))
    offered = matches if len(matches) > 1 else [i for i in ("price", "smaller", "larger", "appeal", "promo") if i in values]
    if choice is None and len(matches) == 1:
        choice = matches[0]
    elif choice is None:
        options = [Option(id=_choice_id("condition", run_id, session["id"], turn_id, key),
                          label=_choice_label(key), note=improve.change_text(base, values[key])) for key in offered]
        return machine._end(n, P.GROUP_QUOTE_CHOICE, Choices(id=P.GROUP_TO, kind="single", options=options))
    elif choice not in offered or len(matches) == 1:
        return machine._end(n, P.GROUP_NO_CHOICE, None)

    plan = machine._improve_state(n, run_id, cid)
    condition = values[choice]
    item = next((entry for entry in plan["items"] if entry["values"] == condition), None)
    if item is None:
        reason = P.group_quote_reason(guest["who"], improve.before_after(base, condition)[1])
        item = machine._add_item(plan, base, condition, reason, hypothesis=hypothesis(condition), evidence=[evidence])
    else:
        item.setdefault("evidence", []).append(evidence)
    plan["focus_id"] = item["id"]
    card = machine.improve_card(n)
    label = "두 가격을 함께 테스트하기" if item.get("price_sweep") else f"{item['change']} 테스트하기"
    offer = Choices(id=f"{P.IMPROVE_RUN_TO}:{run_id}", kind="single", options=[Option(id=item["id"], label=label)])
    return [Stage(current="improve"), card, *machine._end(n, f"{P.GROUP_QUOTE_SAVED} {item['change']} 안이에요. {item.get('hypothesis') or hypothesis(condition)}", offer)]


async def _discuss(n: Note, payload: dict, question_id: str, mode: str, participants: list[str]) -> AsyncIterator[ChilseongEvent]:
    yield Stage(current="improve")
    session = None
    async for session in group.discuss(payload["run_id"], question_id, mode, participants):
        yield _card(payload, session=session)
    ending = P.GROUP_DONE if session and session["status"] == "done" else P.GROUP_ERROR
    offer = machine.result_offer(n, payload["run_id"]) if session and session["status"] == "done" else None
    for event in machine._end(n, ending, offer):
        yield event


def typed_plan(n: Note, text: str) -> list[str] | None:
    plan = n.interview_plan
    if not plan:
        return None
    run, question = plan["run"], plan.get("question")
    words = text.strip()
    compact = words.lower().replace(" ", "")
    if plan.get("mode") and compact in ("네", "예", "확정", "시작", "시작해줘", "이대로시작", "확정하고시작하기"):
        return ["confirm", run, question, plan["mode"]]
    if compact in ("다시", "수정", "질문바꾸기", "다시정하기"):
        return ["edit", run]
    if question and not words.endswith(("?", "？")):
        for mode, cues in (("one", ("1:1", "일대일")), ("fgi", ("fgi", "심층", "한명씩")), ("fgd", ("fgd", "토론"))):
            if any(cue in compact for cue in cues):
                return ["method", run, question, mode]
    if words and (not question or words.endswith(("?", "？"))):
        return ["open", run, "custom:" + words]
    return None


def _confirm_plan(n: Note, run: str, question: dict, mode: str, people: list[str]) -> list[ChilseongEvent]:
    n.interview = None
    n.interview_plan = {"run": run, "question": question["id"], "mode": mode, "people": people}
    rows = [ConfirmRow(label="질문", value=question["text"]), ConfirmRow(label="방식", value=_METHODS[mode]),
            ConfirmRow(label="참석자", value=f"가상 소비자 {len(people)}명")]
    confirm = Confirm(id=P.GROUP_TO, title="인터뷰 계획", rows=rows,
                      confirm=ConfirmButton(id=_choice_id("confirm", run, question["id"], mode), label="확정하고 시작하기"),
                      cancel=ConfirmButton(id=_choice_id("edit", run), label="다시 정하기"))
    return machine._end(n, "이 질문과 방식으로 인터뷰를 시작할까요?", confirm)


def _plan_turn(n: Note, payload: dict, ids: list[str]) -> list[ChilseongEvent]:
    action, run = ids[:2]
    question = _question(payload, ids[2]) if len(ids) > 2 else None
    plan = n.interview_plan or {}
    guests = payload["suggested"]
    modes = list(_METHODS) if len(guests) in _GROUP_SIZE else ["one"]
    if action == "method":
        mode = ids[3]
        if not question or plan.get("run") != run or plan.get("question") != question["id"] or mode not in modes:
            return [Say(text=P.GROUP_NO_CHOICE)]
        people = [question.get("visitor") or guests[0]] if mode == "one" and guests else guests
        if not people:
            return [Say(text=P.GROUP_NO_RUN)]
        return _confirm_plan(n, run, question, mode, people)
    n.interview = None
    n.interview_plan = {"run": run, "question": question["id"] if question else None}
    if question:
        prompt = f"질문은 “{question['text']}”예요. 어떤 방식으로 들어볼까요?"
        options = [Option(id=_choice_id("method", run, question["id"], mode), label=_METHODS[mode]) for mode in modes]
        options.append(Option(id=_choice_id("edit", run), label="질문 바꾸기"))
    else:
        prompt = "가상 소비자에게 무엇을 물어볼까요? 질문을 고르거나 직접 적어 주세요."
        options = [Option(id=_choice_id("open", run, q["id"]), label=q["text"]) for q in payload["questions"]]
        options += [Option(id=_choice_id("reopen", run, s["id"]), label=P.group_reopen(s["mode"]), note=s["question"])
                    for s in reversed(group.completed(run))]
    return [Stage(current="improve"), _card(payload, question=question),
            *machine._end(n, prompt, Choices(id=P.GROUP_TO, kind="single", options=options))]


def individual_card(iv: dict) -> Card:
    person = iv["participant"]
    return Card(id=f"group-{iv['run_id']}", kind="group", stage="improve", title="1:1 인터뷰", status="ready",
                payload={"demo": False, "view": "individual", "run_id": iv["run_id"], "concept": iv["concept"],
                         "questions": [], "candidates": [person], "suggested": [],
                         "individual": {"question": iv["question"], "qa": iv["qa"]}})


async def handle(n: Note, conv_id: str, ids: list[str], text: str) -> AsyncIterator[ChilseongEvent]:
    """실제 매대와 연결된 질문, 참석자, 인터뷰 기록만 사용한다."""
    ids = _route(ids)
    action, run_id = (ids + ["", ""])[:2]
    if (action == "start" and len(ids) < 5) or (action != "start" and len(ids) not in _ROUTES.get(action, ())):
        yield Say(text=P.GROUP_NO_CHOICE)
        return
    meta = owned_target(n, conv_id, run_id)
    if meta is None or not _latest_board(n, meta):
        yield Say(text=P.GROUP_NO_RUN)
        return
    if action == "plans":
        from agent.steps import ReadTask
        n.interview = n.interview_plan = None
        log = machine.TurnLog(text=text, ids=[run_id], conv_id=conv_id)
        async for event in machine.h_improve(n, log, n.next_id("work"), ReadTask(do="improve", ids=[run_id]), None):
            yield event
        return
    setup = group.setup(run_id)
    if not setup:
        yield Say(text=P.GROUP_NO_RUN)
        return
    payload = {key: setup[key] for key in ("concept", "questions", "candidates", "suggested")}
    payload["run_id"] = run_id

    if action in ("open", "edit", "method"):
        for event in _plan_turn(n, payload, ids):
            yield event
        return
    confirmed = action == "confirm"
    if confirmed:
        plan = n.interview_plan or {}
        if (run_id, ids[2], ids[3]) != (plan.get("run"), plan.get("question"), plan.get("mode")):
            yield Say(text=P.GROUP_NO_CHOICE)
            return
        mode = plan["mode"]
        action = "one" if mode == "one" else "start"
        ids = [action, run_id, ids[2], *([] if mode == "one" else [mode]), *plan["people"]]
    if action in ("reopen", "quote", "condition"):
        session = group.get_session(run_id, ids[2])
        if not session or session.get("id") != ids[2]:
            yield Say(text=P.GROUP_NO_SESSION)
            return
        n.interview = n.interview_plan = None
        if action == "reopen":
            if session["status"] == "running":
                participants = [guest["id"] for guest in session["participants"]]
                async for event in _discuss(n, payload, session["question_id"], session["mode"], participants):
                    yield event
            else:
                yield Stage(current="improve")
                yield _card(payload, session=session)
        else:
            for event in _quote(n, meta, session, ids[3], ids[4] if action == "condition" else None):
                yield event
        return

    question = group_setup.resolve_question(payload, ids[2])
    participants = ids[3:] if action == "one" else ids[4:]
    candidates = {c["id"] for c in payload["candidates"]}
    if not question or len(participants) != len(set(participants)) or not candidates.issuperset(participants):
        yield Say(text=P.GROUP_NO_CHOICE)
        return
    mode = "one" if action == "one" else ids[3]
    if action != "one" and (mode not in P.GROUP_METHODS or len(participants) not in _GROUP_SIZE):
        yield Say(text=P.GROUP_NO_CHOICE)
        return
    if not confirmed:
        for event in _confirm_plan(n, run_id, question, mode, participants):
            yield event
        return
    n.interview_plan = None
    if action == "one":
        called = machine._call_visitor(n, conv_id, [run_id, participants[0]])
        if n.interview is not None:
            person = next(p for p in payload["candidates"] if p["id"] == participants[0])
            n.interview.update(participant=person, concept=payload["concept"], question=question["text"])
            yield Stage(current="improve")
            yield individual_card(n.interview)
        for event in called:
            if n.interview is None or not isinstance(event, Choices):
                yield event
        if n.interview is not None:
            async for event in machine._interview_turn(n, conv_id, question["text"], []):
                yield event
        return

    n.interview = None
    async for event in _discuss(n, payload, question["id"], mode, participants):
        yield event
