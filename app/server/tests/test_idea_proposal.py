"""11-25: 칠성이가 스스로 낸 아이디어가 과제 슬라이드의 칸(규격, 권장 소비자가, 유통기한·열량, 출시·판매 시기, 채널)을 제안한다."""

import asyncio
from datetime import date
from types import SimpleNamespace

import pytest

from agent import idea_spec, machine
from llm.base import set_llm
from llm.fake import FakeLLM

TODAY = date(2026, 11, 25)


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


def item(name, container, volume, **kw):
    base = {"name": name, "flavor": name.split()[0], "container": container, "volume_ml": volume,
            "features": ["상큼한 향"], "line": f"{name} 한 줄", "diff": "다른 맛", "price": 1500,
            "shelf_life_months": 12, "kcal": 120, "launch": "2027-05", "season": "", "channels": ["편의점"]}
    base.update(kw)
    return base


def test_chilseong_ideas_carry_the_task_sheet_fields(fake):
    start(fake, "p1")
    ev = send(fake, "p1", 2, "아이디어 줘", read_ans(task("ideas")))
    items = card(ev, "ideas")["items"]
    sizes = idea_spec.shelf_sizes("음료")
    for it in items:
        assert it["by"] == "chilseong"
        v = it["variants"][0]
        container = machine.CONVS["p1"].idea(it["id"])["_container"]
        assert v["volume_ml"] in sizes[container][0]  # 매대에 있는 용량
        assert v["price"] % 100 == 0 and v["shelf_life_months"] and v["kcal"] is not None
        assert "factory_price" not in v  # 출고가는 제안하지 않는다
        assert it["launch"] == "2027-05" and it["channels"][0] == "편의점"


