"""멈춘 매대 테스트(11-25): 멈추면 칠성이가 지금까지의 답으로 결과를 말하고, 이어서 돌릴 수 있다. fake 어댑터만 쓴다."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from agent import explore, machine
from agent import phrases as P
from evals.test_open import Chat, card, fake, ideas_now, read_ans, reply_of, says, task, with_ideas  # noqa: F401
from shelftest import runner, store
from tools.consumer import Group
from tests.test_result_say import said, view as fake_view


@pytest.fixture(autouse=True)
def small_tests(monkeypatch):
    monkeypatch.setenv("AX_SHELF_TOTAL", "20")


def _keep(run_id: str, n: int) -> None:
    """저장된 답 가운데 앞의 n명만 남겨 '중간에 멈춘' 테스트를 만든다."""
    import json

    rows = store.answers(run_id)
    visits: list[str] = []
    for r in rows:
        if r.get("visit") and r["visit"] not in visits:
            visits.append(r["visit"])
    keep = set(visits[:n])
    kept = [r for r in rows if r.get("visit") in keep]
    store._answers_path(run_id).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept),
                                           encoding="utf-8")
    meta = store.load_meta(run_id)
    meta["status"] = "stopped"
    store.save_meta(meta)


def _target_run(chat: Chat) -> str:
    t = with_ideas(chat)
    a = ideas_now(t)[0]["id"]
    chat.send("A로 컨셉 만들자", read=read_ans(task("concepts", ids=[a])))
    note = machine.CONVS[chat.id]
    note.group, note.occasion_code = Group(age="19-29", label="20대"), "D7"
    chat.send(P.BTN_SHELF)
    chat.send("바로 타깃 테스트", ["explore-skip"])
    with patch.object(runner, "_start", lambda run_id: None):
        t = chat.send(P.BTN_SHELF_START, ["shelf-start"])
    return card(t, "shelf-run").payload["run_id"]


def test_stopped_target_run_speaks_so_far_and_opens_result(fake):
    chat = Chat(fake)
    run_id = _target_run(chat)
    asyncio.run(runner._run(run_id))
    _keep(run_id, 7)
    v = runner.view(run_id)
    assert v["status"] == "stopped" and v["asked"] == 7
    t = chat.send(P.BTN_STOPPED_RESULT)
    text = says(t)
    assert text.startswith("20명 중 7명에서 멈췄어요. 지금까지의 결과예요.")
    assert P.FEW_ANSWERS in text and P.RESULT_DONE not in text
    assert card(t, "result")


def test_stopped_target_run_with_no_answers_opens_nothing(fake):
    chat = Chat(fake)
    run_id = _target_run(chat)
    runner.stop(run_id)
    t = chat.send(P.BTN_STOPPED_RESULT)
    assert says(t) == P.STOPPED_EMPTY
    assert not [e for e in t if getattr(e, "kind", None) == "result"]


def test_resume_runs_only_the_rest(fake):
    chat = Chat(fake)
    run_id = _target_run(chat)
    asyncio.run(runner._run(run_id))
    _keep(run_id, 5)
    before = len(store.answers(run_id))
    with patch.object(runner, "_start", lambda rid: None):
        assert runner.resume(run_id) is True
        assert runner.resume(run_id) is False  # 이미 돌고 있음
    asyncio.run(runner._run(run_id))
    v = runner.view(run_id)
    assert v["status"] == "done" and v["asked"] == 20
    kept = store.answers(run_id)[:before]
    assert len({r["visit"] for r in kept if r.get("visit")}) == 5  # 앞의 답은 그대로 남는다


def test_stopped_explore_gives_so_far_and_no_conclusion_when_few(fake, monkeypatch):
    monkeypatch.setenv("AX_EXPLORE_PER_CELL", "2")
    monkeypatch.setattr(runner, "_start", lambda run_id: None)
    chat = Chat(fake)
    idea_id = ideas_now(with_ideas(chat))[0]["id"]
    chat.send("컨셉 만들자", read=read_ans(task("concepts", ids=[idea_id])))
    note = machine.CONVS[chat.id]
    note.group = Group(age="19-29", sex="여자")
    entry = chat.send(P.BTN_SHELF)
    start = reply_of(entry).actions[0]
    run = card(chat.send(start.label, [start.id]), "explore").payload["run_id"]
    asyncio.run(runner._run(run))
    _keep(run, 6)
    t = chat.send(P.BTN_STOPPED_RESULT, ["explore-result", run])
    text = says(t)
    assert text.startswith("16명 중 6명에서 멈췄어요. 지금까지의 결과예요.") and P.FEW_ANSWERS in text
    options = reply_of(t).options
    assert options[0].id.endswith("/board") and options[-1].id.endswith("/ages")


def test_stopped_explore_with_no_answers(fake, monkeypatch):
    monkeypatch.setenv("AX_EXPLORE_PER_CELL", "2")
    monkeypatch.setattr(runner, "_start", lambda run_id: None)
    chat = Chat(fake)
    idea_id = ideas_now(with_ideas(chat))[0]["id"]
    chat.send("컨셉 만들자", read=read_ans(task("concepts", ids=[idea_id])))
    entry = chat.send(P.BTN_SHELF)
    start = reply_of(entry).actions[0]
    run = card(chat.send(start.label, [start.id]), "explore").payload["run_id"]
    runner.stop(run)
    assert says(chat.send(P.BTN_STOPPED_RESULT, ["explore-result", run])) == P.STOPPED_EMPTY


def test_stopped_explore_with_enough_answers_uses_axes():
    from agent.note import Note

    spec = runner.Spec("chat", "a", "밀키스 화채", "슬림캔", 250, 1200, age="19-29", sex="여자", total=300)
    groups = lambda keys: [{"key": k, "label": k, "n": 40, "picked": 4, "rate": 10.0} for k in keys]  # noqa: E731
    study = {"cells": [{"age": a, "sex": s, "n": 20, "picked": 2, "rate": 10.0} for a, s in explore.CELLS],
             "overlap": True, "suggested": None,
             "axes": {"sex": {"groups": groups(["남자", "여자"]), "clear": False},
                      "age": {"groups": groups(["19-29", "30-39", "40-49", "50-59"]), "clear": False}}}
    text = says(explore._offer_targets(Note(), "r", study, spec, lead=P.stopped_line(160, 320)))
    assert text.startswith("320명 중 160명에서 멈췄어요. 지금까지의 결과예요. ") and P.FEW_ANSWERS not in text


def test_stopped_result_bits_drop_done_and_insights_when_few():
    turn, text = said(fake_view(status="stopped", asked=12, n=12, k=2))
    assert P.RESULT_DONE not in text and text.endswith(P.FEW_ANSWERS) and "일 때" not in text
    turn, text = said(fake_view(status="stopped", asked=120, n=120, k=30))
    assert P.RESULT_DONE not in text and "일 때" in text
