import asyncio
import csv
import json

import pytest
from fastapi.testclient import TestClient

import ideas
import main
import onsite
from agent import diagnose, machine
from agent.note import Note
from onsite.schema import CSV_COLUMNS, FILENAMES
from shelftest import catalog, runner, store
from test_explore_engine import panel, spec  # noqa: F401
from tools.consumer import Group


def _write(table, rows):
    with (onsite.directory() / FILENAMES[table]).open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS[table])
        writer.writeheader()
        writer.writerows(rows)


def _price_sample(wtp=1400):
    onsite.directory().mkdir(exist_ok=True)
    _write("survey_ratings", [
        {"rid": f"synthetic-{i}", "concept": "밀키스 화채", "shown_price": 1800, "wtp": value}
        for i, value in enumerate((wtp - 200, wtp, wtp, wtp + 200))
    ] + [
        {"rid": "unmatched-size", "concept": "밀키스 화채", "shown_price": 1200, "wtp": 5000},
        {"rid": "unmatched-item", "concept": "생강 음료 견본", "shown_price": 1800, "wtp": 9000},
    ])


def _concept(pack="페트", volume=500, price=1800):
    return {"id": "concept-a", "name": "밀키스 화채", "_flavor": "수박화채", "_volume": volume,
            "_container": pack, "price": f"{price:,}원", "pack": f"{volume}mL {pack}", "points": []}


def _product(price, *, name="견본 페트", kind="탄산", pack=1, ours=False, volume=500, added=False):
    return catalog.Product(name, {"매대": "음료", "종류": kind, "묶음 수량": str(pack),
                                  "우리 제품": "예" if ours else "아니오", "가격(원)": str(price),
                                  "용량(ml)": str(volume), "모양": ""}, {}, added=added)


def test_live_and_prototype_share_price_trend_and_history(monkeypatch):
    _price_sample()
    for key in FILENAMES:
        (onsite.directory() / FILENAMES[key]).touch()
    (onsite.directory() / FILENAMES["survey_summary"]).write_text("{}", encoding="utf-8")
    searches = [
        {"keyword": "수박화채", "month": f"{year}-{month:02}", "search_index": value}
        for year, scores in ((2022, [10, 10, 60, 85, 48, 10]), (2023, [9, 11, 25, 40, 13, 10]))
        for month, value in zip(range(4, 10), scores, strict=True)
    ]
    searches += [{"keyword": "수박화채", "month": "2021-12", "search_index": 100},
                 {"keyword": "수박화채", "month": "2022-01", "search_index": 99}]
    _write("trend", searches)
    monkeypatch.setattr(catalog, "current", lambda: (
        _product(1000, name="견본", added=True), _product(1850), _product(2200),
        _product(900, volume=250), _product(600, ours=True), _product(5000, pack=2), _product(7500, kind="커피"),
    ))
    monkeypatch.setattr(ideas, "similar", lambda _: [
        {"source": "assets", "name": "수박맛 견본A", "status": "폐기", "started": "2019-12-01", "score": 9},
        {"source": "assets", "name": "수박맛 견본B", "status": "단종", "launched_on": "2020-09-01", "score": 9},
    ])
    n = Note(concepts=[_concept()])
    card = diagnose.board(n, n.concepts[0])
    assert (card.kind, card.stage) == ("diagnosis", "concept")
    with TestClient(main.app) as client:
        response = client.get("/api/w7/diagnosis", params={"pack": "500mL PET"})
        default = client.get("/api/w7/diagnosis").json()
        assert client.get("/api/w7/diagnosis", params={"pack": "등록되지 않은 규격"}).status_code == 422
    default_price = next(s for s in default["sections"] if s["id"] == "price")
    assert default_price["current"] == 1200 and default_price["wtp"] is None and "250mL" in default_price["spec"]
    assert response.status_code == 200
    assert response.json()["fixes"] == card.payload["fixes"]
    rows = {row["id"]: row for row in card.payload["sections"]}
    assert [(peak["year"], peak["season"], peak["peak"]) for peak in rows["trend"]["peaks"]] == [
        (2022, "여름", 85), (2023, "여름", 40),
    ]
    assert "정점이 지났어요" in rows["trend"]["summary"] and "피크아웃" not in rows["trend"]["summary"]
    assert rows["trend"]["keyword"] == "수박화채" and "2022년 85, 2023년 40" in rows["trend"]["summary"]
    assert any("다른 과일 맛" in detail for detail in rows["trend"]["details"])
    assert rows["history"]["summary"] == "수박맛 견본B(2020년)가 단종된 적이 있어요. 사유는 기록에 없어요."
    assert "·" not in rows["history"]["summary"] + "".join(rows["history"]["details"])
    assert rows["price"]["rivals"] == {"count": 4, "low": 900, "high": 2200}
    assert rows["price"]["same"] == {"count": 2, "low": 1850, "high": 2200}
    assert rows["price"]["wtp"]["n"] == 4 and rows["price"]["wtp"]["median"] == 1400
    assert rows["price"]["summary"] == "권장 소비자가는 1,800원으로, 소비자가 내겠다는 값(조사의 가운데 값)보다 400원 높아요."
    assert "냉장·냉동 진열 설비가 필요 없어요" in rows["distribution"]["summary"]
    assert "점포율이 없어요" in rows["distribution"]["details"][0]
    assert "synthetic-" not in response.text
    # 컨셉 보드 분석의 차트와 표가 쓰는 칸
    assert card.title == "컨셉 보드 분석"
    assert {"month": "2022-07", "search_index": 85} in rows["trend"]["series"]
    assert rows["price"]["points"] == [{"name": "견본 페트", "price": 1850}, {"name": "견본 페트", "price": 2200}]
    assert rows["history"]["rows"][0] == {"name": "수박맛 견본B", "year": 2020, "status": "단종", "reasons": None}
    assert rows["distribution"]["storage"] == "상온"


