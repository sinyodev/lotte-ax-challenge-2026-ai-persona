"""지시서 33: 아이디어와 컨셉이 과제의 제품 사양(규격별 가격, 유통기한, 열량, 출시, 채널)을 담는다."""

import asyncio
import copy
import re
from datetime import date

import pytest

from agent import idea_spec, machine, steps
from events import ConceptItem, IdeaItem
from llm.base import set_llm
from llm.fake import FakeLLM
from onsite import concepts

TODAY = date(2026, 11, 20)


def task(do, slot="", value="", ids=None, text=""):
    return {"do": do, "slot": slot, "value": value, "ids": ids or [], "text": text}


def read_ans(*tasks, **kw):
    out = {"tasks": list(tasks), "lookups": [], "product_kind": "없음", "shelf_kind": "없음", "target_age": "없음",
           "target_sex": "없음", "occasion_code": "없음"}
    out.update(kw)
    return out


@pytest.fixture
def fake():
    f = FakeLLM()
    set_llm(f)
    return f


def send(fake, conv, n, text, read):
    fake.answers["read"] = [read]

    async def run():
        return [e async for e in machine.turn(conv, text, [], n, today=TODAY)]

    out = asyncio.run(run())
    fake.answers.pop("read", None)
    return out


def card(events, kind):
    cards = [e for e in events if e.t == "card" and e.kind == kind and e.status == "ready"]
    return cards[-1].payload if cards else None


def start(fake, conv):
    send(fake, conv, 1, "탄산 신제품 검토해 보고 싶어",
         read_ans(task("note", "product", "탄산"), product_kind="탄산음료", shelf_kind="탄산"))


def test_concepts_carry_shelf_life_and_kcal_from_the_task_sheet():
    milkis = concepts.match("밀키스 화채")
    assert [(v["shelf_life_months"], v["kcal"]) for v in milkis["variants"]] == [(12, 130), (9, 260)]
    assert concepts.match("레쓰비 프리즈")["variants"][0]["kcal"] == 100
    juicy = concepts.match("쥬시모먼트")["variants"][0]
    assert juicy["shelf_life_months"] is None and juicy["shelf_life_days"] == 45 and juicy["kcal"] is None
    assert concepts.match("  밀키스화채 여름판 ") is milkis  # 공백 무시, 이름을 담으면
    assert concepts.match("제주 말차 라떼") is None


def test_task_concept_name_alone_fills_the_spec_and_shelf_gets_first_variant(fake):
    conv = "spec-milkis"
    start(fake, conv)
    t = send(fake, conv, 2, "내 아이디어로 밀키스 화채", read_ans(task("my_idea", text="밀키스 화채")))
    # 11-25: 규격마다 카드 하나(슬림캔, PET). 이름·맛·설명은 같고 규격과 그 값만 다르다
    item, pet = [i for i in card(t, "ideas")["items"] if i["name"] == "밀키스 화채"]
    IdeaItem.model_validate(item)
    assert [v["label"] for v in item["variants"]] == ["슬림캔 250ml"]
    assert [v["label"] for v in pet["variants"]] == ["PET 500ml"] and pet["variants"][0]["price"] == 1800
    assert item["variants"][0] == {"label": "슬림캔 250ml", "volume_ml": 250, "price": 1200, "factory_price": 780,
                                   "shelf_life_months": 12, "kcal": 130}
    assert item["launch"] == "2027-05" and item["season"] == "5~9월 한정"
    assert item["channels"] == ["편의점", "대형마트·SSM", "온라인"] and item["shelf_variant"] == 0
    assert (item["line"], item["flavor"], item["features"]) == (pet["line"], pet["flavor"], pet["features"])
    assert not re.search(r"\d", item["line"])  # 한 줄 설명에 숫자를 되풀이하지 않는다
    idea = machine.CONVS[conv].idea(item["id"])
    assert (idea["_container"], idea["_volume"]) == ("캔", 250)
    assert (machine.CONVS[conv].idea(pet["id"])["_container"], machine.CONVS[conv].idea(pet["id"])["_volume"]) == ("페트", 500)

    t = send(fake, conv, 3, "밀키스 화채로 컨셉 만들자", read_ans(task("concepts", ids=[item["id"]])))
    c = next(x for x in card(t, "concepts")["items"] if x["id"] == item["id"])
    ConceptItem.model_validate(c)
    assert c["price"] == "1,200원" and len(c["variants"]) == 1 and c["shelf_variant"] == 0
    keys = [r["key"] for r in c["spec"]]
    assert "pack" not in keys and "price" not in keys and "channel" not in keys  # 표가 대신한다
    concept = machine.CONVS[conv].concept(item["id"])
    assert (concept["_container"], concept["_volume"], machine._price_won(concept["price"])) == ("캔", 250, 1200)


