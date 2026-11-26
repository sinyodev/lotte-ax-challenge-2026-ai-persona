"""모델 없이 사용량 수집, CLI 계측, 매대 결과 저장을 확인한다."""

import asyncio
import json
from pathlib import Path

import pytest

from llm import cli, usage
from llm.base import LLMError, LLMTimeout, TURN_CALLS
from shelftest import store, usage as shelf_usage


def _record(model="gpt-6-luna", **counts):
    entry = {"task": "견본", "model": model, "sec": 0.25, "ok": True,
             "input_tokens": 100, "output_tokens": 10, "cached_input_tokens": 40, **counts}
    usage.record(entry, system="가나다라", user="마바사", output="아자차카타")


def test_actual_zero_and_missing_tokens_are_distinct(monkeypatch):
    monkeypatch.setenv("AX_USD_KRW", "1500")
    with usage.collect() as zero:
        _record(input_tokens=0, output_tokens=0, cached_input_tokens=0)
    assert zero.summary()["estimated"] is False
    assert zero.summary()["input_tokens"] == zero.summary()["output_tokens"] == 0
    assert zero.summary()["est_cost_usd"] == zero.summary()["est_cost_krw"] == 0

    with usage.collect() as missing:
        _record(input_tokens=None, output_tokens=0, cached_input_tokens=None)
        _record(input_tokens=0, output_tokens=None, cached_input_tokens=0)
    summary = missing.summary()
    assert summary["input_tokens"] == summary["output_tokens"] == 2
    assert summary["estimated"] is True
    assert summary["cached_input_tokens"] is None
    assert summary["call_seconds"] == 0.5
    assert summary["est_cost_usd"] == pytest.approx(1.2e-6)
    assert summary["est_cost_krw"] == pytest.approx(1.2e-6 * 1500)


def test_cached_cost_uses_each_model_and_unknown_model_blocks_total(monkeypatch):
    monkeypatch.setenv("AX_USD_KRW", "NaN")
    with usage.collect() as collected:
        _record()
        _record("gpt-6.2-sol", cached_input_tokens=0)
        mixed = collected.summary()
        _record("unknown-test-model", ok=False)

    luna_cost = 11.4e-6  # (60 × $0.10 + 40 × $0.01 + 10 × $0.50) / 1M
    sol_cost = 300e-6
    assert mixed["est_cost_usd"] == pytest.approx(luna_cost + sol_cost)
    assert mixed["est_cost_krw"] == pytest.approx((luna_cost + sol_cost) * 1400)
    assert mixed["priced_as"] is None
    summary = collected.summary()
    assert summary["calls"] == 3 and summary["failed_calls"] == 1
    assert summary["input_tokens"] == 300 and summary["output_tokens"] == 30
    assert summary["cached_input_tokens"] == 80
    assert summary["est_cost_usd"] is summary["est_cost_krw"] is summary["priced_as"] is None
    assert summary["by_model"]["gpt-6-luna"]["est_cost_usd"] == pytest.approx(luna_cost)
    assert summary["by_model"]["unknown-test-model"]["est_cost_usd"] is None


def test_long_context_tier_is_selected_per_attempt():
    with usage.collect() as collected:
        _record(input_tokens=272_000, output_tokens=100, cached_input_tokens=0)
        _record(input_tokens=272_001, output_tokens=100, cached_input_tokens=272_000)
    assert collected.summary()["est_cost_usd"] == pytest.approx(
        (272_000 * 0.1 + 100 * 0.5 + 272_000 * 0.02 + 1 * 0.2 + 100 * 0.75) / 1_000_000,
    )


def test_direct_api_cost_keeps_measured_tokens_but_ignores_runner_input_and_cache():
    with usage.collect() as usual:
        _record(input_tokens=4_474, output_tokens=15, cached_input_tokens=4_096)
    with usage.collect() as direct:
        _record(input_tokens=4_474, output_tokens=15, cached_input_tokens=4_096, cost_input_tokens=34)

    summary = direct.summary()
    assert summary["input_tokens"] == usual.summary()["input_tokens"] == 4_474
    assert summary["output_tokens"] == 15 and summary["cached_input_tokens"] == 4_096
    assert summary["cost_input_tokens"] == 34
    assert summary["cost_basis"] == "direct_api_uncached_estimate"
    assert summary["estimated"] is True
    assert summary["est_cost_usd"] == pytest.approx((34 * 0.10 + 15 * 0.50) / 1_000_000)
    assert summary["est_cost_usd"] < usual.summary()["est_cost_usd"]
    model = summary["by_model"]["gpt-6-luna"]
    for name in ("input_tokens", "output_tokens", "cost_input_tokens", "cost_basis", "estimated", "est_cost_usd"):
        assert model[name] == summary[name]