def test_survey_does_not_cross_package_or_flavor():
    _price_sample()
    can = _concept("캔", 250, 1200)
    alternative_flavor = {**_concept(), "_flavor": "생강"}
    for concept in (can, alternative_flavor):
        n = Note(concepts=[concept])
        payload = diagnose.board(n, concept).payload
        price = next(row for row in payload["sections"] if row["id"] == "price")
        assert price["wtp"] is None and not payload["fixes"]
        assert any("내겠다는 값" in detail for detail in price["details"])


def test_missing_data_and_distribution_store_denominator(monkeypatch):
    monkeypatch.setattr(catalog, "current", lambda: ())
    monkeypatch.setattr(ideas, "similar", lambda _: [])
    absent = diagnose.prototype_diagnosis()
    # 상온 제품의 유통은 걸리는 것이 없어서 괜찮음(ok). 나머지는 자료 없음
    assert {row["id"]: row["status"] for row in absent["sections"]}["distribution"] == "ok"
    assert {row["status"] for row in absent["sections"] if row["id"] != "distribution"} == {"missing"}
    assert not absent["fixes"]
    onsite.directory().mkdir()
    _write("infra", [
        {"channel": "편의점", "stores": 800, "frozen_rate": 0.24, "chilled_rate": 0.76},
        {"channel": "대형마트", "stores": 40, "frozen_rate": 0.85},
    ])
    concept = {"id": "synthetic", "name": "견본 냉동 파우치", "storage": "냉동"}
    card = diagnose.board(Note(), concept)
    distribution = next(row for row in card.payload["sections"] if row["id"] == "distribution")
    assert (distribution["rate"], distribution["stores"], distribution["status"]) == (0.24, 800, "flag")
    assert "800곳" in distribution["summary"] and "24%" in distribution["summary"]
    assert "85%" not in json.dumps(card.payload)