def test_planner_numbers_override_only_what_was_said():
    ans = steps.IdeaAnswer(name="밀키스 화채", flavor="수박", container="페트", volume_ml=500, features=["수박"],
                           line="수박화채 맛 밀키스", diff="여름",
                           variants=[steps.VariantAnswer(container="페트", volume_ml=500, price=1500, kcal=999)])
    spec = idea_spec.planner_spec("밀키스 화채", ans, "밀키스 화채, PET 500ml는 1,500원으로")
    pet = spec["variants"][1]
    assert pet["price"] == 1500  # 말한 값이 먼저
    assert pet["kcal"] == 260  # 말하지 않은 999는 버리고 과제의 값을 둔다
    assert spec["variants"][0]["price"] == 1200


def test_other_name_with_one_pack_stays_one_line_and_no_numbers_are_invented(fake):
    conv = "spec-matcha"
    start(fake, conv)
    t = send(fake, conv, 2, "내 아이디어로 제주 말차 라떼 캔 250ml", read_ans(task("my_idea", text="제주 말차 라떼 캔 250ml")))
    item = next(i for i in card(t, "ideas")["items"] if "말차" in i["name"])
    assert item["pack"] == "캔 250ml"
    for k in ("variants", "launch", "season", "channels", "storage", "shelf_variant"):
        assert k not in item
    # 모델이 숫자를 지어내도 말에 없으면 버린다
    ans = steps.IdeaAnswer(name="제주 말차 라떼", flavor="말차", container="캔", volume_ml=250, features=["말차"],
                           line="말차 라떼", diff="말차",
                           variants=[steps.VariantAnswer(container="캔", volume_ml=250, price=1800, kcal=120)])
    spec = idea_spec.planner_spec("제주 말차 라떼", ans, "제주 말차 라떼 캔 250ml")
    assert spec["variants"] == []  # 규격 하나에 숫자가 없으면 표 없이 한 줄


def test_old_ideas_and_concepts_without_spec_still_render():
    old_idea = {"id": "a", "name": "보리 소다", "flavor": "보리", "pack": "캔 355ml", "features": ["구수함"],
                "line": "구수한 탄산", "diff": "곡물", "by": "chilseong", "_container": "캔", "_volume": 355}
    IdeaItem.model_validate(machine._idea_public(old_idea))
    assert idea_spec.public(old_idea) == {} and idea_spec.tested_line(old_idea) is None


def test_tested_line_names_the_tested_variant():
    c = {"variants": concepts.spec_of(concepts.match("밀키스 화채"))["variants"], "_shelf_variant": 0}
    assert idea_spec.tested_line(c) == "슬림캔 250ml로 테스트, PET 500ml도 있음"


def old_board(fake, conv):
    """옛 대화의 모양: 규격 둘이 한 아이디어와 한 컨셉의 variants에 든 것(11-25 전). 규격 바꾸기의 길을 지킨다."""
    start(fake, conv)
    t = send(fake, conv, 2, "내 아이디어로 밀키스 화채", read_ans(task("my_idea", text="밀키스 화채")))
    iid = card(t, "ideas")["items"][0]["id"]
    t = send(fake, conv, 3, "밀키스 화채로 컨셉 만들자", read_ans(task("concepts", ids=[iid])))
    n = machine.CONVS[conv]
    both = concepts.spec_of(concepts.match("밀키스 화채"))["variants"]
    n.ideas = [i for i in n.ideas if i["id"] == iid]
    n.ideas[0]["variants"] = copy.deepcopy(both)
    n.concept(iid)["variants"] = copy.deepcopy(both)
    return iid, t


