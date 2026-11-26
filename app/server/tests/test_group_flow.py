"""가짜 응답기로 매대 결과에서 인터뷰·개선안·결과 보고서까지 이어 간다."""

import asyncio
import json
from copy import deepcopy

import pytest

from agent import diagnose, improve, improve_compare, machine, persist, proposal, proposal_group, result_brief
from agent import phrases as P
from agent.note import Note
from export_aisdk import ui_parts
from shelftest import group, group_flow, method, runner, store
from test_improve_w7 import card, engine, turn

CHAT = "chat-111111111111"
OTHER = "chat-222222222222"
PRICE_BARRIER = "가격이 비쌈"


@pytest.fixture
def tried(engine):
    concept = {"id": "a", "name": "견본 감귤 음료", "price": "1,800원", "pack": "500ml 페트", "_container": "페트",
               "_volume": 500, "_flavor": "감귤 맛", "_carb": "보통", "headline": "식사와 함께", "points": []}
    note = machine.CONVS[CHAT] = Note(concepts=[concept], confirmed=True, shelf_kind="탄산")

    async def run():
        spec = machine.shelf_spec(CHAT, note, concept)
        spec.total = 12
        run_id = runner.create(spec)
        await runner._run(run_id)
        return run_id

    run_id = asyncio.run(run())
    note.last_run = note.runs[concept["id"]] = run_id
    rows = store.answers(run_id)
    original = store.load_meta(run_id)
    for row in rows:
        if row.get("cond") == method.CONCEPT and row["product"] != original["line"]:
            row["barriers"] = [PRICE_BARRIER]
    store._answers_path(run_id).unlink()
    for row in rows:
        store.append_answer(run_id, row)
    return run_id


def ask(ids=(), text=P.BTN_ASK_GROUP, chat=CHAT):
    return turn(chat, text, ids, P.GROUP_TO if ids else None)


def approved(ids):
    prompt = ask(ids)[-1]
    assert prompt.t == "confirm"
    return [prompt.confirm.id]


def setup(run_id):
    opened = ask(["open", run_id, f"barrier:{PRICE_BARRIER}"])
    payload = card(opened, "group")
    assert payload["demo"] is False and payload["view"] == "setup"
    assert payload["selected_question_id"] == "barrier"
    return payload


def test_result_opens_group_without_changing_eligibility_or_counts():
    view = {"concept": {"name": "견본"}, "who": {"label": "전체"}}
    result = {"n": 20, "picked": 10, "rank": 1, "products": 5,
              "from": {"own": [{"name": "견본 자사", "count": 3}], "rival": [{"name": "견본 타사", "count": 7}]},
              "barriers": [{"label": "맛이 끌리지 않음", "count": 8}]}
    people = [result_brief.Visitor("a", "가상 소비자 가", [], True, True),
              result_brief.Visitor("b", "가상 소비자 나", ["맛이 끌리지 않음"], False, False)]
    ctx = result_brief.Ctx("run-000000000001", view, result, visitors=people)
    barrier, own, report = result_brief.collect_actions(ctx)
    assert barrier["reason"] == P.act_barrier("맛이 끌리지 않음", 8)
    assert own["reason"] == P.act_own(10, 3)
    assert [a["label"] for a in (barrier, own)] == [P.BTN_ASK_GROUP] * 2
    assert barrier["do"] == {"say": P.BTN_ASK_GROUP, "to": P.GROUP_TO,
                             "ids": ["open", ctx.run_id, "barrier:맛이 끌리지 않음"]}
    assert own["do"]["ids"] == ["open", ctx.run_id, "own"]
    assert report["id"] == "report"
    said, topics = group_flow.invitation({"brief": {"actions": [barrier, own, report]}}, {"items": []})
    assert barrier["reason"] in said and own["reason"] in said
    assert [group_flow._route([option.id]) for option in topics.options] == [barrier["do"]["ids"], own["do"]["ids"], ["edit", ctx.run_id], ["plans", ctx.run_id]]
    result["from"]["own"][0]["count"] = 2
    result["from"]["rival"][0]["count"] = 8
    assert result_brief.rule_own(ctx) is None