@pytest.mark.parametrize("choice", ["original", "fix", "both"])
def test_approved_choice_starts_the_corresponding_target_runs(choice, panel, monkeypatch):
    _price_sample()
    concept = _concept()
    n = Note(concepts=[concept], stage="concept", confirmed=True, group=Group(age="19-29", sex="여자"),
             occasion_code="D1")
    machine.adopt("test-chat", n)
    monkeypatch.setattr(runner, "default_total", lambda: 2)
    diagnose.board(n, concept)
    ids = [concept["id"], choice, *(["price-1400"] if choice != "original" else [])]

    async def scenario():
        approval = [event async for event in machine.turn("test-chat", "", ids, 2, reply_to=diagnose.REPLY_TO)]
        assert approval[0].current == "shelf" and n.shelf_pending == concept["id"]
        confirmation = [event async for event in machine.turn("test-chat", "", ["explore-skip"], 3)]
        confirm = next(event for event in confirmation if event.t == "confirm")
        expected_price = 1400 if choice == "fix" else 1800
        assert f"{expected_price:,}원" in confirm.rows[0].note
        events = [event async for event in machine.turn("test-chat", "", [machine.SHELF_START], 4)]
        shelf = next(event for event in events if getattr(event, "kind", None) == "shelf-run")
        assert shelf.payload["concept"]["price"] == expected_price
        target_id = shelf.payload["run_id"]
        target = store.load_meta(target_id)
        assert target_id == n.last_run and target["mode"] == "target" and not target["change"]
        task = runner.TASKS.get(target_id)
        if task is not None:
            await task
        if choice != "both":
            assert not n.improve
            assert [row["concept"]["price"] for row in store.all_meta()] == [expected_price]
            return
        assert n.improve["base_run"] == target_id
        assert any(getattr(event, "kind", None) == "improve" for event in events)
        item, = n.improve["items"]
        assert item["hypothesis"] and item["evidence"][0]["origin"] == "internal"
        variant = store.load_meta(item["run_id"])
        assert variant["participants"] == target["participants"]
        assert variant["target"] == target["target"] and variant["occasion_code"] == target["occasion_code"]
        assert variant["concept"]["price"] == 1400 and variant["mode"] == "improve"
        if "base_run_id" in variant:
            assert variant["base_run_id"] == target_id
        task = runner.TASKS.get(item["run_id"])
        if task is not None:
            await task
        diagnose.after_target(n, "test-chat", concept, target_id)
        assert n.improve["items"] == [item]
        assert len(store.all_meta()) == 2

    asyncio.run(scenario())
    assert concept["price"] == "1,800원"


def test_rejects_stale_approval_after_concept_edit():
    _price_sample()
    concept = _concept()
    n = Note(concepts=[concept])
    diagnose.board(n, concept)
    assert any("골라 주세요" in getattr(event, "text", "")
               for event in diagnose.choose(n, "test-chat", [concept["id"], "both", "invented-id"]))
    diagnose.choose(n, "test-chat", [concept["id"], "fix", "price-1400"])
    concept["price"] = "1,900원"
    current = spec(price=1900)
    assert diagnose.selected_spec(concept, current) is current
    events = diagnose.choose(n, "test-chat", [concept["id"], "both", "price-1400"])
    assert events[0].kind == "diagnosis"
    assert not concept["_diagnosis"].get("approved")


# ---------- 확정 차례의 칠성이의 말과 대화의 버튼(견본 /proto/analysis, 11-25). 값은 지어낸 견본 ----------