def test_direct_api_cost_requires_measured_output_and_known_price():
    with usage.collect() as collected:
        _record(input_tokens=4_474, output_tokens=None, cost_input_tokens=34, ok=False)
        _record("unknown-test-model", cost_input_tokens=34)
    assert collected.summary()["est_cost_usd"] is None
    for model in collected.summary()["by_model"].values():
        assert model["est_cost_usd"] is None

    with usage.collect() as zero:
        _record(input_tokens=0, output_tokens=0, cached_input_tokens=0, cost_input_tokens=34)
    assert zero.summary()["input_tokens"] == zero.summary()["output_tokens"] == 0
    assert zero.summary()["est_cost_usd"] == pytest.approx(34 * 0.10 / 1_000_000)


def test_mixed_api_cost_bases_are_visible():
    with usage.collect() as collected:
        _record(cost_input_tokens=30)
        _record()
    summary = collected.summary()
    assert summary["cost_basis"] == summary["by_model"]["gpt-6-luna"]["cost_basis"] == "mixed"
    assert summary["cost_input_tokens"] == 130 and summary["input_tokens"] == 200


def test_nested_concurrent_and_late_tasks_are_isolated():
    async def scenario():
        release = asyncio.Event()

        async def child(value):
            await release.wait()
            _record(input_tokens=value, cached_input_tokens=0)

        async def another_run():
            with usage.collect() as own:
                await child(7)
            return own

        unrelated = asyncio.create_task(another_run())
        with usage.collect() as outer:
            early = asyncio.create_task(child(10))
            with usage.collect() as inner:
                late = asyncio.create_task(child(20))
                _record(input_tokens=30, cached_input_tokens=0)
            _record(input_tokens=40, cached_input_tokens=0)
            assert inner.summary()["calls"] == 1
        # 문맥을 나간 뒤에도 작업은 생성할 때 받은 집계에 기록한다.
        with usage.collect() as later:
            release.set()
            own, _, _ = await asyncio.gather(unrelated, early, late)
        assert (outer.summary()["calls"], outer.summary()["input_tokens"]) == (4, 100)
        assert (inner.summary()["calls"], inner.summary()["input_tokens"]) == (2, 50)
        assert (own.summary()["calls"], own.summary()["input_tokens"]) == (1, 7)
        assert later.summary()["calls"] == 0
        _record()  # 닫힌 문맥과 무관한 호출
        assert outer.summary()["calls"] == 4

    asyncio.run(scenario())


def _cli_stdout(monkeypatch, payload):
    class Process:
        async def communicate(self, _):
            return json.dumps(payload).encode(), b""

    async def spawn(*_, **__):
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)


def test_cli_records_actual_model_and_cache_breakdown(monkeypatch):
    _cli_stdout(monkeypatch, {
        "type": "result", "structured_output": {"answer": "OUTPUT_SAMPLE"},
        "usage": {"input_tokens": 50, "output_tokens": 0, "cache_read_input_tokens": 20,
                  "cache_creation_input_tokens": 30,
                  "cache_creation": {"ephemeral_1h_input_tokens": 10}},
        "modelUsage": {"claude-opus-5-5": {"inputTokens": 50, "outputTokens": 0,
                                           "cacheReadInputTokens": 20, "cacheCreationInputTokens": 30}},
    })
    responder = cli.CliLLM("opus")
    turn = []
    token = TURN_CALLS.set(turn)
    try:
        with usage.collect() as collected:
            assert asyncio.run(responder.ask("견본", "SYSTEM_SAMPLE", "USER_SAMPLE", {})) == {"answer": "OUTPUT_SAMPLE"}
    finally:
        TURN_CALLS.reset(token)
    summary = collected.summary()
    assert summary["calls"] == 1 and summary["failed_calls"] == 0
    assert summary["estimated"] is False
    assert summary["input_tokens"] == 100 and summary["output_tokens"] == 0
    assert summary["cached_input_tokens"] == 20 and summary["priced_as"] == "claude-opus-5-5"
    assert summary["est_cost_usd"] == pytest.approx((50 * 4 + 20 * 0.2 + 20 * 5 + 10 * 8) / 1_000_000)
    assert len(turn) == len(responder.log) == 1
    assert turn[0] == responder.log[0]
    assert all(text not in repr((turn, collected._attempts)) for text in ("SYSTEM_SAMPLE", "USER_SAMPLE", "OUTPUT_SAMPLE"))


