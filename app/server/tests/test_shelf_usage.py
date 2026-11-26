"""실행별 호출 수, 비용, 정지·재개와 옛 기록 조회를 확인한다."""

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from types import SimpleNamespace

import pytest
from test_explore_engine import finish, panel, spec  # noqa: F401

from llm.base import LLMError, set_llm
from shelftest import method, runner, store, usage


def test_fallback_counts_retries_and_only_uncached_calls(panel, monkeypatch):
    _, fake = panel
    monkeypatch.setattr(usage, "model_usage", None)
    answer = fake.answers["shopper"]
    fake.answers["shopper"] = [LLMError("실패"), {"choice_number": 99}, answer, answer]

    async def scenario():
        first = await finish(spec(age="19-29", sex="여자", total=1))
        assert await finish(spec(age="19-29", sex="여자", total=1)) == first
        fake.answers["shopper"] = answer
        cached = await finish(spec(age="19-29", sex="여자", total=1, price=1400))
        return first, cached

    first, cached = asyncio.run(scenario())
    assert len(fake.calls) == 5
    first_usage = runner.view(first)["usage"]
    assert first_usage == {"elapsed_s": first_usage["elapsed_s"], "calls": 4, "input_tokens": None,
                           "output_tokens": None, "est_cost_krw": None, "est_cost_usd": None, "priced_as": None}
    assert runner.view(cached)["usage"]["calls"] == 1
    assert sum(1 for row in store.answers(cached) if row.get("reused")) == 1


def test_w0_summary_accounts_for_adapter_retries_and_keeps_runs_separate(panel, monkeypatch):
    _, fake = panel
    answer = fake.answers["shopper"]
    local: ContextVar[dict] = ContextVar("test_model_usage")

    @contextmanager
    def collect():
        summary = {}
        token = local.set(summary)
        try:
            yield SimpleNamespace(summary=lambda: summary)
        finally:
            local.reset(token)

    def recorded(system, user, schema):
        priced = user.startswith("sample-0")
        calls = 2 if "new_product" in schema["properties"] else 1
        local.get().update(calls=calls, input_tokens=3 * calls, output_tokens=2 * calls,
                           est_cost_krw=10 * calls if priced else None,
                           est_cost_usd=0.01 * calls if priced else None, priced_as="견본" if priced else None)
        return answer(system, user, schema)

    fake.answers["shopper"] = recorded
    monkeypatch.setattr(usage, "model_usage", SimpleNamespace(collect=collect))

    async def scenario():
        return await asyncio.gather(finish(spec(age="19-29", sex="여자", total=1)),
                                    finish(spec(age="19-29", sex="남자", total=1)))

    usd, unpriced = asyncio.run(scenario())
    priced = runner.view(usd)["usage"]
    assert priced["calls"] == 3 and priced["input_tokens"] == 9 and priced["output_tokens"] == 6
    assert priced["est_cost_usd"] == pytest.approx(0.03) and priced["est_cost_krw"] == 30
    assert priced["priced_as"] == "견본"
    other = runner.view(unpriced)["usage"]
    assert other["calls"] == 3 and other["input_tokens"] == 9 and other["output_tokens"] == 6
    assert other["est_cost_usd"] is other["est_cost_krw"] is other["priced_as"] is None


@pytest.mark.parametrize("stop", [True, False])
def test_elapsed_excludes_stopped_time_and_reopens_same_plan(panel, monkeypatch, stop):
    people, fake = panel
    monkeypatch.setattr(usage, "model_usage", None)
    clock = [0.0]
    monkeypatch.setattr(usage, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    s = spec(age="19-29", sex="여자", total=2, occasion_code="D1")

    async def scenario():
        began = asyncio.Event()

        class Blocking:
            async def ask(self, *args, **kwargs):
                began.set()
                await asyncio.Future()

        set_llm(Blocking())
        run_id = runner.create(s)
        await began.wait()
        initial = store.load_meta(run_id)["participants"]
        clock[0] = 3.5
        live = runner.view(run_id)["usage"]
        assert live["elapsed_s"] == 3.5 and live["calls"] == 2
        task = runner.TASKS[run_id]
        if stop:
            assert runner.stop(run_id)
        else:
            task.cancel()  # 서버 종료 때는 running으로 보존한다.
        await asyncio.gather(task, return_exceptions=True)
        clock[0] = 135.0
        assert usage.view(run_id)["elapsed_s"] == 3.5

        set_llm(fake)
        if stop:
            assert runner.create(s) == run_id
        else:
            people.reverse()
            assert runner.view(run_id)["status"] == "running"
        clock[0] = 136.5
        await runner.TASKS[run_id]
        v = runner.view(run_id)
        assert v["status"] == "done" and v["asked"] == 2 and v["usage"]["elapsed_s"] == 5.0
        assert v["usage"]["calls"] == 6 and len(fake.calls) == 4
        assert initial == store.load_meta(run_id)["participants"]
        actual = {(r["visit"], r["uuid"], r["occasion"]) for r in store.answers(run_id)}
        assert actual == {(p["visit"], p["uuid"], p["occasion"]) for p in initial}

    asyncio.run(scenario())


def test_old_record_has_no_usage_and_retains_known_cohort(panel):
    first = asyncio.run(finish(spec(age="19-29", sex="여자", total=2)))
    old = store.load_meta(first)
    participants = old["participants"]
    for field in ("usage_version", "participants", "mode", "placement", "shelf_products"):
        old.pop(field)
    store.save_meta(old)
    people, _ = panel
    people.reverse()

    v = runner.view(first)
    assert v["status"] == "done" and v["asked"] == 2 and v["requested"] == 2
    assert v["placement"] is None and "usage" not in v
    changed = runner.apply_change(spec(age="19-29", sex="여자", total=2), {"price": 1500})
    new = asyncio.run(finish(changed))
    assert store.load_meta(new)["participants"] == participants
    assert runner.view(new)["usage"]["calls"] == 2


def test_completed_run_without_calendar_reopens_after_calendar_is_enabled(panel, monkeypatch):
    run_id = asyncio.run(finish(spec(age="19-29", sex="여자", total=2)))
    old = store.load_meta(run_id)
    assert "visit_months" not in old and all("visit_month" not in p for p in old["participants"])
    before = runner.view(run_id)
    monkeypatch.setenv("AX_LLM", "codex")
    monkeypatch.setenv("AX_SHOPPER_ROUND", "6")
    reopened = runner.view(run_id)
    assert reopened["status"] == "done" and reopened["asked"] == before["asked"] == 2
    assert "visit_months" not in reopened and store.load_meta(run_id) == old


def test_truncated_journal_record_preserves_subsequent_entries(panel):
    run_id = asyncio.run(finish(spec(age="19-29", sex="여자", total=1)))
    path = store.RUNS_DIR / f"{run_id}.jsonl"
    with path.open("ab") as stream:
        stream.write(b'{"unfinished": "\xed\x95')
    store.append_answer(run_id, {"visit": "T999", "skip": True})
    assert [r["cond"] for r in store.answers(run_id)[:-1]] == [method.CONCEPT, method.BASELINE]
    assert store.answers(run_id)[-1] == {"visit": "T999", "skip": True}
