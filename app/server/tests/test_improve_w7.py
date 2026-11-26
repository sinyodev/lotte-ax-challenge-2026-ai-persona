"""창작 매대와 창작 가상 소비자만 쓰는 W7 개선 테스트."""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

from agent import improve, improve_compare, machine, persist
from agent import phrases as P
from agent.note import Note
from llm.base import set_llm
from llm.fake import FakeLLM
from shelftest import catalog, method, runner, store
from tools import shelf_items


def choice(visit, consumer, occasion, product):
    return {"cond": method.CONCEPT, "visit": visit, "uuid": consumer, "occasion": occasion, "product": product}


def test_pair_uses_common_completed_identity_and_actual_choice():
    original = {"line": "old", "shelf_products": [["own", "자사", True], ["rival", "타사", False]]}
    changed = {"line": "new"}
    before = [
        choice("1", "alpha", "meal", "old"),
        choice("2", "beta", "snack", "rival"),
        choice("3", "gamma", "snack", "old"),
        choice("4", "delta", "meal", method.NO_PURCHASE),
        choice("5", "epsilon", "meal", "old"),
        choice("6", "zeta", "meal", "old"),
        choice("7", "eta", "meal", "old"),
        choice("8", "theta", "meal", "old"),
        {"visit": "8", "skip": True},
    ]
    after = [
        choice("1", "alpha", "meal", "new"),
        choice("2", "beta", "snack", "new"),
        choice("3", "gamma", "snack", "own"),
        choice("4", "delta", "meal", "own"),
        choice("5", "different", "meal", "new"),
        choice("6", "zeta", "snack", "new"),
        choice("9", "eta", "meal", "new"),
        choice("8", "theta", "meal", "new"),
        choice("10", "iota", "meal", "new"),
    ]
    paired = improve_compare.paired(original, changed, before, after)
    assert {k: paired[k] for k in ("n", "both", "gained", "lost", "neither")} == {
        "n": 4, "both": 1, "gained": 1, "lost": 1, "neither": 1,
    }
    assert (paired["original_rate"], paired["changed_rate"], paired["delta_pp"]) == (50, 50, 0)
    assert paired["gained_groups"] == [{"label": "경쟁 제품", "count": 1}]
    assert paired["lost_groups"] == [{"label": "자사 제품", "count": 1}]
    assert paired["low_pp"] < 0 < paired["high_pp"]
    assert paired["verdict"] == "unclear"
    assert improve_compare.paired(original, changed, before, []) is None


def test_all_unchanged_pairs_still_have_uncertainty():
    rows = [choice(str(i), str(i), "meal", "other") for i in range(20)]
    same = {"line": "new", "shelf_products": []}
    paired = improve_compare.paired(same, same, rows, rows)
    assert paired["n"] == paired["neither"] == 20
    assert paired["low_pp"] < 0 < paired["high_pp"]


def make_product(i, price):
    return catalog.Product(f"견본 제품 {i}", {
        "매대": "음료", "상품명": f"fixture-{i}", "제조사": "견본 회사", "우리 제품": "아니오",
        "종류": "탄산", "용량(ml)": "500", "묶음 수량": "1", "가격(원)": str(price), "행사": "행사 없음",
        "모양": "페트", "당": "가당", "탄산": "있음",
    }, {})