def test_odd_sizes_and_prices_are_snapped_to_the_shelf(fake):
    start(fake, "p2")
    fake.answers["ideas"] = [{"need": "여름에 시원하게", "items": [
        item("수박 소다", "캔", 181, price=950, kcal=900, launch="2025-01", season="여름 한정",
             channels=["온라인", "대형마트·SSM", "자판기"]),
        item("유자 소다", "컵", 133, price=99999, shelf_life_months=40, season="6~8월 한정"),
        item("자두 소다", "병", 333, price=2240, launch="2027-13"),
    ]}]
    ev = send(fake, "p2", 2, "아이디어 줘", read_ans(task("ideas")))
    a, b, c = card(ev, "ideas")["items"]
    sizes = idea_spec.shelf_sizes("음료")
    can_vols, can_lo, _ = sizes["캔"]
    # 181mL 캔 → 매대의 캔 가운데 가장 가까운 용량, 950원 → 100원 단위로 캔 가격 범위 안
    assert a["variants"][0]["volume_ml"] == min(can_vols, key=lambda x: abs(x - 181))
    assert a["variants"][0]["price"] == max(1000, -(-can_lo // 100) * 100) and a["variants"][0]["price"] % 100 == 0
    assert "kcal" not in a["variants"][0]  # 용량의 0.8배를 넘는 열량은 버린다
    assert "launch" not in a and "season" not in a  # 지난 출시, 달이 없는 판매 시기는 버린다
    assert a["channels"] == ["편의점", "대형마트·SSM", "온라인"]  # 편의점은 늘, 모르는 채널은 버린다
    assert b["variants"][0]["volume_ml"] == min(sizes["컵"][0], key=lambda x: abs(x - 133))
    assert b["variants"][0]["price"] == sizes["컵"][2] // 100 * 100 and "shelf_life_months" not in b["variants"][0]
    assert b["season"] == "6~8월 한정"
    assert c["variants"][0]["volume_ml"] == 355  # 병은 매대 자료가 없어 190, 250, 355, 500 가운데
    assert c["variants"][0]["price"] == 2200 and "launch" not in c
    assert machine.CONVS["p2"].idea(a["id"])["pack"] == f"캔 {a['variants'][0]['volume_ml']}ml"


def test_concept_from_a_chilseong_idea_tests_the_proposed_price(fake):
    start(fake, "p3")
    ev = send(fake, "p3", 2, "아이디어 줘", read_ans(task("ideas")))
    first = card(ev, "ideas")["items"][0]
    proposed = first["variants"][0]["price"]
    ev = send(fake, "p3", 3, "A로 컨셉 만들자", read_ans(task("concepts", ids=[first["id"]])))
    c = card(ev, "concepts")["items"][0]
    assert c["price"] == f"{proposed:,}원"
    assert c["variants"][0]["price"] == proposed and c["launch"] == first["launch"]
    assert c["channels"] == first["channels"]
    n = machine.CONVS["p3"]
    spec = machine.shelf_spec("p3", n, n.concepts[0])
    assert spec.price == proposed and spec.volume == first["variants"][0]["volume_ml"]


def test_proposed_spec_ignores_old_answers_without_the_new_fields():
    ans = SimpleNamespace(container="페트", volume_ml=500)
    spec = idea_spec.proposed_spec(ans, "음료", TODAY)
    assert spec["variants"] == [] and spec["channels"] == ["편의점"] and spec["launch"] is None


def test_old_ideas_without_spec_still_render():
    old = {"id": "a", "name": "옛 아이디어", "flavor": "청귤", "pack": "페트 500ml", "features": ["x"],
           "line": "l", "diff": "d", "by": "chilseong", "_container": "페트", "_volume": 500}
    assert idea_spec.public(old) == {}
    assert machine._idea_public(old)["name"] == "옛 아이디어"


def test_task_concept_said_by_the_planner_becomes_idea_a(fake):
    send(fake, "p4", 1, "밀키스 화채를 기획하려고 해. 20대를 위한 여름 한정 탄산음료야.",
         read_ans(task("note", "product", "밀키스 화채"), product_kind="탄산음료", shelf_kind="탄산"))
    ev = send(fake, "p4", 2, "이 방향으로 아이디어 내기", read_ans(task("ideas")))
    items = card(ev, "ideas")["items"]
    a = items[0]
    assert a["id"] == "a" and a["name"] == "밀키스 화채" and a["by"] == "planner" and a["flavor"] == "수박화채맛"
    # 11-25: 규격마다 카드 하나(A 슬림캔, B PET). 이름·맛은 같고 규격과 그 값만 다르다
    b = items[1]
    assert b["name"] == "밀키스 화채" and b["by"] == "planner" and b["flavor"] == "수박화채맛"
    assert [(v["volume_ml"], v["price"], v["factory_price"], v["shelf_life_months"], v["kcal"])
            for x in (a, b) for v in x["variants"]] == [(250, 1200, 780, 12, 130), (500, 1800, 1200, 9, 260)]
    assert a["pack"] == "캔 250ml" and b["pack"] == "페트 500ml"
    assert a["launch"] == "2027-05" and a["season"] == "5~9월 한정" and a["channels"] == ["편의점", "대형마트·SSM", "온라인"]
    assert len(items) == 3 and items[2]["by"] == "chilseong"  # 칠성이의 제안은 하나만(한 화면에 셋)
    ideas_user = [c["user"] for c in fake.calls if c["task"] == "ideas"][-1]
    assert "새 아이디어 1개를 낸다" in ideas_user and "밀키스 화채 (맛 수박화채맛, 과제의 컨셉)" in ideas_user
    offer = next(e for e in ev if e.t == "actions")
    assert [x.label for x in offer.actions][0] == "아이디어 선택하기"
    # 다른 아이디어 보기에서는 다시 넣지 않는다
    ev = send(fake, "p4", 3, "다른 아이디어는 없어?", read_ans(task("more")))
    names = [i["name"] for i in card(ev, "ideas")["items"]]
    assert names.count("밀키스 화채") == 2 and len(names) == 3


def test_task_idea_failure_does_not_fail_the_turn(fake, monkeypatch):
    async def boom(*a, **k):
        raise machine.StepFailed("my_idea", "x")

    monkeypatch.setattr(machine.steps, "my_idea", boom)
    send(fake, "p5", 1, "밀키스 화채를 기획하려고 해",
         read_ans(task("note", "product", "밀키스 화채"), product_kind="탄산음료", shelf_kind="탄산"))
    ev = send(fake, "p5", 2, "이 방향으로 아이디어 내기", read_ans(task("ideas")))
    items = card(ev, "ideas")["items"]
    # 11-25: 과제 컨셉(규격 둘)을 올리려던 자리라 칠성이의 제안은 하나만 낸다. 실패해도 차례는 이어진다
    assert len(items) == 1 and all(i["by"] == "chilseong" for i in items)