def _payload(*, trend=True, price=True, cheaper=True, fix=True):
    sections = [
        {"id": "trend", "status": "flag" if trend else "ok", "keyword": "수박화채", "highlight": "여름",
         "peaks": [{"year": 2025, "season": "여름", "peak": 90}, {"year": 2026, "season": "여름", "peak": 35}]},
        {"id": "price", "status": "flag" if price else "ok", "current": 1800 if price else 1500,
         "wtp": {"n": 10, "p25": 1500, "median": 1700, "p75": 1900},
         "same": {"count": 3, "low": 2000 if cheaper else 1600, "high": 2500}},
        {"id": "history", "status": "ok"},
        {"id": "distribution", "status": "ok"},
    ]
    fixes = [{"id": "price-1700", "values": {"price": 1700}}] if fix else []
    return {"concept_id": "concept-a", "concept_name": "견본", "sections": sections, "fixes": fixes}


def test_confirm_turn_two_flags_says_insight_and_offers_both_prices():
    say, buttons = diagnose.confirm_turn(_payload())
    assert say == ("이 컨셉으로 정했어요. 분석에서 살펴볼 점이 두 가지 나왔어요.\n\n"
                   "수박화채 검색은 올여름 정점이 작년 여름의 39%예요. 1,800원은 소비자가 내겠다는 값(1,700원)보다 100원 높아요. "
                   "다만 같은 용량의 다른 제품 3종(2,000원부터)보다는 싸요.\n\n"
                   "가격만 바꿔 1,800원과 1,700원을 매대에서 견줘 볼까요?")
    assert buttons == [
        ("w7-diagnose|concept-a|both|price-1700", "1,800원과 1,700원 둘 다 테스트"),
        ("w7-diagnose|concept-a|original", "1,800원만 테스트"),
        ("w7-diagnose|concept-a|fix|price-1700", "1,700원만 테스트"),
    ]


def test_confirm_turn_one_flag_drops_sentences_that_do_not_apply():
    say, _ = diagnose.confirm_turn(_payload(trend=False, cheaper=False))
    assert say.startswith("이 컨셉으로 정했어요. 분석에서 살펴볼 점이 한 가지 나왔어요.\n\n1,800원은")
    assert "검색" not in say and "다만" not in say


def test_confirm_turn_without_flags_offers_as_is():
    say, buttons = diagnose.confirm_turn(_payload(trend=False, price=False, fix=False))
    assert say == "이 컨셉으로 정했어요. 분석에서 테스트를 막는 점은 없었어요.\n\n이대로 매대에 올려 볼까요?"
    assert buttons == [("w7-diagnose|concept-a|original", "이대로 테스트하기"), ("download", "제안서로 내려받기")]


def test_chat_button_goes_to_choose_without_reading(panel, monkeypatch):
    _price_sample()
    concept = _concept()
    n = Note(concepts=[concept], stage="concept", confirmed=True, group=Group(age="19-29", sex="여자"),
             occasion_code="D1")
    machine.adopt("test-chat", n)
    monkeypatch.setattr(runner, "default_total", lambda: 2)
    diagnose.board(n, concept)
    assert diagnose.pick_ids(["go-shelf"]) is None
    trace: dict = {}

    async def scenario():
        return [event async for event in machine.turn(
            "test-chat", "1,800원과 1,400원 둘 다 테스트", [f"{diagnose.PICK}{concept['id']}|both|price-1400"], 2,
            trace=trace)]

    events = asyncio.run(scenario())
    assert events[0].current == "shelf" and n.shelf_pending == concept["id"]
    assert concept["_diagnosis"]["choice"] == "both" and concept["_diagnosis"]["approved"]["id"] == "price-1400"
    assert trace["read"]["skipped"] and trace["read"]["tasks"] == []


def test_survey_wtp_spread_and_acceptance_counts():
    _price_sample()  # 지어낸 응답 1,200 / 1,400 / 1,400 / 1,600원
    concept = _concept()
    price = next(s for s in diagnose.board(Note(concepts=[concept]), concept).payload["sections"] if s["id"] == "price")
    wtp = price["wtp"]
    assert (wtp["low"], wtp["high"]) == (1200, 1600)
    assert wtp["accept"] == [[1200, 4], [1300, 3], [1400, 3], [1500, 1], [1600, 1]]