def test_selected_question_reaches_one_shopper_and_preserves_followup(engine, tried):
    payload = setup(tried)
    assert card(ask(), "group")["questions"] == payload["questions"]
    shopper = next(p for p in payload["candidates"] if not p["picked"])
    question = next(q for q in payload["questions"] if q["id"] == "barrier")
    denied = ask(["one", tried, question["id"], "not-a-visit"])
    assert denied[0].text == P.GROUP_NO_CHOICE

    events = ask(approved(["one", tried, question["id"], shopper["id"]]), text="이 손님에게 물어봐요")
    choices = [e for e in events if e.t in ("choices", "actions", "confirm")]
    assert choices == [events[-1]] and choices[0].kind == "single"
    assert events[-2].speaker.label == shopper["who"]
    call = next(call for call in reversed(engine.calls) if call["task"] == "interview")
    assert call["user"].endswith(question["text"])
    assert machine.CONVS[CHAT].interview["qa"][0][0] == question["text"]
    follow = turn(CHAT, P.INTERVIEW_ASKS[0][1], [P.INTERVIEW_ASKS[0][0]])
    assert len(card(follow, "group")["individual"]["qa"]) == 2
    next_person = turn(CHAT, P.INTERVIEW_NEXT[1], [P.INTERVIEW_NEXT[0]])
    assert card(next_person, "group")["candidates"][0]["id"] != shopper["id"]
    new_plan = next(o for o in next_person[-1].options if o.label == P.BTN_OTHER_INTERVIEW)
    finished = turn(CHAT, P.INTERVIEW_END[1], [P.INTERVIEW_END[0]])[-1]
    restart = next(a for a in finished.actions if a.label == P.BTN_OTHER_INTERVIEW)
    assert restart.id == new_plan.id
    assert any(a.id == machine.IMPROVE for a in finished.actions)
    machine.CONVS[CHAT].last_run = "run-000000000000"
    planning = turn(CHAT, restart.label, [restart.id], finished.id)
    assert card(planning, "group")["view"] == "setup"
    assert machine.CONVS[CHAT].interview_plan == {"run": tried, "question": None}
    machine.CONVS[OTHER] = persist.from_dict(persist.to_dict(machine.CONVS[CHAT]))
    assert ask(["open", tried], chat=OTHER)[0].text == P.GROUP_NO_RUN