def test_switching_the_shelf_variant_needs_no_model(fake):
    conv = "spec-switch"
    iid, _ = old_board(fake, conv)
    before = len(fake.calls)

    async def run(text, ids=(), to=None):
        return [e async for e in machine.turn(conv, text, list(ids), 4, today=TODAY, reply_to=to)]

    t = asyncio.run(run("PET 500ml를 매대에 올릴 규격으로 바꿔 줘"))
    assert [c["task"] for c in fake.calls[before:]] == []  # 모델을 부르지 않는다
    c = card(t, "concepts")["items"][0]
    assert c["shelf_variant"] == 1 and c["price"] == "1,800원"
    concept = machine.CONVS[conv].concept(iid)
    assert (concept["_container"], concept["_volume"]) == ("페트", 500)
    assert "PET 500ml" in " ".join(e.text for e in t if e.t == "say")
    # 카드의 줄을 누른 답(metadata.reply)으로도 바꾼다
    t = asyncio.run(run("슬림캔 250ml", [iid, "0"], machine.VARIANT_TO))
    assert card(t, "concepts")["items"][0]["shelf_variant"] == 0
    assert machine._price_won(machine.CONVS[conv].concept(iid)["price"]) == 1200
    # 보고서의 제품 개요는 테스트한 규격을 밝힌다(4절)
    from agent import proposal
    sp = proposal._spec(machine.CONVS[conv], machine.CONVS[conv].concept(iid))
    assert sp["pack"] == "슬림캔 250ml로 테스트, PET 500ml도 있음" and sp["price"] == "1,200원"
    assert sp["channel"] == "편의점, 대형마트·SSM, 온라인"


def test_task_concept_mark_carries_to_the_concept_and_the_diagnosis(fake):
    from agent import diagnose
    conv = "spec-task"
    start(fake, conv)
    t = send(fake, conv, 2, "내 아이디어로 밀키스 화채", read_ans(task("my_idea", text="밀키스 화채")))
    item = card(t, "ideas")["items"][0]
    assert item["flavor"] == "수박화채맛" and "_task_concept" not in item
    t = send(fake, conv, 3, "밀키스 화채로 컨셉 만들자", read_ans(task("concepts", ids=[item["id"]])))
    c = card(t, "concepts")["items"][0]
    assert c["name"] == "밀키스 화채"  # 가짜 응답기는 "컨셉 a"를 내지만 과제 컨셉은 아이디어의 이름 그대로
    assert {"key": "storage", "label": "보관", "value": "상온"} in c["spec"]
    concept = machine.CONVS[conv].concept(item["id"])
    assert concept["_task_concept"] == "milkis-hwachae"
    concept["name"] = "밀키스 화채 썸머"  # 이름이 바뀌어도 과제 컨셉으로 찾는다
    assert diagnose._official(concept)["id"] == "milkis-hwachae"


def test_planner_flavor_wins_over_the_task_flavor():
    ans = steps.IdeaAnswer(name="밀키스 화채", flavor="복숭아", container="캔", volume_ml=250, features=["x"],
                           line="여름 밀키스", diff="여름")
    assert "_flavor" not in idea_spec.planner_spec("밀키스 화채", ans, "밀키스 화채를 복숭아 맛으로")
    assert idea_spec.planner_spec("밀키스 화채", ans, "밀키스 화채")["_flavor"] == "수박화채맛"


def test_variant_pick_is_locked_after_confirm(fake):
    conv = "spec-lock"
    iid, _ = old_board(fake, conv)
    t = send(fake, conv, 4, "이대로 확정", read_ans(task("confirm")))
    assert card(t, "concepts")["locked"] is True

    async def run():
        return [e async for e in machine.turn(conv, "x", [iid, "1"], 5, today=TODAY, reply_to=machine.VARIANT_TO)]

    asyncio.run(run())
    assert machine.CONVS[conv].concept(iid).get("_shelf_variant", 0) == 0


