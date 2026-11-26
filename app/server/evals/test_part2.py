"""2부의 뒤쪽(지시서 17): 한 손님에게 묻기, 개선안 테스트. fake 어댑터만 쓴다."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from agent import explore, improve, machine
from agent import persist
from agent import phrases as P
from evals.test_open import Chat, calls, card, fake, ideas_now, read_ans, reply_of, says, task, with_ideas  # noqa: F401
from llm.base import LLMError
from shelftest import runner, store
from tools.consumer import Group


@pytest.fixture(autouse=True)
def small_tests(monkeypatch):
    monkeypatch.setenv("AX_SHELF_TOTAL", "20")


def after_test(chat: Chat, *, legacy: bool = False) -> tuple[str, dict]:
    """컨셉 하나를 매대에 올려 끝까지 돌리고 결과를 본 대화. (테스트 id, 결과)"""
    t = with_ideas(chat)
    a = ideas_now(t)[0]["id"]
    chat.send("A로 컨셉 만들자", read=read_ans(task("concepts", ids=[a])))
    note = machine.CONVS[chat.id]
    note.group, note.occasion_code = Group(age="19-29", label="20대"), "D7"
    chat.send(P.BTN_SHELF)
    chat.send("바로 타깃 테스트", ["explore-skip"])
    # 아래에서 직접 실행한다. 옛 실행은 첫 응답부터 당시의 질문 방식으로 만든다.
    with patch.object(runner, "_start", lambda run_id: None):
        t = chat.send(P.BTN_SHELF_START, ["shelf-start"])
    run_id = card(t, "shelf-run").payload["run_id"]
    if legacy:
        meta = store.load_meta(run_id)
        for key in ("concept_prompt_version", "shopper_adapter", "base_run_id"):
            meta.pop(key, None)
        for key in ("flavor", "form", "appeal", "kind", "sugar_caffeine"):
            meta["concept"].pop(key, None)
        store.save_meta(meta)
    asyncio.run(runner._run(run_id))
    t = chat.send(P.BTN_RESULT)
    assert [x.id for x in reply_of(t).actions] == ["improve", "report"]
    return run_id, runner.view(run_id)


@pytest.mark.parametrize("keep_original", [True, False])
def test_explore_restore_choose_target_and_review(fake, monkeypatch, keep_original):
    monkeypatch.setenv("AX_EXPLORE_PER_CELL", "2")
    monkeypatch.setattr(runner, "_start", lambda run_id: None)
    chat = Chat(fake)
    idea_id = ideas_now(with_ideas(chat))[0]["id"]
    chat.send("컨셉 만들자", read=read_ans(task("concepts", ids=[idea_id])))
    note = machine.CONVS[chat.id]
    note.group = Group(age="19-29", sex="여자")
    note.concepts[0].update(name="밀키스 화채", pack="250ml 슬림캔", price="1,200원",
                            _container="슬림캔", _volume=250, _storage="상온")
    entry = chat.send(P.BTN_SHELF)
    assert "19~59세 소비자 16명" in says(entry)
    start = reply_of(entry).actions[0]
    t = chat.send(start.label, [start.id])
    run = card(t, "explore").payload["run_id"]
    asyncio.run(runner._run(run))
    options = reply_of(chat.send("탐색 결과 보기", ["explore-result", run])).options
    machine.CONVS[chat.id] = persist.from_dict(persist.to_dict(note))
    if keep_original:
        chosen = next(o for o in options if o.id.endswith("/board"))
    else:
        ages = reply_of(chat.send(options[-1].label, [options[-1].id])).options
        age = next(o for o in ages if o.label == "40~49세")
        sexes = reply_of(chat.send(age.label, [age.id])).options
        chosen = next(o for o in sexes if o.label == "40~49세 남성")
    t = chat.send(chosen.label, [chosen.id])
    target = card(t, "shelf-run").payload["run_id"]
    asyncio.run(runner._run(target))
    meta = store.load_meta(target)
    assert meta["target"] == ({"age": "19-29", "sex": "여자"} if keep_original else {"age": "40-49", "sex": "남자"})
    assert meta["explore_id"] == run and "탐색 응답 2명 중" in meta["target_basis"]
    assert {p["uuid"] for p in meta["participants"]}.isdisjoint(p["uuid"] for p in store.load_meta(run)["participants"])
    assert runner.view(target)["asked"] == 20 and card(chat.send(P.BTN_RESULT), "result")
    saved = machine.CONVS[chat.id]
    # 같은 컨셉에 직접 POST /api/runs로 개선안을 보내도 탐색 뒤 고른 타깃을 쓴다.
    spec = machine.shelf_spec(chat.id, saved, saved.concepts[0])
    changed = runner.create(runner.apply_change(spec, {"price": 1100}))
    assert store.load_meta(changed)["participants"] == meta["participants"]


@pytest.mark.parametrize("picked,others,suggested,first_choice", [
    (12, 8, False, "board"),       # 가장 많이 골랐어도 차이가 뚜렷하지 않으면 기존 타깃
    (35, 2, True, "40-49/남자"),    # 차이가 뚜렷하면 반응이 높았던 손님
    (8, 8, False, "board"),        # 공동 1위
    (0, 0, False, "board"),
])
def test_explore_message_recommends_a_target_before_asking(picked, others, suggested, first_choice):
    from agent.note import Note

    spec = runner.Spec("chat", "a", "밀키스 화채", "슬림캔", 250, 1200, age="19-29", sex="여자", total=300)
    cells = []
    for age, sex in explore.CELLS:
        k = picked if (age, sex) == ("40-49", "남자") else others
        cells.append({"age": age, "sex": sex, "n": 40, "picked": k, "rate": 100 * k / 40})
    study = {"cells": cells, "overlap": not suggested, "suggested": {"age": "40-49", "sex": "남자"} if suggested else None}
    events = explore._offer_targets(Note(), "r", study, spec)
    text = says(events)
    options = reply_of(events).options
    assert text.endswith("300명에게 해보길 추천해요. 누구에게 물어볼까요?")
    assert options[0].id == f"explore-target/r/{first_choice}" and options[0].label.endswith("(추천)")
    if picked > others:
        assert text.startswith("40~49세 남성") and f"40명 중 {picked}명" in text
        assert ("다른 그룹보다 선택률이 높아요" if suggested else "차이가 뚜렷하지 않아요") in text
    elif picked:
        assert "가장 높은 선택률" in text
    else:
        assert "고른 사람은 없었어요" in text


# ---------- A. 한 손님에게 묻기 ----------


def test_call_ask_and_end_a_visitor(fake):
    chat = Chat(fake)
    run_id, v = after_test(chat)
    q = (v["result"]["quotes"]["passed"] or v["result"]["quotes"]["picked"])[0]
    reads = len(calls(fake, "read"))
    t = chat.send(f"{q['who']} 손님에게 묻기", [run_id, q["visitor"]], to="visitor")
    assert says(t).endswith("손님을 모셨어요. 궁금한 것을 물어보세요.")
    chips = reply_of(t)
    assert chips.t == "choices" and [o.label for o in chips.options] == [
        "얼마면 구매하시겠어요?", "어떤 점이 바뀌면 구매하시겠어요?", "평소에는 어떤 음료를 구매하시나요?",
        "다른 손님 인터뷰하기", "인터뷰 마치기"]
    note = machine.CONVS[chat.id]
    assert note.interview["run_id"] == run_id and note.interview["visitor"] == q["visitor"]
    # 칩으로 물으면 그 손님이 답한다(읽기를 거치지 않는다, 다른 화자)
    t = chat.send("얼마면 구매하시겠어요?", ["ask-price"])
    shopper = [e for e in t if e.t == "say"]
    assert len(shopper) == 1 and shopper[0].speaker.kind == "shopper" and shopper[0].speaker.label == q["who"]
    assert shopper[0].text == "1,500원이면 한번 집어 볼 것 같아요."
    assert [o.id for o in reply_of(t).options] == ["ask-change", "ask-usual", "interview-next", "interview-end"]
    # 직접 쓴 말도 그 손님에게 간다. 지금까지 묻고 답한 것을 함께 넘긴다
    t = chat.send("왜 안 집으셨어요?")
    assert [e.speaker.kind for e in t if e.t == "say"] == ["shopper"]
    assert len(calls(fake, "read")) == reads  # 읽기를 거치지 않았다
    ask = calls(fake, "interview")[-1]
    assert "[지금까지 묻고 답한 것]" in ask["user"] and "얼마면 구매하시겠어요?" in ask["user"]
    assert "[당신]" in ask["user"] and "[지금의 상황]" in ask["user"] and "[음료 매대]" not in ask["user"]
    assert ask["model"] == runner.shopper_model()
    # 이름(손님 서술 맨 앞의 이름)은 화면으로 내보내지 않는다
    assert all(e.speaker is None or "씨" not in e.speaker.label for e in t if e.t == "say")
    # 인터뷰 마치기: 칠성이가 돌아오고 원래의 버튼을 다시 낸다
    t = chat.send("인터뷰 마치기", ["interview-end"])
    assert says(t) == P.INTERVIEW_BYE and all(e.speaker is None for e in t if e.t == "say")
    assert [x.id for x in reply_of(t).actions] == ["improve", f"{machine.GROUP_OPEN}:{run_id}", "report"]
    assert note.interview is None


def test_end_by_words_and_unknown_visitor(fake):
    chat = Chat(fake)
    run_id, v = after_test(chat)
    t = chat.send("손님에게 묻기", [run_id, "T999"], to="visitor")
    assert says(t) == P.INTERVIEW_NOT_FOUND and machine.CONVS[chat.id].interview is None
    q = v["result"]["quotes"]["passed"][0]
    chat.send("묻기", [run_id, q["visitor"]], to="visitor")
    t = chat.send("이제 그만 물어볼게")
    assert says(t) == P.INTERVIEW_BYE
    chat.send("묻기", [run_id, q["visitor"]], to="visitor")
    t = chat.send("인터뷰 끝낼게요")
    assert says(t) == P.INTERVIEW_BYE


def _called(chat: Chat) -> str:
    return machine.CONVS[chat.id].interview["visitor"]


def test_next_shopper_is_someone_new_then_cycles(fake):
    """지시서 18의 C: "손님 인터뷰하기"를 다시 누르거나 "다른 손님 인터뷰하기"를 누르면 아직 안 부른 손님이 온다."""
    chat = Chat(fake)
    run_id, v = after_test(chat)
    pool = machine._shopper_pool(run_id)
    quotes = [q["visitor"] for q in v["result"]["quotes"]["picked"] + v["result"]["quotes"]["passed"]]
    assert pool[:len(quotes)] == quotes and len(pool) == len(set(pool)) > 2  # 손님의 말 먼저, 그다음 답의 손님
    reads = len(calls(fake, "read"))
    t = chat.send(P.BTN_ASK_SHOPPER, ["ask-shopper"])
    first = _called(chat)
    assert first == pool[0] and says(t).endswith("손님을 모셨어요. 궁금한 것을 물어보세요.")
    chat.send(P.INTERVIEW_END[1], [P.INTERVIEW_END[0]])
    chat.send(P.BTN_ASK_SHOPPER, ["ask-shopper"])  # 다시 눌러도 같은 손님이 오지 않는다
    assert _called(chat) == pool[1]
    seen = [first, pool[1]]
    for _ in range(len(pool) - 2):
        t = chat.send(P.INTERVIEW_NEXT[1], [P.INTERVIEW_NEXT[0]])
        assert says(t).endswith("손님을 모셨어요. 궁금한 것을 물어보세요.") and reply_of(t).t == "choices"
        seen.append(_called(chat))
    assert seen == pool and len(calls(fake, "read")) == reads  # 읽기를 거치지 않았다
    # 모두 불렀으면 처음부터 다시 돈다
    chat.send(P.INTERVIEW_NEXT[1], [P.INTERVIEW_NEXT[0]])
    assert _called(chat) == pool[0]
    # 부른 손님은 대화 파일에도 남는다
    from agent import persist

    note = machine.CONVS[chat.id]
    assert persist.from_dict(persist.to_dict(note)).interviewed == note.interviewed == {run_id: [pool[0]]}
    assert persist.from_dict({k: v for k, v in persist.to_dict(note).items() if k != "interviewed"}).interviewed == {}


def test_card_call_counts_as_called(fake):
    """카드의 "이 손님 인터뷰하기"로 부른 손님도 부른 목록에 적어, 버튼으로 다시 부르지 않는다."""
    chat = Chat(fake)
    run_id, _ = after_test(chat)
    pool = machine._shopper_pool(run_id)
    chat.send("묻기", [run_id, pool[0]], to="visitor")
    chat.send(P.INTERVIEW_END[1], [P.INTERVIEW_END[0]])
    chat.send(P.BTN_ASK_SHOPPER, ["ask-shopper"])
    assert _called(chat) == pool[1]


def test_shopper_answer_is_checked(fake):
    chat = Chat(fake)
    run_id, v = after_test(chat)
    q = v["result"]["quotes"]["passed"][0]
    chat.send("묻기", [run_id, q["visitor"]], to="visitor")
    fake.answers["interview"] = [{"text": "마셔 보니 맛있었어요."}, {"text": "아직 안 마셔 봐서 모르겠어요."}]
    t = chat.send("맛은 어땠어요?")
    assert says(t) == "아직 안 마셔 봐서 모르겠어요."  # 마셔 본 듯한 말은 다시 쓰게 한다
    fake.answers["interview"] = [{"text": "마셔 봤는데 별로였어요."}, {"text": "AI라서 몰라요."}]
    t = chat.send("맛은요?")
    assert says(t) == "음, 그건 잘 모르겠어요."  # 두 번 걸리면 고정된 말
    fake.answers["interview"] = LLMError("x")
    t = chat.send("그럼요?")
    assert says(t) == "음, 그건 잘 모르겠어요."


def test_speaker_survives_saving():
    from events import Say, Speaker
    from export_aisdk import ui_parts

    ev = Say(text="안녕하세요", speaker=Speaker(kind="shopper", label="24세 여자, 대학생")).model_dump(exclude_none=True)
    parts = ui_parts([ev], None)
    assert parts[-1]["providerMetadata"] == {"chilseong": {"speaker": {"kind": "shopper", "label": "24세 여자, 대학생"}}}
    plain = ui_parts([Say(text="칠성이").model_dump(exclude_none=True)], None)
    assert "providerMetadata" not in plain[-1]


# ---------- B. 개선안 테스트 ----------


def test_legacy_improve_proposes_checked_changes(fake):
    chat = Chat(fake)
    run_id, v = after_test(chat, legacy=True)
    t = chat.send(P.BTN_IMPROVE, ["improve"])
    assert any(e.t == "stage" and e.current == "improve" for e in t)
    c = card(t, "improve")
    assert c.payload["base_run"] == run_id
    items = c.payload["items"]
    price = v["concept"]["price"]
    assert [i["id"] for i in items] == ["A", "B"]
    assert items[0]["change"] == f"가격 {price:,}원 → {price - 200:,}원"
    assert items[1]["change"] == "행사 없음 → 1+1"
    # 지시서 19: 타일이 그리는 종류와 앞뒤 값
    assert [(i["kind"], i["before"], i["after"]) for i in items] == [
        ("price", f"{price:,}원", f"{price - 200:,}원"), ("promo", "행사 없음", "1+1")]
    assert all("run_id" not in i for i in items)
    actions = reply_of(t).actions
    assert [x.id for x in actions] == [f"try-candidate:{run_id}:A", f"choose-candidate:{run_id}", "report"]
    assert items[0]["after"] in says(t) and says(t).count("?") == 1
    assert "•" not in says(t) and items[1]["after"] not in says(t)
    menu = chat.send(actions[1].label, [actions[1].id], to=reply_of(t).id)
    assert [o.id for o in reply_of(menu).options] == ["A", "B"]
    selected = chat.send("1+1", ["B"], to=f"compare-candidate:{run_id}")
    assert card(selected, "improve").payload["focus_id"] == "B" and "1+1" in says(selected)
    assert all("run_id" not in it for it in card(selected, "improve").payload["items"])
    again = chat.send(f"{items[0]['after']} 보여줘")
    assert card(again, "improve").payload["focus_id"] == "A"
    started = chat.send("이 안으로 테스트해줘")
    updated = card(started, "improve").payload
    assert updated["items"][0].get("run_id") and not updated["items"][1].get("run_id")


def test_workbench_price_edit_reuses_candidate_without_starting_test(fake):
    chat = Chat(fake)
    run, view = after_test(chat, legacy=True)
    chat.send(P.BTN_IMPROVE, ["improve"])
    raw = '{"price":"%s"}' % f"{view['concept']['price'] - 300:,}원"
    invalid = chat.send("가격 바꾸기", ["A", '{"price":"-200"}'], to=f"edit-candidate:{run}")
    assert not any(e.t == "card" for e in invalid)
    for _ in range(2):
        changed = chat.send("이 값으로 비교", ["A", raw], to=f"edit-candidate:{run}")
        payload = card(changed, "improve").payload
        assert payload["focus_id"] == "C" and len(payload["items"]) == 3
        assert payload["items"][0]["edit_values"]["price"] == view["concept"]["price"] - 200
        assert payload["items"][2]["edit_values"]["price"] == view["concept"]["price"] - 300
        assert all(not it.get("run_id") for it in payload["items"])
        assert payload["items"][2]["after"] in says(changed)


def test_legacy_improve_checks_and_falls_back_to_template(fake):
    chat = Chat(fake)
    run_id, v = after_test(chat, legacy=True)
    c = v["concept"]
    same = {"price": c["price"], "container": c["container"] if c["container"] in improve.CONTAINERS else "캔",
            "volume_ml": c["volume"], "name": c["name"], "promo": "없음"}
    bad = {"items": [
        {**same, "kind": "price", "price": c["price"] - 150, "reason": "가격이 걸린 손님이 3명이라 낮춰요."},  # 100원 단위가 아님
        {**same, "kind": "promo", "promo": "1+1", "reason": "손님 77명이 망설여서 붙여요."},  # 받지 않은 숫자
        {**same, "kind": "name", "name": "코카콜라 요거트", "reason": "이름이 걸린 손님이 1명이라 바꿔요."},  # 다른 회사 이름
    ]}
    fake.answers["improve"] = [bad, bad]
    t = chat.send("개선안 만들어 줘", read=read_ans(task("improve")))
    items = card(t, "improve").payload["items"]
    assert len(items) == 1  # 하나도 안 남아 글틀로 하나
    order = [b["label"] for b in v["result"]["barriers"] if b["label"] in (improve.FIRST_SEEN, improve.PRICEY, improve.PACK)]
    top = order[0] if order else None
    if top == improve.PRICEY:
        assert items[0]["change"].startswith("가격")
    elif top == improve.PACK:
        assert items[0]["change"].startswith("용기와 용량")
    else:
        assert items[0]["change"] == "행사 없음 → 1+1"
    assert len(calls(fake, "improve")) == 2  # 한 번 다시 쓰게 했다


def test_one_bad_item_is_rewritten_once():
    base = improve.Base("굿모닝", "병", 300, 2000)
    res = {"n": 20, "picked": 1, "rank": 9, "products": 56,
           "barriers": [{"label": "처음 보는 제품이라 망설여짐", "count": 17}], "views": []}
    _, allowed = improve.facts(base, res, "20대 손님")
    ok = improve.Idea(kind="price", price=1800, container="병", volume_ml=300, name="굿모닝", promo="없음",
                      reason="망설인 손님이 17명이라 200원 낮춰요.")
    assert improve._judge(base, ok, allowed) == ({"price": 1800}, [])
    pack = improve.Idea(kind="pack", price=2000, container="캔", volume_ml=333, name="굿모닝", promo="없음",
                        reason="망설인 손님이 17명이라 캔으로 바꿔요.")
    values, why = improve._judge(base, pack, allowed)
    assert values == {"container": "캔", "volume": 333} and why  # 333ml은 매대에 있을 법하지 않다
    assert not improve._judge(base, pack.model_copy(update={"volume_ml": 355}), allowed)[1]
    assert improve._judge(base, ok.model_copy(update={"reason": "많이들 망설여서요."}), allowed)[1]  # 숫자가 없다
    assert improve.check_values(base, {"container": "컵"})


def test_legacy_rerun_reuses_baselines_and_compares(fake):
    chat = Chat(fake)
    run_id, v = after_test(chat, legacy=True)
    chat.send(P.BTN_IMPROVE, ["improve"])
    before = len([c for c in fake.calls if c["task"] == "shopper"])
    t = chat.send("이 안으로 다시 묻기", ["A"], to="improve")
    item = card(t, "improve").payload["items"][0]
    new_run = item["run_id"]
    assert new_run != run_id and says(t) == P.improve_started(["가격 변경안"])
    meta = store.load_meta(new_run)
    assert meta["change"] == {"price": v["concept"]["price"] - 200} and meta["total"] == v["total"]
    asyncio.run(runner._run(new_run))
    asked = len([c for c in fake.calls if c["task"] == "shopper"]) - before
    assert asked == v["total"]  # 컨셉을 올린 매대만 다시 묻는다(컨셉이 없는 매대의 답은 다시 쓴다)
    assert sum(1 for r in store.answers(new_run) if r.get("reused")) == v["total"]
    assert store.load_meta(new_run)["requested"] == store.load_meta(run_id)["requested"]
    t = chat.send(P.BTN_IMPROVE_COMPARE, ["improve-compare"])
    r0, r1 = v["result"], runner.view(new_run)["result"]
    if improve.verdict(r0, r1) == "unclear":
        assert "오차 범위" in says(t)
    # 같은 안을 다시 누르면 새로 돌리지 않는다
    t = chat.send("이 안으로 다시 묻기", ["A"], to="improve")
    assert card(t, "improve").payload["items"][0]["run_id"] == new_run


def test_plan_names_follow_the_kind():
    """지시서 19의 B: 안의 이름은 바꾼 것으로. 같은 종류가 둘이면 뒤의 것에 숫자. 처음 안은 기존안."""
    base = improve.Base("굿모닝", "병", 300, 2000)
    items = [{"id": k, **improve.describe(base, v), "values": v} for k, v in
             [("A", {"price": 1800}), ("B", {"name": "굿모닝 유자"}), ("C", {"container": "캔", "volume": 355}),
              ("D", {"promo": "1+1"}), ("E", {"price": 1600})]]
    assert [improve.plan_name(items, it) for it in items] == [
        "가격 변경안", "제품명 변경안", "용기·용량 변경안", "행사 변경안", "가격 변경안 2"]
    assert improve.plan_name(items, None) == "기존안"
    assert [(it["kind"], it["before"], it["after"]) for it in items] == [
        ("price", "2,000원", "1,800원"), ("name", "굿모닝", "굿모닝 유자"), ("pack", "300ml 병", "355ml 캔"),
        ("promo", "행사 없음", "1+1"), ("price", "2,000원", "1,600원")]
    # 옛 노트의 항목(kind가 없음)도 값에서 이름을 정한다
    old = [{"id": "A", "values": {"promo": "2+1"}}, {"id": "B", "values": {"promo": "1+1"}}]
    assert [improve.plan_name(old, it) for it in old] == ["행사 변경안", "행사 변경안 2"]
    # 여럿을 바꾼 안(기획자가 직접 말함)은 앞의 것의 이름, 앞뒤 값은 쉼표로
    both = improve.describe(base, {"price": 1500, "promo": "1+1"})
    assert both["kind"] == "price" and both["before"] == "2,000원, 행사 없음" and both["after"] == "1,500원, 1+1"


def test_legacy_names_in_words_and_read(fake):
    """칠성이의 말과 읽기에 넘기는 개선안 표가 같은 이름을 쓰고, 읽기가 고른 improve_rerun으로 그 안을 돌린다."""
    chat = Chat(fake)
    chat_run, v = after_test(chat, legacy=True)
    chat.send(P.BTN_IMPROVE, ["improve"])
    ctx = machine._read_context(machine.CONVS["c1"])
    assert "- id A (가격 변경안): 가격" in ctx and "- id B (행사 변경안): 행사 없음 → 1+1 [아직 테스트 안 함]" in ctx
    t = chat.send("행사 변경안으로 테스트해 줘", read=read_ans(task("improve_rerun", ids=["B"])))
    items = card(t, "improve").payload["items"]
    assert says(t) == P.improve_started(["행사 변경안"]) and items[1]["run_id"] and "run_id" not in items[0]
    # 카드의 "남은 안 모두 테스트하기"는 읽지 않고 남은 안을 돌린다
    reads = len(calls(fake, "read"))
    t = chat.send(P.BTN_IMPROVE_ALL)
    assert len(calls(fake, "read")) == reads and says(t) == P.improve_started(["가격 변경안"])
    # 지시서 20의 A: 도는 동안에는 "변경안 결과 보기"를 내밀지 않는다(카드가 결과가 나오면 스스로 보낸다). 버튼도 내지 않는다
    assert reply_of(t) is None
    asyncio.run(runner._run(items[1]["run_id"]))
    # 카드가 스스로 보낸 말(metadata.reply {to: "auto", ids: []})도 읽지 않고 견준다
    t = chat.send(P.BTN_IMPROVE_COMPARE, to="auto")
    assert len(calls(fake, "read")) == reads
    assert "기존안" in says(t) and "고친 안" not in says(t) and "집" not in says(t)


def test_overlap_rule():
    a = {"picked": 4, "n": 100, "low": 1.6, "high": 9.8}
    b = {"picked": 6, "n": 100, "low": 2.8, "high": 12.5}
    c = {"picked": 30, "n": 100, "low": 21.9, "high": 39.6}
    assert improve.verdict(a, b) == "unclear" and improve.verdict(a, c) == "more" and improve.verdict(c, a) == "less"


def test_planner_says_the_change(fake):
    chat = Chat(fake)
    run_id, v = after_test(chat)
    t = chat.send("1,500원으로 해서 1+1 붙여서 다시 물어봐", read=read_ans(task("improve_run", text="1,500원으로 해서 1+1 붙여서 다시 물어봐")))
    items = card(t, "improve").payload["items"]
    assert items[-1]["change"] == f"가격 {v['concept']['price']:,}원 → 1,500원, 행사 없음 → 1+1"
    assert items[-1]["run_id"] and items[-1]["reason"] == P.IMPROVE_REASON_PLANNER
    assert store.load_meta(items[-1]["run_id"])["change"] == {"price": 1500, "promo": "1+1"}
    t = chat.send("150원으로 해서 다시 물어봐", read=read_ans(task("improve_run", text="150원으로 해서 다시 물어봐")))
    assert says(t) == P.IMPROVE_NOT_UNDERSTOOD  # 매대에 있을 법하지 않은 값


def test_improve_without_result(fake):
    chat = Chat(fake)
    with_ideas(chat)
    t = chat.send("개선안 만들어 줘", read=read_ans(task("improve")))
    assert says(t) == P.IMPROVE_NO_RESULT


def test_report_moves_stage_and_offers_download(fake):
    chat = Chat(fake)
    after_test(chat)
    t = chat.send(P.BTN_REPORT, ["report"])
    assert any(e.t == "stage" and e.current == "report" for e in t)
    assert says(t) == P.REPORT_READY and [x.id for x in reply_of(t).actions] == ["download"]


def test_report_button_after_improve_and_cancel(fake):
    """지시서 18의 D: 개선안을 돌리지 않아도, 시작 확인에서 그만둬도 결과 보고서로 갈 수 있다."""
    chat = Chat(fake)
    run_id, _ = after_test(chat)
    t = chat.send(P.BTN_IMPROVE, ["improve"])
    assert "report" in [x.id for x in reply_of(t).actions]
    t = chat.send("이 안으로 다시 묻기", ["A"], to="improve")
    assert reply_of(t) is None  # 개선안 테스트를 시작한 차례에는 버튼을 내지 않는다(카드가 결과가 나오면 스스로 보낸다)
    t = chat.send("1,500원으로 해서 다시 물어봐", read=read_ans(task("improve_run", text="1,500원으로 해서 다시 물어봐")))
    assert reply_of(t) is None
    # 다시 매대에 올리려다 그만두면 결과 보기와 결과 보고서를 낸다
    chat.send(P.BTN_SHELF)
    assert reply_of(chat.send("바로 타깃 테스트", ["explore-skip"])).t == "confirm"
    t = chat.send(P.BTN_SHELF_CANCEL, ["shelf-cancel"])
    assert says(t) == P.SHELF_CANCELLED
    assert [x.id for x in reply_of(t).actions] == ["show-result", "go-shelf", "report"]
    assert [x.label for x in reply_of(t).actions] == [P.BTN_RESULT, P.BTN_SHELF, P.BTN_REPORT]
    reads = len(calls(fake, "read"))
    t = chat.send(P.BTN_RESULT, ["show-result"])
    assert card(t, "result").payload == {"run_id": run_id} and len(calls(fake, "read")) == reads
    t = chat.send(P.BTN_REPORT, ["report"])
    assert says(t) == P.REPORT_READY


def test_small_test_does_not_promise_100(fake):
    assert "100명" not in P.shelf_started(20) and "100명" not in P.shelf_waiting(3, 20)
    assert "100명" in P.shelf_started(300)


def test_result_points_out_cannibalization():
    """구매한 손님의 절반 이상이 우리 제품에서 왔으면 걸린 점 대신 그것을 말한다."""
    from agent import machine, voice

    v = {"who": {"label": "20대 손님"}, "status": "done", "concept": {"name": "녹차"}, "asked": 182, "total": 182,
         "result": {"n": 182, "picked": 17, "products": 56, "rank": 3,
                    "from": {"rival": [{"name": "코카콜라 제로", "count": 2}],
                             "own": [{"name": "롯데 더하다 보리차", "count": 14}, {"name": "트레비", "count": 1}], "none": 0},
                    "barriers": [{"label": "늘 마시는 것이 있음", "count": 95}], "by_occasion": []}}
    bits, order, _ = machine._result_bits(v)
    turn = voice.result_turn(product="녹차", received=bits, order=order)
    assert "182명 중 17명이 녹차를 골랐고 56개 제품 가운데 3위예요" in turn.fallback
    assert "고른 17명 가운데 15명은 자사 제품(롯데 더하다 보리차)을 고르던 손님" in turn.fallback
    assert "늘 마시는 것이 있음" not in turn.fallback
    assert voice.check(turn.fallback, turn.facts) == []


def test_words_while_the_start_card_is_up_do_not_break(fake):
    """시작 확인 카드가 떠 있을 때 버튼 대신 말로 고쳐 달라고 해도 읽고 처리한다(확인 카드의 버튼을 읽기에 넘긴다)."""
    chat = Chat(fake)
    t = with_ideas(chat)
    a = ideas_now(t)[0]["id"]
    chat.send("A로 컨셉 만들자", read=read_ans(task("concepts", ids=[a])))
    note = machine.CONVS[chat.id]
    note.group, note.occasion_code = Group(age="19-29", label="20대"), "D7"
    chat.send(P.BTN_SHELF)
    t = chat.send("바로 타깃 테스트", ["explore-skip"])
    assert reply_of(t).t == "confirm"
    assert "'테스트 시작하기'(id shelf-start)" in machine.offer_lines(note.last_offer)
    cid = note.concepts[0]["id"]
    t = chat.send("가격은 2100원으로", read=read_ans(task("edit_concept", ids=[cid], text="가격은 2100원으로")))
    assert says(t)