def test_group_record_survives_reload_and_powers_pair_and_report(engine, tried, monkeypatch):
    opened = ask(["open", tried, f"barrier:{PRICE_BARRIER}"])
    payload = card(opened, "group")
    assert any(e.t == "stage" and e.current == "improve" for e in opened)
    selected = payload["suggested"]
    start = next(o for o in opened[-1].options if o.label == "집단 토론(FGD)")
    confirm = approved([start.id])
    assert not any(c["task"] == "group_turn" for c in engine.calls)
    machine.CONVS[CHAT] = persist.from_dict(persist.to_dict(machine.CONVS[CHAT]))
    events = ask(confirm)
    cards = [e for e in events if e.t == "card"]
    assert any(a.id == f"{machine.GROUP_OPEN}:{tried}" for a in events[-1].actions)
    assert len({c.id for c in cards}) == 1
    snapshots = [c.payload["session"] for c in cards]
    session = snapshots[-1]
    assert session["status"] == "done" and cards[-1].payload["view"] == "conclusion"
    assert [len(s["turns"]) for s in snapshots[:-1]] == list(range(1 + len(session["turns"])))
    assert {t["person"] for t in session["turns"]} == set(selected)
    calls = [c for c in engine.calls if c["task"] == "group_turn"]
    assert len(calls) == session["calls"] == len(selected) * session["rounds"]
    parts = ui_parts([e.model_dump(exclude_none=True) for e in events], None)
    assert [p["data"]["payload"]["session"] for p in parts if p["type"] == "data-card"] == [session]

    machine.CONVS[CHAT] = note = persist.from_dict(persist.to_dict(machine.CONVS[CHAT]))
    reopened = card(ask(["reopen", tried, session["id"]]), "group")
    assert reopened["session"] == group.get_session(tried, session["id"]) == session
    via_choice = next(e for e in ask(["open", tried]) if e.t == "choices")
    assert card(ask([next(o.id for o in via_choice.options if group_flow._route([o.id])[0] == "reopen")]), "group")["session"] == session
    assert not any(e.t == "card" for e in ask(["quote", tried, session["id"], "different-turn"]))
    quote = next(t for t in session["turns"] if "가격이 낮아지면" in t["text"])
    mismatched = deepcopy(session)
    next(p for p in mismatched["participants"] if p["id"] == quote["person"])["who"] = "다른 별명"
    assert group_flow.saved_turn(tried, mismatched, quote["id"]) is None
    clicked = ["quote", tried, session["id"], quote["id"]]
    quote_events = ask(clicked)
    plan_card = card(quote_events)
    item = next(it for it in plan_card["items"] if it["id"] == plan_card["focus_id"])
    test_offer = quote_events[-1]
    evidence = {"origin": "record", "session_id": session["id"], "quote_id": quote["id"], "text": quote["text"]}
    assert item["kind"] == "price" and item["evidence"] == [evidence]
    assert note.improve["items"][0]["values"] == {"price": 1700}
    assert card(ask(clicked))["items"] == [item]

    variant_id = card(turn(CHAT, test_offer.options[0].label, [test_offer.options[0].id], test_offer.id))["items"][0]["run_id"]
    asyncio.run(runner._run(variant_id))
    pair = improve_compare.for_runs(tried, variant_id)
    assert pair and pair["n"] == 12
    adopted = card(turn(CHAT, "채택할게요", [tried, item["id"]], "w7-adopt"))
    assert adopted["adopted_item_id"] == item["id"]
    assert card(ask(clicked))["adopted_item_id"] == item["id"]
    assert note.concepts[0]["_adopted_improvement"]["evidence"] == [evidence]

    prior_voice = {"factor": "매대 선택 발언", "who": "견본 가상 소비자", "quote": "견본 응답이에요."}
    prior_compare = {"title": "기존 대조", "lines": ["견본 대조 결과"]}
    monkeypatch.setenv("AX_REPORT_MIN", "1")
    paper = proposal.test_section(note, note.concepts[0], {"id": CHAT})
    paper["evidence"]["voices"].insert(0, prior_voice)
    paper["evidence"]["compare"] = [prior_compare]
    proposal_group.add(note, note.concepts[0], paper)
    proposal_group.add(note, note.concepts[0], paper)
    voices = paper["evidence"]["voices"]
    assert voices[0] == prior_voice
    assert sum(v["quote"] == quote["text"] for v in voices) == 1
    for label in ("모인 의견", "갈린 의견", "바뀐 생각"):
        assert any(label in v["factor"] for v in voices)
    assert paper["evidence"]["compare"] == [prior_compare]
    row = paper["evidence"]["variants"][1]
    assert row["adopted"] and row["pair"] == pair
    lines = row["line"].splitlines()
    assert "12명 기준" in lines[1]
    assert lines[2] == (
        f"두 안 모두 선택 {pair['both']}명, 개선안에서만 선택 {pair['gained']}명, "
        f"원래 안에서만 선택 {pair['lost']}명, 두 안 모두 미선택 {pair['neither']}명"
    )
    assert f"{pair['low_pp']:+.1f}~{pair['high_pp']:+.1f}%p" in lines[3]
    assert "판정" in lines[4] and quote["text"] in lines[-1]


