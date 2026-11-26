"""매대 테스트(지시서 15): 방법이 스크립트와 같은지, 뒤에서 도는 작업, 통로. 모델은 fake만 쓴다."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

import chats
import main
from agent import persist
from agent.note import Note, Slot
from llm.base import set_llm
from llm.fake import FakeLLM
from shelftest import method, result, runner, store
from tools.consumer import Group

LINE = "테스트 녹차 페트 500ml"


@pytest.fixture(autouse=True)
def no_onsite_tables(monkeypatch, tmp_path):
    monkeypatch.setenv("AX_ONSITE_DIR", str(tmp_path / "missing"))


def shelf_args(**kw):
    base = dict(name=LINE, price=1800, promo="", line="", band="19-29", occasion="D7", mix=True, ask=True, limit=20)
    base.update(kw)
    return argparse.Namespace(**base)


# ---------- 방법: 스크립트와 한 글자도 다르지 않다 ----------


@pytest.mark.parametrize("promo", ["", "1+1"])
def test_prompts_match_shelf_test_script_without_onsite_data(promo):
    args = shelf_args(promo=promo)
    plain, with_concept = method.shelf_test.setup(args)
    p = method.plan("19-29", None, "D7", args.limit, LINE, args.price, promo or None)
    assert [(v["방문"], v["uuid"], v["상황 번호"]) for v in p.visits] == \
        [(v["방문"], v["uuid"], v["상황 번호"]) for v in plain["visits"][: args.limit]]
    for v in p.visits:
        for cond in (method.BASELINE, method.CONCEPT):
            ctx = with_concept if cond == method.CONCEPT else plain
            system, user, order = method.pilot.prompts(ctx, v, cond, 1)
            if cond == method.CONCEPT:
                number = next(i + 1 for i, q in enumerate(order) if q["상품명"] == LINE)
                user += method.shelf_test.ASK.format(number=number, name=method.pilot._display[LINE])
            assert method.prompts(p, v, cond) == (system, user, order)


def test_no_target_uses_every_age_and_real_occasions():
    p = method.plan(None, None, None, 30, LINE, 1800, None)
    assert len({v["연령대"] for v in p.visits}) > 2
    assert len({v["상황 번호"] for v in p.visits}) > 1
    women = method.plan("30-39", "여자", None, 10, LINE, 1800, None)
    assert {v["성별"] for v in women.visits} == {"여자"} and {v["연령대"] for v in women.visits} == {"30-39"}


def _captured_schema(monkeypatch, call):
    seen = {}

    def fake_run(cmd, **kw):
        seen["schema"] = json.loads(cmd[cmd.index("--json-schema") + 1])
        out = {"type": "result", "is_error": False, "usage": {},
               "structured_output": {"choice_number": 0, "reason_needs": [], "reason_other": "", "reason_sentence": "",
                                     "new_product": {"view": "관심 없다", "barriers": [], "said": ""}}}
        return subprocess.CompletedProcess(cmd, 0, json.dumps(out), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    call()
    return seen["schema"]


def test_answer_schema_matches_shelf_test_script(monkeypatch):
    asked = _captured_schema(monkeypatch, lambda: method.shelf_test.answer("s", "u", True))
    plain = _captured_schema(monkeypatch, lambda: method.shelf_test.answer("s", "u", False))
    assert method.schema(True) == asked
    assert method.schema(False) == plain


def test_parse_rejects_numbers_off_the_shelf():
    order = [{"상품명": "가"}, {"상품명": "나"}]
    ok = method.parse({"choice_number": 2, "reason_needs": ["N01"], "reason_other": "", "reason_sentence": "a\nb"},
                      order, False)
    assert ok["product"] == "나" and ok["sentence"] == "a b"
    with pytest.raises(method.BadAnswer):
        method.parse({"choice_number": 3, "reason_needs": [], "reason_other": "", "reason_sentence": ""}, order, False)
    with pytest.raises(method.BadAnswer):  # 새 제품에 대한 생각이 빠짐
        method.parse({"choice_number": 0, "reason_needs": [], "reason_other": "", "reason_sentence": ""}, order, True)


def test_wilson():
    from shelftest.result import wilson

    assert wilson(0, 0) == (0.0, 0.0)
    low, high = wilson(4, 100)
    assert 1.5 <= low <= 1.7 and 9.8 <= high <= 10.0


# ---------- 뒤에서 도는 작업 ----------


@pytest.fixture
def fake():
    f = FakeLLM()
    set_llm(f)
    return f


def spec(**kw) -> runner.Spec:
    base = dict(chat_id="c1", concept_id="a", name="테스트 녹차", container="페트", volume=500, price=1800,
                age="19-29", occasion_code="D7", total=12)
    base.update(kw)
    return runner.Spec(**base)


def shopper_calls(fake):
    return [c for c in fake.calls if c["task"] == "shopper"]


def run_to_end(s: runner.Spec) -> str:
    async def go():
        run_id = runner.create(s)
        task = runner.TASKS.get(run_id)
        if task is not None:
            await task
        return run_id

    return asyncio.run(go())


def test_run_asks_each_shopper_twice_and_counts(fake):
    run_id = run_to_end(spec())
    calls = shopper_calls(fake)
    assert len(calls) == 24  # 12명 × (컨셉이 없는 매대, 컨셉을 올린 매대)
    assert all(c["model"] == runner.DEFAULT_MODEL for c in calls)
    assert sum("[하나 더]" in c["user"] for c in calls) == 12
    v = runner.view(run_id)
    assert v["status"] == "done" and v["asked"] == 12 and v["total"] == 12 and v["skipped"] == 0
    assert v["concept"] == {"id": "a", "name": "테스트 녹차", "pack": "500ml 페트", "container": "페트", "volume": 500,
                            "price": 1800, "promo": None}
    assert v["who"]["label"] == "20대 손님" and v["who"]["occasion"] == "밖에서 식사할 때 입가심"
    assert 0 < v["who"]["occasion_share"] < 100
    r = v["result"]
    assert r["n"] == 12 and r["products"] == 56
    assert sum(x["count"] for x in r["views"]) == 12
    assert sum(x["n"] for x in r["by_occasion"]) == 12
    assert r["picked"] == sum(x["picked"] for x in r["by_occasion"])
    assert r["low"] <= 100 * r["picked"] / 12 <= r["high"]
    if r["picked"]:
        me = [x for x in r["neighbors"] if x["self"]]
        assert len(me) == 1 and me[0]["picked"] == r["picked"] and r["rank"] >= 1
        assert sum(x["count"] for x in r["from"]["rival"] + r["from"]["own"]) + r["from"]["none"] == r["picked"]
    for q in r["quotes"]["picked"] + r["quotes"]["passed"]:
        assert re.fullmatch(r"\d+세 (남자|여자)(, .+)?", q["who"])
        assert set(q) == {"visitor", "who", "occasion", "said", "chose"}
    assert len(r["quotes"]["passed"]) <= 4


def test_concept_shelf_is_asked_first(fake):
    run_id = run_to_end(spec(total=6))
    calls = shopper_calls(fake)
    assert all("[하나 더]" in c["user"] for c in calls[:6])  # 컨셉을 올린 매대가 모두 먼저
    assert not any("[하나 더]" in c["user"] for c in calls[6:])
    rows = [r for r in store.answers(run_id) if r["cond"] == method.CONCEPT]
    r = result.summarize(store.load_meta(run_id), rows, {})  # 컨셉이 없는 매대의 답이 오기 전
    assert r["n"] == 6 and r["from"]["pending"] == r["picked"]
    assert not r["from"]["rival"] and not r["from"]["own"] and r["from"]["none"] == 0


def test_same_thing_again_gives_the_same_run_and_baselines_are_reused(fake):
    first = run_to_end(spec())
    assert run_to_end(spec()) == first
    assert len(shopper_calls(fake)) == 24  # 다시 묻지 않는다
    second = run_to_end(spec(price=1500))  # 가격이 다르면 새 테스트. 컨셉이 없는 매대의 답은 다시 쓴다
    assert second != first
    assert len(shopper_calls(fake)) == 24 + 12
    rows = store.answers(second)
    assert sum(1 for r in rows if r.get("reused")) == 12


def test_bad_answers_are_asked_again_then_the_shopper_is_skipped(fake):
    s = spec(total=6)
    p = method.plan(s.age, s.sex, s.occasion_code, s.total, method.line_name(s.name, s.container, s.volume),
                    s.price, None)
    _, first_user, _ = method.prompts(p, p.visits[0], method.BASELINE)
    who = first_user.split("[평소 습관]", 1)[0]
    from llm.fake import _shopper

    def answer(system, user, schema):
        if user.startswith(who):
            return {"choice_number": 999, "reason_needs": [], "reason_other": "", "reason_sentence": ""}
        return _shopper(system, user, schema)

    fake.answers["shopper"] = answer
    run_id = run_to_end(s)
    v = runner.view(run_id)
    assert v["skipped"] == 1 and v["asked"] == 5
    assert sum(1 for c in shopper_calls(fake) if c["user"].startswith(who)) == 3  # 처음 + 다시 두 번


def test_resumes_after_restart(fake):
    run_id = run_to_end(spec(total=6))
    meta = store.load_meta(run_id)
    rows = store.answers(run_id)
    keep = [r for r in rows if r["visit"] in ("T001", "T002")]
    store.delete(run_id)
    meta["status"] = "running"
    store.save_meta(meta)
    for r in keep:
        store.append_answer(run_id, r)
    before = len(shopper_calls(fake))

    async def go():
        runner.view(run_id)  # 읽으면 남은 손님부터 이어서 돈다
        await runner.TASKS[run_id]

    asyncio.run(go())
    v = runner.view(run_id)
    assert v["status"] == "done" and v["asked"] == 6
    assert len(shopper_calls(fake)) - before == 4  # 남은 네 명의 컨셉 매대만(컨셉이 없는 매대는 저장해 둔 답)


def test_stop(fake):
    async def go():
        run_id = runner.create(spec(total=12))
        assert runner.stop(run_id)
        await asyncio.sleep(0)
        return run_id

    run_id = asyncio.run(go())
    assert runner.view(run_id)["status"] == "stopped"


def test_change_is_applied():
    s = runner.apply_change(spec(), {"price": "1500", "promo": "1+1", "volume": 350, "other": 1})
    assert (s.price, s.promo, s.volume) == (1500, "1+1", 350) and "other" not in s.change


# ---------- 통로 ----------


def _chat_with_concepts(chat_id: str = "chat-shelf", confirmed: bool = True) -> None:
    n = Note(product=Slot("녹차", "planner"), target=Slot("20대", "planner"))
    n.kind, n.shelf_kind, n.group, n.occasion_code = "차", "차", Group(age="19-29", label="20대"), "D7"
    n.confirmed = confirmed
    n.concepts = [{"id": "a", "name": "테스트 녹차", "headline": "h", "benefit": "b", "points": [], "price": "1,800원",
                   "pack": "500ml 페트", "_container": "페트", "_volume": 500, "_price_by": "shelf", "_shelf_v": 4}]
    chats.save({"id": chat_id, "title": "녹차", "created_at": "2026-11-23T00:00:00+00:00",
                "updated_at": "2026-11-23T00:00:00+00:00", "part": "concept", "source": "live", "messages": [],
                "note": persist.to_dict(n), "turns": []})


def test_runs_api(fake):
    _chat_with_concepts()
    with TestClient(main.app) as client:
        assert client.post("/api/runs", json={"chat_id": "chat-none", "concept_id": "a"}).status_code == 404
        assert client.post("/api/runs", json={"chat_id": "chat-shelf", "concept_id": "z"}).status_code == 404
        res = client.post("/api/runs", json={"chat_id": "chat-shelf", "concept_id": "a", "total": 8})
        assert res.status_code == 200
        run_id = res.json()["run_id"]
        for _ in range(200):
            body = client.get(f"/api/runs/{run_id}").json()
            if body["status"] != "running":
                break
            time.sleep(0.02)
        assert body["status"] == "done" and body["asked"] == 8 and body["result"]["n"] == 8
        assert set(body) >= {"id", "status", "concept", "who", "asked", "total", "skipped", "started_at", "updated_at",
                             "model", "result", "placement"}
        assert body["placement"] is None
        again = client.post("/api/runs", json={"chat_id": "chat-shelf", "concept_id": "a", "total": 8}).json()
        assert again["run_id"] == run_id
        changed = client.post("/api/runs", json={"chat_id": "chat-shelf", "concept_id": "a", "total": 8,
                                                 "change": {"price": 1500}}).json()
        assert changed["run_id"] != run_id
        assert client.post(f"/api/runs/{changed['run_id']}/stop").status_code == 200
        assert client.get("/api/runs/run-000000000000").status_code == 404
        assert client.get("/api/runs/../x").status_code == 404
        assert client.post("/api/runs/run-000000000000/stop").status_code == 404


def test_chat_listing_has_confirmed_concepts():
    _chat_with_concepts("chat-yes")
    _chat_with_concepts("chat-no", confirmed=False)
    client = TestClient(main.app)
    rows = {r["id"]: r for r in client.get("/api/chats").json()}
    assert rows["chat-yes"]["concepts"] == [{"id": "a", "name": "테스트 녹차", "container": "페트", "pack": "500ml 페트",
                                             "price": "1,800원"}]
    assert rows["chat-no"]["concepts"] == []