@pytest.fixture
def engine(monkeypatch, tmp_path):
    fake = FakeLLM()
    set_llm(fake)
    machine.reset()
    monkeypatch.setenv("AX_LLM", "fake")
    monkeypatch.setenv("AX_TREND_SCHEDULE", "0")
    monkeypatch.setenv("AX_ONSITE_DIR", str(tmp_path / "missing"))
    monkeypatch.setattr(store, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(store, "BASE_DIR", tmp_path / "baselines")
    monkeypatch.setattr(runner, "_start", lambda _run_id: None)
    items = [make_product(i, price) for i, price in enumerate((1300, 1500, 1800, 2100))]
    monkeypatch.setattr(catalog, "current", lambda: items)
    people = tuple(method.Person(f"fixture-person-{i}", "여자", "19-29", 24, "학생",
                                 (24, "학생", "가상 지역", "1인 가구", f"창작 손님 {i}", ""))
                   for i in range(12))
    occasions = {"meal": {"상황": "점심 식사", "풀어 쓴 설명": "가볍게 점심을 먹어요."}}
    profiles = {p.uuid: {"좋아하는 음료 1순위": "차", "2순위": "", "3순위": "", "제로 음료 빈도": "가끔",
                         "다이어트 관심(1~5)": 3, "건강 관심(1~5)": 3, "규칙적 운동": "가끔"} for p in people}
    needs = [{"번호": code, "욕구": title, "풀어 쓴 설명": title}
             for code, title in (("N07", "맛이 확실한 것 즐기기"), ("N08", "새로운 것 맛보기"),
                                 ("N09", "음식과 어울리게 마시기"))]
    monkeypatch.setattr(method, "people", lambda *_: people)
    monkeypatch.setattr(method, "occasion_of", lambda *_: "meal")
    monkeypatch.setattr(method, "occasions", lambda: occasions)
    monkeypatch.setattr(method.pilot, "_display", {})
    monkeypatch.setattr(method.pilot, "ROUND", method.ROUND)
    monkeypatch.setattr(method, "base_ctx", lambda: {"shelf": "음료", "occasions": occasions,
                                                    "profiles": profiles, "needs": needs})
    yield fake
    machine.reset()
    set_llm(None)


def turn(chat, text, ids=(), reply_to=None):
    async def collect():
        return [event async for event in machine.turn(chat, text, list(ids), 2, reply_to=reply_to)]

    return asyncio.run(collect())


def card(events, kind="improve"):
    return next(e.payload for e in events if e.t == "card" and e.kind == kind)


def test_w7_uses_same_conditions_and_adopts_once(engine, monkeypatch):
    c = {"id": "x", "name": "견본 과일 음료", "price": "1,800원", "pack": "500ml 페트", "_container": "페트",
         "_volume": 500, "_flavor": "진한 맛", "_carb": "보통", "headline": "봄 한정", "points": [],
         "_sugar": "가당", "benefit": ""}
    note = machine.CONVS["scene-e"] = Note(concepts=[c], shelf_kind="탄산")

    async def make_run():
        spec = machine.shelf_spec("scene-e", note, c)
        spec.total = 12
        return runner.create(spec)

    run_id = asyncio.run(make_run())
    note.last_run = note.runs["x"] = run_id
    asyncio.run(runner._run(run_id))
    snapshot = store.load_meta(run_id)
    # 이 테스트에서 확인하려는 비선택 이유를 창작 선택 기록에서 하나씩 만든다.
    existing = store.answers(run_id)
    for row, label in zip((r for r in existing if r["cond"] == method.CONCEPT), method.BARRIERS):
        row["barriers"] = [label]
    store._answers_path(run_id).unlink()
    for row in existing:
        store.append_answer(run_id, row)

    offers = card(turn("scene-e", P.BTN_IMPROVE, ["improve"]))
    assert {i["kind"] for i in offers["items"]} >= {"price", "flavor", "form"}
    assert all(i["hypothesis"] and i["evidence"] for i in offers["items"])
    assert [p["price"] for p in offers["price_curve"]] == [1500, 1800, 2100]
    assert all(p["rate"] is None and "sales" not in p for p in offers["price_curve"])

    flavor = next(i for i in offers["items"] if i["kind"] == "flavor")
    form = next(i for i in offers["items"] if i["kind"] == "form")
    lower = next(i for i in offers["items"] if i["kind"] == "price")
    machine.CONVS["scene-e"] = note = persist.from_dict(persist.to_dict(note))
    revisited = card(turn("scene-e", P.BTN_IMPROVE, ["improve"]))
    assert revisited["items"] == offers["items"]

    result = card(turn("scene-e", "개선안을 비교해 주세요", [run_id, flavor["id"], form["id"], lower["id"]], "improve"))
    runs = [i for i in result["items"] if i.get("run_id")]
    assert len(runs) == 4
    for item in runs:
        variant = store.load_meta(item["run_id"])
        assert variant["participants"] == snapshot["participants"]
        assert variant["shelf_products"] == snapshot["shelf_products"]
        assert variant["base_run_id"] == run_id
        assert len(variant["change"]) == 1
        if item["id"] == lower["id"]:
            assert runner.stop(variant["id"])
            retry = card(turn("scene-e", "가격을 다시 테스트해 주세요", [run_id, item["id"]], "improve"))
            restarted = next(it for it in retry["items"] if it["id"] == item["id"])
            assert restarted["run_id"] == variant["id"]
            assert store.load_meta(variant["id"])["status"] == "running"
        asyncio.run(runner._run(variant["id"]))
        answers = store.answers(variant["id"])
        assert sum(bool(r.get("reused")) for r in answers) == snapshot["total"]

    prompts = [call["user"] for call in engine.calls if call["task"] == "shopper"]
    assert any("- 맛: 진한 맛" in p for p in prompts)
    assert any("- 맛: 향을 줄인 진한 맛" in p and "- 제형: 탄산 보통" in p for p in prompts)
    assert any("- 맛: 진한 맛" in p and "- 제형: 무탄산" in p for p in prompts)
    assert not any("연결한 니즈" in p for p in prompts)
    before_plan = runner._plan(snapshot)
    after_meta = store.load_meta(next(i["run_id"] for i in runs if i["id"] == form["id"]))
    after_plan = runner._plan(after_meta)
    assert before_plan.with_concept["fulfills"][before_plan.line]["N09"] == "잘 채움"
    assert after_plan.with_concept["fulfills"][after_plan.line]["N09"] == "못 채움"

    comparison = card(turn("scene-e", P.BTN_IMPROVE_COMPARE))
    finished = [i for i in comparison["items"] if i.get("run_id")]
    assert all(i["paired"]["n"] == 12 for i in finished)
    assert all(p["n"] == 12 and p["rate"] is not None for p in comparison["price_curve"])
    price_points = [(p["price"], p["run_id"]) for p in comparison["price_curve"] if p["price"] != 1800]
    with monkeypatch.context() as optional:
        optional.setitem(sys.modules, "calibrate", None)
        assert all("sales" not in p for p in improve_compare.price_curve(run_id, 1800, price_points))
        calls = []

        def estimate(concept, result):
            price = concept["price"]
            calls.append((price, result["n"]))
            return {"monthly": [{"month": "2026-07", "amount": [price, 2 * price, 3 * price]}],
                    "assumptions": ["견본 기간"]}

        optional.setitem(sys.modules, "calibrate", SimpleNamespace(sales=SimpleNamespace(estimate=estimate)))
        curve = improve_compare.price_curve(run_id, 1800, price_points)
        assert calls == [(1500, 12), (1800, 12), (2100, 12)]
        assert [p["sales"]["monthly"][0]["amount"][1] for p in curve] == [3000, 3600, 4200]
    item = next(i for i in finished if i["id"] == form["id"])
    foreign = machine.CONVS["foreign"] = persist.from_dict(persist.to_dict(note))
    denied = turn("foreign", "채택", [run_id, item["id"]], "w7-adopt")
    assert not any(e.t == "card" for e in denied) and foreign.concepts[0]["_carb"] == "보통"

    adopted = turn("scene-e", "채택", [run_id, item["id"]], "w7-adopt")
    assert card(adopted)["adopted_item_id"] == item["id"]
    assert {"key": "carbonation", "label": "탄산", "value": "무탄산"} in card(adopted, "concepts")["items"][0]["spec"]
    assert note.concepts[0]["_adopted_improvement"]["evidence"] == item["evidence"]
    assert store.load_meta(run_id) == snapshot
    before = persist.to_dict(note)["concepts"][0]["_adopted_improvement"]
    repeat = turn("scene-e", "채택", [run_id, item["id"]], "w7-adopt")
    assert card(repeat)["adopted_item_id"] == item["id"]
    assert note.concepts[0]["_adopted_improvement"] == before

    manual = card(turn("scene-e", "맛을 상큼한 배 맛으로 바꿔서 다시 테스트해 줘"))
    chosen = next(i for i in manual["items"] if i["after"] == "상큼한 배 맛")
    assert store.load_meta(chosen["run_id"])["concept"]["flavor"] == "상큼한 배 맛"


def test_no_features_still_uses_same_shelf_description_template():
    row = method.concept_row("견본", 1700, None)
    plan = SimpleNamespace(line="견본", with_concept={"products": [row]})
    assert shelf_items.enrich_concept(plan, {"volume": 250, "container": "캔"}) is plan
    prompt = shelf_items.concept_prompt(plan, [row])
    assert "- 맛: 표기 없음" in prompt and "- 제형: 표기 없음" in prompt
    assert "- 가격: 1,700원" in prompt and "- 용량: 250mL" in prompt


def test_selected_quote_is_saved_with_plan():
    imp = {"items": []}
    base = improve.Base("견본", "병", 250, 1700)
    quote = {"origin": "record", "text": "포장 앞에서 맛이 뭔지 한눈에 알면 좋겠어요.",
             "quote_id": "quote-1", "session_id": "session-1"}
    item = machine._add_item(imp, base, {"appeal": "부드러운 배 향"}, "맛을 설명하는 문구를 써 봐요.",
                             hypothesis="표기가 선택을 도울까요?", evidence=[quote])
    payload = machine.improve_card(Note(improve=imp)).payload
    assert item["values"] == {"appeal": "부드러운 배 향"}
    assert payload["items"][0]["hypothesis"] == "표기가 선택을 도울까요?"
    assert payload["items"][0]["evidence"] == [quote]


def test_public_run_changes_only_the_requested_saved_feature(engine):
    from fastapi.testclient import TestClient
    import chats
    import main

    board = {"id": "new", "name": "견본 음료", "_volume": 500, "_container": "페트", "pack": "500ml 페트",
             "_flavor": "배 맛", "_carb": "보통", "price": "1,800원", "benefit": "기존 소구점"}
    note = Note(concepts=[board], shelf_kind="탄산")
    chats.save({"id": "sample-run", "title": "견본", "source": "live", "messages": [], "note": persist.to_dict(note)})
    request = {"chat_id": "sample-run", "concept_id": "new", "total": 12}
    with TestClient(main.app) as client:
        missing = client.post("/api/runs", json={**request, "change": {"form": "무탄산"}})
        assert missing.status_code == 422 and "원래 안" in missing.json()["detail"]
        base = store.load_meta(client.post("/api/runs", json=request).json()["run_id"])
        for key, value in (("form", "무탄산"), ("flavor", "진한 배 맛"), ("appeal", "간식과 함께")):
            reply = client.post("/api/runs", json={**request, "change": {key: value}})
            assert reply.status_code == 200
            variant = store.load_meta(reply.json()["run_id"])
            assert variant["base_run_id"] == base["id"] and variant["participants"] == base["participants"]
            assert variant["concept"] == {**base["concept"], key: value}
            assert variant["concept_prompt_version"] == base["concept_prompt_version"]
        rejected = client.post("/api/runs", json={**request, "change": {"form": "무탄산", "price": 1600}})
        assert rejected.status_code == 422 and "하나" in rejected.json()["detail"]
        base.pop("concept_prompt_version")
        store.save_meta(base)
        incompatible = client.post("/api/runs", json={**request, "change": {"form": "무탄산"}})
        assert incompatible.status_code == 422 and "이전 테스트" in incompatible.json()["detail"]


def test_report_uses_the_paired_verdict_on_the_first_page_and_in_the_appendix():
    from agent import review

    base = {"picked": 30, "n": 100, "rank": 1, "products": 20, "low": 18, "high": 50}
    changed = {**base, "picked": 40, "low": 23, "high": 56}
    pair = {"n": 100, "both": 30, "gained": 10, "lost": 0, "neither": 60, "original_rate": 30,
            "changed_rate": 40, "delta_pp": 10, "low_pp": 1, "high_pp": 16, "verdict": "more"}
    assert improve.verdict(base, changed) == "unclear"
    tested = review.Inputs(base, "20대", "견본", "캔", "1,200원", "음료", 100, 100,
                           variants=[review.Variant("가격 변경안", "1,100원", changed, pair)])
    rows = review.compare_rows(base, tested.variants)
    assert rows[1]["best"] and rows[1]["verdict"] == "better"
    assert any("공통 응답자 100명" in line for line in review.recommend(tested, rows)["reasons"])
    rules = review.appendix(tested)["rules"]
    assert any("가격 변경안: 같은 방문" in line for line in rules) and not any("윌슨" in line for line in rules)
    decreasing = {**pair, "both": 20, "lost": 10, "gained": 0, "neither": 70, "verdict": "less",
                  "changed_rate": 20, "delta_pp": -10, "low_pp": -16, "high_pp": -1}
    tested.variants = [review.Variant("가격 변경안", "1,600원", {**changed, "picked": 20}, decreasing)]
    lower_rows = review.compare_rows(base, tested.variants)
    assert any("기존안보다 선택률이 낮음" in line for line in review.recommend(tested, lower_rows)["reasons"])