def test_ambiguous_quote_asks_for_one_condition_and_rejects_stale_board(engine, tried):
    original = store.load_meta(tried)
    note = machine.CONVS[CHAT]
    empty = {"chat_id": CHAT, "evidence": {}}
    proposal_group.add(note, note.concepts[0], empty)
    assert empty["evidence"] == {}
    payload = setup(tried)
    text = "오늘 어떻게 고를지는 조금 더 생각해 볼래요."

    def answer(_system, user, _schema):
        return {"text": text, "choice": json.loads(user)["participant"]["choice"], "reply_to": None,
                "reply_quote": None, "stance": None, "position": None, "position_quote": None}

    engine.answers["group_turn"] = answer
    cards = [e for e in ask(approved(["start", tried, payload["selected_question_id"], "fgi", *payload["suggested"]])) if e.t == "card"]
    session = cards[-1].payload["session"]
    assert session["status"] == "done" and len(session["turns"]) == len(payload["suggested"])
    quote_ids = ["quote", tried, session["id"], session["turns"][0]["id"]]
    request = ask(quote_ids)
    assert note.improve is None
    chooser = request[-1]
    assert chooser.t == "choices" and chooser.kind == "single"
    choice = next(o for o in chooser.options if o.label == P.GROUP_CHANGE_CHOICES["smaller"])
    assert card(ask([choice.id]))["items"][0]["evidence"][0]["text"] == text
    assert note.improve["items"][0]["values"] == {"volume": original["concept"]["volume"] - 50}
    note.concepts[0]["price"] = "2,000원"
    assert ask(quote_ids)[0].text == P.GROUP_NO_RUN
    note.concepts[0]["price"] = "1,800원"
    note.runs["a"] = "run-000000000002"
    assert ask(["reopen", tried, session["id"]])[0].text == P.GROUP_NO_RUN
    note.runs["a"] = tried
    foreign = {"chat_id": OTHER, "evidence": {}}
    proposal_group.add(note, note.concepts[0], foreign)
    assert foreign["evidence"] == {}


def test_adopts_quote_improvement_after_testing_only_the_selected_diagnosis(engine, tried, monkeypatch):
    note = machine.CONVS[CHAT]
    concept = note.concepts[0]
    concept["_diagnosis"] = {"choice": "fix", "signature": diagnose._signature(concept),
                             "approved": {"values": {"price": 1600}}}
    assert ask(["open", tried])[0].text == P.GROUP_NO_RUN

    async def run():
        spec = machine.shelf_spec(CHAT, note, concept, board_target=True)
        assert spec.price == 1600
        spec.total = 12
        run_id = runner.create(spec)
        await runner._run(run_id)
        return run_id

    fixed_run = asyncio.run(run())
    note.last_run = note.runs[concept["id"]] = fixed_run
    machine.CONVS[CHAT] = note = persist.from_dict(persist.to_dict(note))
    payload = card(ask(["open", fixed_run]), "group")
    assert payload["run_id"] == fixed_run
    assert note.concepts[0]["price"] == "1,800원"

    quote_text = "작은 용량이라면 비교해 볼래요."

    def answer(_system, user, _schema):
        return {"text": quote_text, "choice": json.loads(user)["participant"]["choice"], "reply_to": None,
                "reply_quote": None, "stance": None, "position": None, "position_quote": None}

    engine.answers["group_turn"] = answer
    events = ask(approved(["start", fixed_run, payload["questions"][0]["id"], "fgi", *payload["suggested"]]))
    session = [e.payload["session"] for e in events if e.t == "card"][-1]
    assert session["status"] == "done"
    quote_ids = ["quote", fixed_run, session["id"], session["turns"][0]["id"]]
    item = card(ask(quote_ids))["items"][0]
    assert note.improve["items"][0]["values"] == {"volume": 450}
    rerun = card(turn(CHAT, "이 안만 테스트해 주세요", [fixed_run, item["id"]], "improve"))
    variant_id = rerun["items"][0]["run_id"]
    original, variant = store.load_meta(fixed_run), store.load_meta(variant_id)
    assert original["concept"]["price"] == variant["concept"]["price"] == 1600
    assert variant["concept"]["volume"] == 450
    asyncio.run(runner._run(variant_id))

    adopted = card(turn(CHAT, "채택할게요", [fixed_run, item["id"]], "w7-adopt"))
    assert adopted["adopted_item_id"] == item["id"]
    concept = note.concepts[0]
    assert concept["price"] == "1,600원" and concept["_volume"] == 450
    assert concept["_adopted_improvement"]["evidence"][0]["text"] == quote_text
    assert store.load_meta(fixed_run) == original
    assert card(ask(quote_ids))["adopted_item_id"] == item["id"]

    monkeypatch.setenv("AX_REPORT_MIN", "1")
    report = proposal.test_section(note, concept, {"id": CHAT})
    assert report["evidence"]["compare"] == []
    assert any(row.get("adopted") and quote_text in row["line"] for row in report["evidence"]["variants"])
    assert any(voice["quote"] == quote_text for voice in report["evidence"]["voices"])