def test_switching_the_variant_keeps_the_open_actions(fake):
    conv = "spec-offer"
    iid, t = old_board(fake, conv)
    before = next(e for e in t if e.t == "actions")
    ids = [a.id for a in before.actions]
    assert "confirm-concepts" in ids

    async def run(n, ids_, text):
        return [e async for e in machine.turn(conv, text, ids_, n, today=TODAY, reply_to=machine.VARIANT_TO)]

    for n_user, k in ((4, "1"), (5, "1")):  # 바꾸기, 그리고 "이미 매대에 올릴 규격"
        t = asyncio.run(run(n_user, [iid, k], "PET 500ml"))
        again = next(e for e in t if e.t == "actions")
        assert [a.id for a in again.actions] == ids and [a.label for a in again.actions] == [a.label for a in before.actions]
    t = send(fake, conv, 6, "이 컨셉으로 확정하기", read_ans(task("confirm")))
    assert machine.CONVS[conv].confirmed


def test_vague_season_does_not_override_the_task_season():
    ans = steps.IdeaAnswer(name="밀키스 화채", flavor="수박", container="캔", volume_ml=250, features=["x"],
                           line="여름 밀키스", diff="여름", season="여름 한정", launch="내년 여름")
    spec = idea_spec.planner_spec("밀키스 화채", ans, "여름 한정 탄산음료 밀키스 화채")
    assert spec["season"] == "5~9월 한정" and spec["launch"] == "2027-05"
    ans = ans.model_copy(update={"season": "6~8월 한정", "launch": "2027-06"})
    spec = idea_spec.planner_spec("밀키스 화채", ans, "밀키스 화채, 2027년 6월 출시, 6~8월 한정")
    assert spec["season"] == "6~8월 한정" and spec["launch"] == "2027-06"


def test_meta_sentences_about_the_answer_form_are_dropped(fake):
    text = "밀키스에 여름철 화채의 풍미를 더한 점이 달라요. 용량 칸은 형식상 입력값이며 실제 규격은 미정이에요."
    assert idea_spec.clean_meta(text) == "밀키스에 여름철 화채의 풍미를 더한 점이 달라요."
    assert idea_spec.clean_meta("용량은 미정이에요.") == ""
    fake.answers["my_idea"] = [{"name": "밀키스 화채", "flavor": "수박화채", "container": "캔", "volume_ml": 250,
                                "features": ["수박"], "line": "수박화채 맛 밀키스예요. 용기 칸은 형식상 채웠어요.",
                                "diff": text}]
    conv = "spec-meta"
    start(fake, conv)
    t = send(fake, conv, 2, "내 아이디어로 밀키스 화채", read_ans(task("my_idea", text="밀키스 화채")))
    item = card(t, "ideas")["items"][0]
    assert item["line"] == "수박화채 맛 밀키스예요." and item["diff"] == "밀키스에 여름철 화채의 풍미를 더한 점이 달라요."
    prompt = next(c for c in fake.calls if c["task"] == "my_idea")
    assert "과제의 컨셉 '밀키스 화채'" in prompt["user"]


def test_number_points_are_dropped_not_fatal():
    a = steps.ConceptAnswer(idea_id="a", name="밀키스 화채", headline="여름 밥상에 시원한 한 캔", benefit="입안이 개운해요",
                            points=["수박화채 맛", "250mL 캔", "과일 일러스트"])
    steps._keep_points(a)
    assert a.points == ["수박화채 맛", "과일 일러스트"]
    b = steps.ConceptAnswer(idea_id="a", name="x", headline="h", benefit="b", points=["250mL 캔", "1,200원", "수박 맛"])
    with pytest.raises(ValueError):
        steps._keep_points(b)
    c = steps.ConceptAnswer(idea_id="a", name="x", headline="h", benefit="b", points=["당 0g", "0kcal", "수박 맛"])
    steps._keep_points(c)
    assert len(c.points) == 3  # 제로 표기는 그대로