def test_cli_mixed_model_failure_keeps_one_attempt_and_measured_usage(monkeypatch):
    _cli_stdout(monkeypatch, [
        {"type": "system", "subtype": "init", "model": "claude-opus-5-5"},
        {"type": "result", "is_error": True, "usage": {"input_tokens": 120, "output_tokens": 8},
         "modelUsage": {"claude-opus-5-5": {"inputTokens": 100, "outputTokens": 5},
                        "claude-sonnet-5-5": {"inputTokens": 20, "outputTokens": 3}}},
    ])
    responder = cli.CliLLM()
    with usage.collect() as collected, pytest.raises(LLMError):
        asyncio.run(responder.ask("견본", "가", "나", {}))
    summary = collected.summary()
    assert summary["calls"] == summary["failed_calls"] == len(responder.log) == 1
    assert summary["input_tokens"] == 120 and summary["output_tokens"] == 8
    assert summary["by_model"]["claude-sonnet-5-5"]["input_tokens"] == 20
    assert summary["priced_as"] is None
    assert summary["est_cost_usd"] == pytest.approx(570e-6)


@pytest.mark.parametrize("reason", ["cancelled", "timeout", "subprocess"])
def test_cli_records_interrupted_attempt_and_cleans_workdir(monkeypatch, reason):
    async def scenario():
        began = asyncio.Event()
        killed = []
        workdirs = []

        class Process:
            async def communicate(self, _):
                began.set()
                await asyncio.Future()

            async def wait(self):
                return -9

        async def spawn(*_, cwd, **__):
            workdirs.append(Path(cwd))
            if reason == "subprocess":
                raise FileNotFoundError()
            return Process()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
        monkeypatch.setattr(cli, "_kill", killed.append)
        responder = cli.CliLLM("claude-opus-5-5")
        turn = []
        token = TURN_CALLS.set(turn)
        try:
            with usage.collect() as collected:
                task = asyncio.create_task(responder.ask("견본", "가나다라", "마바사", {}, timeout=0.01))
                error = {"cancelled": asyncio.CancelledError, "timeout": LLMTimeout, "subprocess": LLMError}[reason]
                if reason == "cancelled":
                    await began.wait()
                    task.cancel()
                with pytest.raises(error):
                    await task
        finally:
            TURN_CALLS.reset(token)
        summary = collected.summary()
        assert summary["calls"] == summary["failed_calls"] == len(turn) == 1
        assert summary["estimated"] is True
        assert summary["input_tokens"] == 2 and summary["output_tokens"] == 0
        assert turn[0]["why"] == reason
        assert len(killed) == (0 if reason == "subprocess" else 1)
        assert len(workdirs) == 1 and not workdirs[0].exists()

    asyncio.run(scenario())


def test_shelf_run_usage_persists_totals_and_hides_partial_cost(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "RUNS_DIR", tmp_path)
    monkeypatch.setenv("AX_USD_KRW", "1500")
    run_id = "run-000000000001"
    measured = shelf_usage.RunUsage(run_id)
    with measured.call():
        _record(ok=False)
        _record()
    with measured.call():
        _record()
    view = shelf_usage.view(run_id)
    assert view["calls"] == 3 and view["input_tokens"] == 300 and view["output_tokens"] == 30
    assert view["priced_as"] == "gpt-6-luna"
    assert view["est_cost_usd"] == pytest.approx(3 * 11.4e-6)
    assert view["est_cost_krw"] == pytest.approx(3 * 11.4e-6 * 1500)

    with measured.call():
        _record("gpt-6.1-terra")
    mixed = shelf_usage.view(run_id)
    assert mixed["calls"] == 4 and mixed["priced_as"] is None
    assert mixed["est_cost_usd"] == pytest.approx(3 * 11.4e-6 + 112e-6)

    with measured.call():
        _record("unknown-test-model")
    partial = shelf_usage.view(run_id)
    assert partial["calls"] == 5 and partial["input_tokens"] == 500 and partial["output_tokens"] == 50
    assert partial["est_cost_usd"] is partial["est_cost_krw"] is partial["priced_as"] is None

    with measured.call():
        pass  # 계측하지 않는 응답기도 호출 수는 기록한다.
    incomplete = shelf_usage.view(run_id)
    assert incomplete["calls"] == 6
    assert all(incomplete[key] is None for key in shelf_usage.METRICS)