def test_reopen_resubscribes_to_running_session_and_returns_completed_immediately(engine, tried, monkeypatch):
    payload = setup(tried)
    selected = payload["suggested"]
    confirmed = approved(["start", tried, payload["selected_question_id"], "fgi", *selected])
    ask_fake = engine.ask

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def gated(task, *args, **kwargs):
            if task == "group_turn":
                entered.set()
                await release.wait()
            return await ask_fake(task, *args, **kwargs)

        monkeypatch.setattr(engine, "ask", gated)

        def request(ids):
            return machine.turn(CHAT, "인터뷰 기록 다시 열기", ids, 2, reply_to=P.GROUP_TO)

        started = request(confirmed)
        assert (await anext(started)).current == "improve"
        first = await anext(started)
        session_id = first.payload["session"]["id"]
        await asyncio.wait_for(entered.wait(), timeout=2)
        await started.aclose()
        assert group.get_session(tried, session_id)["status"] == "running"

        try:
            reopened = request(["reopen", tried, session_id])
            assert (await anext(reopened)).current == "improve"
            current = await anext(reopened)
            assert current.id == first.id
            assert current.payload["session"]["id"] == session_id
            assert current.payload["session"]["status"] == "running"
        finally:
            release.set()
        later = [event async for event in reopened if event.t == "card"]
        assert {event.id for event in later} == {first.id}
        assert [len(event.payload["session"]["turns"]) for event in later[:-1]] == list(range(1, len(selected) + 1))
        done = later[-1].payload["session"]
        assert done["status"] == "done" and done["calls"] == len(selected)
        assert {s["id"] for s in group.completed(tried)} == {session_id}

        completed = [event async for event in request(["reopen", tried, session_id])]
        assert [event.t for event in completed] == ["stage", "card"]
        assert completed[-1].payload["session"] == done
        assert len([call for call in engine.calls if call["task"] == "group_turn"]) == len(selected)

    asyncio.run(scenario())


@pytest.mark.parametrize(("text", "value"), [
    ("가격이 비싸서 1,550원이면 다음에는 다시 볼래요.", {"price": 1550}),
    ("탄산을 없애면 다음에는 비교해 볼래요.", {"form": "무탄산"}),
    ("단맛을 덜 낸 안이라면 비교해 볼래요.", {"flavor": "단맛을 줄인 감귤 맛"}),
    ("작은 용량이라면 비교해 볼래요.", {"volume": 450}),
])
def test_changed_condition_follows_the_quote(text, value):
    base = improve.Base("견본", "페트", 500, 1800, features={"flavor": "감귤 맛", "form": "보통"})
    conditions, matches = group_flow._conditions(base, text, True)
    assert [conditions[key] for key in matches] == [value]

def test_typed_question_and_method_can_change_before_confirmation(engine, tried):
    ask(["edit", tried])
    question = "어떤 표시를 먼저 보셨어요?"
    methods = ask(text=question)[-1]
    assert len(methods.options) == 4
    plan = ask(text="일대일로 들어볼래")[-1]
    assert [row.value for row in plan.rows] == [question, "1:1 인터뷰", "가상 소비자 1명"]
    ask([plan.cancel.id])
    assert ask([plan.confirm.id])[0].text == P.GROUP_NO_CHOICE
    assert not any(c["task"] in ("group_turn", "interview") for c in engine.calls)
    ask(text=question)
    ask(text="FGI")
    events = ask(text="시작")
    assert card(events, "group")["session"]["question"] == question


def test_interview_preparation_precedes_proposals(engine, tried):
    rows = store.answers(tried)
    store._answers_path(tried).unlink()
    for row in rows:
        if row.get("barriers") == [PRICE_BARRIER]:
            row["barriers"] = [improve.FIRST_SEEN]
        store.append_answer(tried, row)
    events = turn(CHAT, "개선안 테스트 준비하기", [f"{machine.PREPARE_IMPROVE}:{tried}"])
    assert card(events, "group")["view"] == "setup"
    assert not any(e.t == "card" and e.kind == "improve" for e in events)
    assert not machine.CONVS[CHAT].improve["items"]
    option = next(o for o in events[-1].options if group_flow._route([o.id])[0] == "plans")
    proposals = ask([option.id], text=option.label)
    assert card(proposals, "improve")["items"]
    assert machine.CONVS[CHAT].interview_plan is None