def test_concept_board_survives_a_number_point(fake):
    conv = "spec-points"
    start(fake, conv)
    t = send(fake, conv, 2, "내 아이디어로 밀키스 화채", read_ans(task("my_idea", text="밀키스 화채")))
    iid = card(t, "ideas")["items"][0]["id"]
    real = llm_fake_concepts()

    def with_pack_point(system, user, schema):
        out = real(system, user, schema)
        for it in out["items"]:
            it["points"] = ["수박화채 맛", "250mL 캔", "과일 일러스트"]
        return out

    fake.answers["concepts"] = with_pack_point
    t = send(fake, conv, 3, "밀키스 화채로 컨셉 만들자", read_ans(task("concepts", ids=[iid])))
    c = card(t, "concepts")["items"][0]
    assert c["points"] == ["수박화채 맛", "과일 일러스트"]


SLIDE = ("밀키스 화채\n수박화채맛 · 부드러운 밀키스에 시원함을 더한 여름 한정\n250mL 슬림캔 / 500mL PET\n"
         "출고가 780원 /캔 1,200원 /PET, 권장 소비자가 캔 1,200원 / PET 1,800원\n캔 12개월, PET 9개월 · 130 kcal / 260 kcal\n"
         "2027년 5월 출시, 시즌 한정 5~9월")


def test_pasted_task_spec_becomes_my_idea_even_if_read_says_ideas(fake):
    assert idea_spec.pasted_task_spec(SLIDE)
    assert not idea_spec.pasted_task_spec("여름 한정 탄산음료 아이디어 줘")
    conv = "spec-paste"
    start(fake, conv)
    t = send(fake, conv, 2, SLIDE, read_ans(task("ideas", text="여름 한정 수박화채 맛")))
    items = card(t, "ideas")["items"]
    assert [i["name"] for i in items] == ["밀키스 화채"] * 2 and {i["by"] for i in items} == {"planner"}
    assert items[1]["variants"][0]["price"] == 1800  # 11-25: 규격마다 카드 하나
    assert [c["task"] for c in fake.calls].count("ideas") == 0


def test_spec_number_sentences_leave_idea_text():
    text = "수박화채 맛 밀키스예요. 가격은 780원, 권장 소비자가는 1200원이에요. 유통기한은 12개월이에요. 2027년 5월에 출시해요."
    assert idea_spec.clean_meta(text) == "수박화채 맛 밀키스예요."


def test_one_idea_makes_the_concept_without_asking(fake):
    conv = "spec-one"
    start(fake, conv)
    send(fake, conv, 2, "내 아이디어로 레몬 탄산", read_ans(task("my_idea", text="레몬 탄산")))
    t = send(fake, conv, 3, "컨셉으로 만들기", read_ans(task("concepts")))
    assert not any(e.t == "choices" for e in t)
    assert len(card(t, "concepts")["items"]) == 1


def test_idea_name_in_the_answer_becomes_the_pick(fake):
    conv = "spec-two"
    start(fake, conv)
    send(fake, conv, 2, "내 아이디어로 밀키스 화채", read_ans(task("my_idea", text="밀키스 화채")))
    send(fake, conv, 3, "내 아이디어로 레몬 탄산", read_ans(task("my_idea", text="레몬 탄산")))
    t = send(fake, conv, 4, "컨셉으로 만들기", read_ans(task("concepts")))
    assert any(e.t == "choices" for e in t)  # 둘이면 지금처럼 묻는다
    t = send(fake, conv, 5, "밀키스 화채로 만들어 줘", read_ans(task("concepts")))
    assert [c["name"] for c in card(t, "concepts")["items"]] == ["밀키스 화채"] * 2  # 규격마다 보드 하나


def test_result_target_label_matches_the_explore_screen():
    from agent import phrases as P
    from agent.result_brief import target_label
    assert target_label({"target": {"age": "40-49", "sex": "남자"}}) == "40~49세 남성"
    assert target_label({"target": {}}) is None
    assert P.interview_say("40~49세 남성") == "40~49세 남성 가상 소비자를 인터뷰할게요"


def llm_fake_concepts():
    from llm import fake as F
    return F.DEFAULTS["concepts"]


# ---------- 11-25: 아이디어와 컨셉 보드를 규격별로 완전히 나눈다 ----------


def turn_ids(conv, n, text, ids, to=None):
    async def run():
        return [e async for e in machine.turn(conv, text, list(ids), n, today=TODAY, reply_to=to)]

    return asyncio.run(run())


