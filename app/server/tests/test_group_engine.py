"""실행에서 집단 인터뷰를 열고, 기록에 남긴 발언과 호출을 확인한다."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from agent import result_brief
from llm.base import LLMError
from llm.fake import FakeLLM
from shelftest import group, group_dialogue, group_store, method, result, runner, store

RUN = "run-0123456789ab"
OTHER = "run-0123456789ff"
LINE = "새 음료 코드"
NAME = "새 음료"
BARRIER = "맛이 끌리지 않음"


@pytest.fixture
def visits(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "RUNS_DIR", tmp_path / "runs")
    people = tuple(method.Person(f"u{i}", "여자" if i < 4 else "남자", "20대" if i < 4 else "40대",
                                 24 if i < 4 else 45, "직장인", (0, 0, 0, 0, "")) for i in range(9))
    assigned = [{"visit": f"v{i}", "uuid": p.uuid, "occasion": "at"} for i, p in enumerate(people)]
    monkeypatch.setattr(method, "people", lambda *_: people)
    monkeypatch.setattr(method, "occasions", lambda: {"at": {"상황": "퇴근길"}})
    monkeypatch.setattr(runner, "_plan", lambda meta: SimpleNamespace(
        visits=[{"방문": p["visit"], "uuid": p["uuid"]} for p in meta["participants"]],
        by_uuid={p.uuid: p for p in people}))
    monkeypatch.setattr(method, "prompts", lambda *_: ("", "퇴근길에 매대를 둘러봐요.", []))
    meta = {"id": RUN, "status": "done", "target": {}, "concept": {"name": NAME, "price": 1000}, "line": LINE,
            "participants": assigned, "shelf_products": [["own-x", "보리차", True], ["rival-x", "탄산수", False]]}
    store.save_meta(meta)
    store.save_meta({**meta, "id": OTHER})
    for i, visitor in enumerate(assigned):
        row = {**visitor, "cond": method.BASELINE, "product": "rival-x" if i % 2 else "own-x",
               "sentence": "늘 마시던 걸로 골랐어요."}
        if i != 3:
            store.append_answer(RUN, row)
        chosen = i in (0, 1, 3)
        row = {**row, "cond": method.CONCEPT,
               "product": LINE if chosen else method.NO_PURCHASE if i == 8 else row["product"],
               "sentence": "새로 나온 게 눈에 띄었어요." if chosen else row["sentence"],
               "barriers": [] if chosen else [BARRIER if i < 7 else "가격이 비쌈"]}
        store.append_answer(RUN, row)
    return meta, people


def test_fgi_summary_counts_people_with_a_recorded_position():
    def answer(key, person, position, text, quote):
        return {"id": key, "person": person, "position": position, "text": text, "position_quote": quote}

    turns = [answer("a", "first", "consider", "조건을 보고 고려해 볼래요.", "고려해 볼래요."),
             answer("b", "first", "consider", "다시 고려해 볼래요.", "고려해 볼래요."),
             answer("c", "second", "pass", "저는 지나칠래요.", "지나칠래요."),
             answer("d", "third", "unsure", "조건을 확인해요.", "더 고민해요.")]
    assert [(f["count"], f["turn_ids"]) for f in group_dialogue.independent_answers(turns)] == [(1, ["a"]), (1, ["c"])]


def test_setup_uses_real_result_counts_and_wider_candidate_pool(visits):
    meta, people = visits
    rows = store.answers(RUN)
    persons = {p.uuid: p for p in people}
    res = result.summarize(meta, rows, persons)
    observed, top_existing = result_brief.scan(meta, rows, persons)
    ctx = result_brief.Ctx(RUN, {}, res, visitors=observed, top_existing=top_existing)
    assert result_brief.rule_top_barrier(ctx) and result_brief.rule_own(ctx)
    payload = group.setup(RUN)
    questions = {q["id"]: q for q in payload["questions"]}
    assert payload["demo"] is False and set(questions) == {"barrier", "own", "segment", "inflow"}
    assert f"지나친 6명 중 4명이 ‘{BARRIER}’" in questions["barrier"]["basis"]
    assert "고른 3명 중 1명" in questions["own"]["basis"]
    assert "40대 남자 응답자 5명 중 0명" in questions["segment"]["basis"]
    assert "두 매대의 답이 모두 있는 2명" in questions["inflow"]["basis"]
    people = {p["id"]: p for p in payload["candidates"]}
    assert people["v0"]["usual"] == "보리차"
    assert "usual" not in people["v3"]
    assert len(people) > len(payload["suggested"]) == 6
    assert {people[v]["picked"] for v in payload["suggested"]} == {True, False}


def test_single_real_answer_has_one_candidate_and_group_cannot_run(visits):
    row = next(r for r in store.answers(RUN) if r["visit"] == "v3" and r["cond"] == method.CONCEPT)
    store.append_answer(OTHER, row)
    payload = group.setup(OTHER)
    assert [q["id"] for q in payload["questions"]] == ["choice"]
    assert [p["id"] for p in payload["candidates"]] == ["v3"]
    assert asyncio.run(_collect(OTHER, "choice", "fgd", ["v3"])) == []
    assert asyncio.run(_collect(OTHER, "choice", "fgi", ["v3", "v4"])) == []
    assert group.setup("../run-0123456789ab") is None


async def _collect(run_id: str, question: str, mode: str, ids: list[str]) -> list[dict]:
    return [session async for session in group.discuss(run_id, question, mode, ids)]


def test_fgi_independent_and_fgd_reads_verified_prior_round(monkeypatch, visits):
    llm = FakeLLM()
    monkeypatch.setattr(group, "get_llm", lambda: llm)
    setup = group.setup(RUN)
    ids = setup["suggested"]
    fgi = asyncio.run(_collect(RUN, "barrier", "fgi", ids))
    assert [len(s["turns"]) for s in fgi] == [*range(7), 6]
    assert fgi[0]["status"] == "running" and fgi[-1]["status"] == "done"
    assert fgi[-1]["calls"] == len(llm.calls) == 6
    fgi_prompts = [json.loads(c["user"]) for c in llm.calls]
    assert all(not p["previous_others"] and not p["previous_self"] for p in fgi_prompts)
    assert {p["question"] for p in fgi_prompts} == {setup["questions"][0]["text"]}
    llm.calls.clear()

    fgd = asyncio.run(_collect(RUN, "segment", "fgd", ids))
    done = fgd[-1]
    assert [len(s["turns"]) for s in fgd] == [*range(13), 12]
    assert done["status"] == "done" and done["calls"] == len(llm.calls) == 12
    turns = {t["id"]: t for t in done["turns"]}
    prompts = [json.loads(c["user"]) for c in llm.calls]
    assert {p["question"] for p in prompts} == {done["question"]}
    assert all(not p["previous_others"] for p in prompts[:6])
    for prompt in prompts[6:]:
        others = prompt["previous_others"]
        assert len(others) == len(ids) - 1
        for ref in others:
            first = turns[ref["id"]]
            assert first["text"] == ref["text"] and first["person"] != prompt["participant"]["id"] and first["round"] == 1
    for turn in done["turns"][6:]:
        assert turn["reply_quote"] in turns[turn["reply_to"]]["text"]
    assert len({t["text"] for t in done["turns"]}) > 6
    assert done["findings"]["agreed"] and done["findings"]["split"]
    for findings in done["findings"].values():
        for finding in findings:
            assert finding["count"] == len({turns[i]["person"] for i in finding["turn_ids"]})
    assert [s["mode"] for s in group.completed(RUN)] == ["fgi", "fgd"]
    assert group.conclusions(RUN)["session_id"] == done["id"]
    assert all(q["text"] == turns[q["turn_id"]]["text"] for q in group.conclusions(RUN)["quotes"])
    assert group.get_session(OTHER, done["id"]) is None
    assert group.get_session(RUN, f"../{done['id']}") is None


def test_invalid_tasting_choice_and_unseen_quote_are_retried(monkeypatch, visits):
    valid = FakeLLM()

    class Respond:
        async def ask(self, task, system, user, schema, **kwargs):
            data = json.loads(user)
            raw = await valid.ask(task, system, user, schema, **kwargs)
            p = data["participant"]
            if not data.get("retry"):
                if data["previous_others"]:
                    return {**raw, "reply_quote": "모델이 만들어 낸 구절"}
                if p["picked"]:
                    return {**raw, "text": "직접 시음했는데 향이 좋았어요."}
                return {**raw, "text": f"오늘은 {NAME}를 골랐어요."}
            return raw

    llm = Respond()
    monkeypatch.setattr(group, "get_llm", lambda: llm)
    ids = ["v0", "v2"]
    done = asyncio.run(_collect(RUN, "barrier", "fgd", ids))[-1]
    assert done["status"] == "done" and done["calls"] == len(valid.calls) == 8
    retries = [json.loads(c["user"]).get("retry", "") for c in valid.calls]
    assert any("시음" in reason for reason in retries)
    assert any("실제로 한 선택" in reason for reason in retries)
    assert any("앞 발언" in reason for reason in retries)


def test_double_start_close_and_replay_do_not_duplicate_calls(monkeypatch, visits):
    reached, release = asyncio.Event(), asyncio.Event()
    valid = FakeLLM()

    class Hold:
        async def ask(self, task, system, user, schema, **kwargs):
            if len(valid.calls) == 1:
                reached.set()
            raw = await valid.ask(task, system, user, schema, **kwargs)
            await release.wait()
            return raw

    llm = Hold()
    monkeypatch.setattr(group, "get_llm", lambda: llm)
    ids = group.setup(RUN)["suggested"]

    async def exercise():
        first = group.discuss(RUN, "barrier", "fgi", ids)
        started = await anext(first)
        assert started["status"] == "running"
        await asyncio.wait_for(reached.wait(), timeout=2)
        duplicate = group.discuss(RUN, "barrier", "fgi", list(reversed(ids)))
        assert (await anext(duplicate))["id"] == started["id"]
        await first.aclose()
        assert len(valid.calls) == len(ids)  # 모두 같은 라운드에서 먼저 시작했다.
        release.set()
        done = [s async for s in duplicate][-1]
        assert done["status"] == "done" and done["calls"] == len(ids)
        replay = await _collect(RUN, "barrier", "fgi", ids)
        assert replay == [done] and len(valid.calls) == len(ids)
        assert group.completed(RUN) == [done]

    asyncio.run(exercise())


def test_llm_failure_keeps_only_real_turns_and_deduplicates_failed_replay(monkeypatch, visits):
    # 한 명이 ATTEMPTS번 모두 실패하면 그 사람만 빼고 확인된 발언으로 맺는다(11-25).
    valid = FakeLLM(answers={"group_turn": [LLMError] * group.ATTEMPTS})
    monkeypatch.setattr(group, "get_llm", lambda: valid)
    ids = ["v0", "v2"]
    done = asyncio.run(_collect(RUN, "barrier", "fgi", ids))[-1]
    assert done["status"] == "done" and done["calls"] == group.ATTEMPTS + 1
    assert [turn["person"] for turn in done["turns"]] == ["v2"]
    assert group.completed(RUN) == [done]
    assert asyncio.run(_collect(RUN, "barrier", "fgi", ids)) == [done]
    assert len(valid.calls) == group.ATTEMPTS + 1


def test_first_round_with_no_confirmed_answer_is_an_error(monkeypatch, visits):
    valid = FakeLLM(answers={"group_turn": [LLMError] * (2 * group.ATTEMPTS)})
    monkeypatch.setattr(group, "get_llm", lambda: valid)
    ids = ["v0", "v2"]
    done = asyncio.run(_collect(RUN, "barrier", "fgi", ids))[-1]
    assert done["status"] == "error" and done["calls"] == 2 * group.ATTEMPTS and done["turns"] == []
    assert group.completed(RUN) == [] and group.conclusions(RUN) is None
    assert asyncio.run(_collect(RUN, "barrier", "fgi", ids)) == [done]
    assert len(valid.calls) == 2 * group.ATTEMPTS


def test_resume_does_not_repeat_an_attempt_interrupted_during_the_call(monkeypatch, visits):
    valid = FakeLLM()
    monkeypatch.setattr(group, "get_llm", lambda: valid)
    setup = group.setup(RUN)
    ids = setup["suggested"][:3]
    session_id = group_store.session_id(RUN, "barrier", "fgi", ids)
    prior_id = f"{session_id}-1-1"
    outstanding_id = f"{session_id}-1-2"
    prior_turn = {"id": prior_id, "person": ids[0], "round": 1, "text": "오늘은 고르지 않았어요."}
    with group_store.claim(RUN, session_id):
        group_store.save({"run_id": RUN, "attempts": {prior_id: {"number": 1, "state": "saved"},
                                                        outstanding_id: {"number": 1, "state": "pending"}},
                          "session": {"id": session_id, "mode": "fgi", "question_id": "barrier",
                                      "question": setup["questions"][0]["text"], "participants": setup["candidates"][:3],
                                      "rounds": 1, "calls": 2, "turns": [prior_turn], "status": "running",
                                      "findings": {"agreed": [], "split": [], "changed": []}}})
    done = asyncio.run(_collect(RUN, "barrier", "fgi", ids))[-1]
    # 중단된 호출(pending)은 다시 보내지 않고 그 사람만 빼고 확인된 발언으로 맺는다
    assert done["status"] == "done" and done["calls"] == 3 and len(valid.calls) == 1
    assert [t["person"] for t in done["turns"]] == [ids[0], ids[2]]


def test_changed_finding_needs_traced_before_and_after():
    before = {"id": "before", "person": "a", "round": 1, "text": "오늘 조건이라면 지나칠래요.",
              "position": "pass", "position_quote": "지나칠래요."}
    after = {"id": "after", "person": "a", "round": 2, "text": "그 조건이면 고려해 볼래요.",
             "position": "consider", "position_quote": "고려해 볼래요.", "changed": True}
    assert group_dialogue.findings([after])["changed"] == []
    assert group_dialogue.findings([before, after])["changed"] == [{
        "text": "‘지나칠래요.’에서 ‘고려해 볼래요.’로 생각이 바뀌었어요.", "turn_ids": ["before", "after"], "count": 1}]


def test_real_shelf_run_opens_group_with_the_visited_shoppers(monkeypatch, tmp_path):
    monkeypatch.setenv("AX_LLM", "fake")
    monkeypatch.setenv("AX_ONSITE_DIR", str(tmp_path / "missing"))
    monkeypatch.setattr(store, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(store, "BASE_DIR", tmp_path / "baselines")
    monkeypatch.setattr(runner, "get_llm", lambda: llm)
    monkeypatch.setattr(group, "get_llm", lambda: llm)
    llm = FakeLLM()

    async def exercise():
        run_id = runner.create(runner.Spec("group-test", "seed", "테스트 레몬차", "캔", 250, 1800, total=30))
        await runner.TASKS[run_id]
        payload = group.setup(run_id)
        assert payload is not None and len(payload["candidates"]) > len(payload["suggested"]) == 6
        question = payload["questions"][0]
        done = (await _collect(run_id, question["id"], "fgd", payload["suggested"]))[-1]
        assert done["status"] == "done" and done["question"] == question["text"]
        assert len(done["turns"]) == 12 and done["calls"] == 12
        assert {t["person"] for t in done["turns"]} == set(payload["suggested"])
        assert {p["picked"] for p in done["participants"]} == {True, False}

    asyncio.run(exercise())