def task_ideas(fake, conv):
    send(fake, conv, 1, "밀키스 화채를 기획하려고 해. 20대를 위한 여름 한정 탄산음료야.",
         read_ans(task("note", "product", "밀키스 화채"), product_kind="탄산음료", shelf_kind="탄산"))
    t = send(fake, conv, 2, "이 방향으로 아이디어 내기", read_ans(task("ideas")))
    return card(t, "ideas")["items"], t


def test_both_specs_button_makes_two_boards_without_reading(fake):
    conv = "split-all"
    items, t = task_ideas(fake, conv)
    a, b = items[0]["id"], items[1]["id"]
    offer = next(e for e in t if e.t == "actions")
    assert offer.actions[0].id == "make-concepts" and offer.actions[0].label == "아이디어 선택하기"
    before = len(fake.calls)
    t = turn_ids(conv, 3, "아이디어 선택하기", ["make-concepts"])
    pick = next(e for e in t if e.t == "choices")  # 카드에서 고르는 차례가 바로 열린다
    assert pick.on_card == "ideas" and pick.kind == "multi" and not fake.calls[before:]
    assert [o.label for o in pick.options][:2] == ["밀키스 화채 슬림캔 250ml", "밀키스 화채 PET 500ml"]  # 이름이 같으면 규격으로 가른다
    t = turn_ids(conv, 4, "밀키스 화채, 밀키스 화채", [a, b], to=pick.id)
    assert "read" not in [c["task"] for c in fake.calls[before:]]  # 묻지 않고 바로 만든다
    boards = card(t, "concepts")["items"]
    assert [c["id"] for c in boards] == [a, b]
    assert [(c["price"], c["variants"][0]["label"]) for c in boards] == [("1,200원", "슬림캔 250ml"), ("1,800원", "PET 500ml")]
    assert all(len(c["variants"]) == 1 and c["insight"] for c in boards)
    for c in boards:
        ConceptItem.model_validate(c)


def test_card_button_adds_a_board_and_keeps_the_old_one(fake):
    conv = "split-add"
    items, _ = task_ideas(fake, conv)
    a, b = items[0]["id"], items[1]["id"]
    t = turn_ids(conv, 3, "밀키스 화채, 컨셉으로 만들어 줘", ["make-concepts", a], to="idea-card")
    assert [c["id"] for c in card(t, "concepts")["items"]] == [a]
    t = turn_ids(conv, 4, "밀키스 화채, 컨셉으로 만들어 줘", ["make-concepts", b], to="idea-card")
    assert [c["id"] for c in card(t, "concepts")["items"]] == [a, b]


def test_two_boards_ask_which_to_confirm_and_the_shelf_gets_that_board(fake):
    conv = "split-confirm"
    items, _ = task_ideas(fake, conv)
    a, b = items[0]["id"], items[1]["id"]
    turn_ids(conv, 3, "두 규격 모두 컨셉으로 만들기", [machine.MAKE_ALL_SPECS])
    t = send(fake, conv, 4, "이 컨셉으로 확정하기", read_ans(task("confirm")))
    pick = next(e for e in t if e.t == "choices")
    assert pick.on_card == "concepts" and [o.label for o in pick.options] == ["보드 1 슬림캔 250ml", "보드 2 PET 500ml"]
    assert not machine.CONVS[conv].confirmed
    t = turn_ids(conv, 5, "보드 2", [b], to=pick.id)
    n = machine.CONVS[conv]
    assert n.confirmed and [c["id"] for c in machine.confirmed_concepts(n)] == [b]
    boards = card(t, "concepts")
    assert boards["locked"] and [c.get("confirmed") for c in boards["items"]] == [None, True]
    spec = machine.shelf_spec(conv, n, machine.confirmed_concepts(n)[0])
    assert (spec.container, spec.volume, spec.price) == ("페트", 500, 1800)
    t = turn_ids(conv, 6, "편의점 매대에 올려 보기", ["go-shelf"])
    assert not any(e.t == "choices" and e.id.startswith(machine.PICK_SHELF) for e in t)  # 확정한 보드로 바로 간다
