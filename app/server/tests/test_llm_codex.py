import asyncio
import json
import signal
from pathlib import Path

import pytest

from llm import base, codex, usage
from llm.base import LLMError, LLMTimeout, TURN_CALLS
from llm.models import ModelChoice


SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}, "example": {"type": "integer"}},
    "required": ["text"],
    "additionalProperties": False,
}


def _events(*items, text='{"text":"꾸민 답", "example":null}', tokens=True):
    events = [{"type": "item.completed", "item": {"type": kind}} for kind in items]
    events.append({"type": "item.completed", "item": {"type": "agent_message", "text": text}})
    completed = {"type": "turn.completed"}
    if tokens:
        completed["usage"] = {"input_tokens": 450, "output_tokens": 15, "cached_input_tokens": 32}
    events.append(completed)
    return "\n".join(json.dumps(e) for e in events).encode()


@pytest.fixture
def fixture_login(monkeypatch, tmp_path):
    home = tmp_path / "fixture-login"
    home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setattr(codex.shutil, "which", lambda name: f"/fixture/{name}")
    monkeypatch.setattr(codex.sys, "platform", "darwin")
    return home


def test_isolation_and_search_config(monkeypatch, tmp_path, fixture_login):
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("CODEX_ACCESS_TOKEN", "fixture-token")
    monkeypatch.setenv("CODEX_EXEC_SERVER_URL", "https://example.invalid")
    root = tmp_path / "run"
    root.mkdir()
    command, env, cwd = codex._prepare(root, ModelChoice("fixture-model", "low"), "꾸민 지침", SCHEMA, True)

    assert command[0] == "/usr/bin/sandbox-exec"
    assert "deny file-write*" in command[6]
    assert "--ignore-user-config" in command and "--ignore-rules" in command and "--ephemeral" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    configs = {command[i + 1] for i, item in enumerate(command) if item == "-c"}
    assert {'forced_login_method="chatgpt"', 'web_search="live"', "project_doc_max_bytes=0", "mcp_servers={}"} <= configs
    assert {"shell_tool", "view_image", "plugins", "apps", "hooks"} <= {
        command[i + 1] for i, item in enumerate(command) if item == "--disable"
    }
    assert env["CODEX_EXEC_SERVER_URL"] == "none"
    assert not {"OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_ACCESS_TOKEN"} & env.keys()
    isolated = Path(env["CODEX_HOME"])
    assert [file.name for file in isolated.iterdir()] == ["auth.json"]
    assert (isolated / "auth.json").readlink() == fixture_login / "auth.json"
    assert list(cwd.iterdir()) == []
    assert "꾸민 지침" not in command
    assert (root / "instructions.txt").read_text(encoding="utf-8") == "꾸민 지침"
    assert json.loads((root / "schema.json").read_text())["required"] == ["text", "example"]


def test_schema_keeps_required_null_and_restores_nested_optional_fields():
    inner = {"type": "object", "properties": {"a": {"type": ["string", "null"]}, "b": {"type": "integer"}},
             "required": ["a"]}
    schema = {"type": "object", "properties": {"rows": {"type": "array", "items": inner}}, "required": ["rows"]}
    child = codex._strict_schema(schema)["properties"]["rows"]["items"]
    assert child["required"] == ["a", "b"]
    assert child["additionalProperties"] is False
    assert child["properties"]["b"] == {"anyOf": [{"type": "integer"}, {"type": "null"}]}
    assert inner["required"] == ["a"]
    assert codex._restore_optional({"rows": [{"a": None, "b": None}, {"a": "값", "b": 1}]}, schema) == {
        "rows": [{"a": None}, {"a": "값", "b": 1}]
    }


def test_real_entry_point_uses_interview_model_and_records_once(monkeypatch, fixture_login):
    monkeypatch.setenv("AX_LLM", "codex")
    monkeypatch.setenv("AX_MODEL_SHOPPER", "fixture-shopper")
    monkeypatch.setenv("AX_MODEL_INTERVIEW", "fixture-interview")
    monkeypatch.setenv("AX_EFFORT_INTERVIEW", "high")
    monkeypatch.setattr(base, "_current", None)
    records = []

    async def run(command, env, cwd, user, timeout):
        assert command[command.index("--model") + 1] == "fixture-interview"
        assert 'model_reasoning_effort="high"' in command
        assert 'web_search="disabled"' in command
        assert user == "꾸민 문의"
        return 0, _events(), b""

    real_record = usage.record

    def record(entry, **inputs):
        records.append((entry, inputs))
        real_record(entry, **inputs)

    monkeypatch.setattr(codex, "_run", run)
    monkeypatch.setattr(usage, "record", record)
    llm = base.get_llm()
    assert isinstance(llm, codex.CodexLLM)
    token = TURN_CALLS.set([])
    try:
        with usage.collect() as meter:
            result = asyncio.run(llm.ask("interview", "꾸민 지침", "꾸민 문의", SCHEMA,
                                         model="fixture-shopper", web=True))
        assert result == {"text": "꾸민 답"}
        assert meter.summary()["calls"] == 1
        assert TURN_CALLS.get() == llm.log
    finally:
        TURN_CALLS.reset(token)
    assert len(records) == 1
    entry, inputs = records[0]
    assert entry["cost_input_tokens"] > 0
    assert {key: value for key, value in entry.items() if key != "cost_input_tokens"} == {
        "task": "interview", "model": "fixture-interview", "sec": entry["sec"], "ok": True,
        "input_tokens": 450, "output_tokens": 15, "cached_input_tokens": 32,
    }
    assert inputs == {"system": "꾸민 지침", "user": "꾸민 문의", "output": '{"text":"꾸민 답", "example":null}'}


def test_direct_api_cost_counts_korean_and_the_strict_schema(monkeypatch, fixture_login):
    async def run(*args):
        return 0, _events(), b""

    monkeypatch.setattr(codex, "_run", run)
    llm = codex.CodexLLM()
    system = "꾸민 지침"
    short, long = "answer now", "여름 정원에서 고를 화분을 아래 조건에 맞춰 하나 선택합니다."

    def measure(prompt):
        with usage.collect() as meter:
            asyncio.run(llm.ask("shopper", system, prompt, SCHEMA, model="gpt-6-luna"))
        return meter.summary()

    short_usage, long_usage = measure(short), measure(long)
    assert short_usage["input_tokens"] == long_usage["input_tokens"] == 450
    assert short_usage["output_tokens"] == long_usage["output_tokens"] == 15
    assert 0 < short_usage["cost_input_tokens"] < long_usage["cost_input_tokens"] < 450
    strict = codex._strict_schema(SCHEMA)
    expected = usage.estimate_direct_api_input(system, long, strict)
    assert expected > usage.estimate_direct_api_input(system, long, SCHEMA)
    assert usage.estimate_direct_api_input("가가가가", "", strict) > usage.estimate_direct_api_input("aaaa", "", strict)
    assert long_usage["cost_input_tokens"] == expected
    assert long_usage["est_cost_usd"] == pytest.approx((expected * 0.10 + 15 * 0.50) / 1_000_000)
    assert short_usage["est_cost_usd"] < long_usage["est_cost_usd"]
    assert all("cost_input_tokens" not in entry for entry in llm.log)


@pytest.mark.parametrize(("failures", "timeout", "outcome", "expected"),
                         [(2, 10, "success", 3), (3, 10, "workspace_config", 3), (1, .1, "timeout", 1)])
def test_workspace_config_retry_within_one_deadline(monkeypatch, fixture_login, failures, timeout, outcome, expected):
    budgets, delays = [], []

    async def run(command, env, cwd, user, remaining):
        budgets.append(remaining)
        if len(budgets) <= failures:
            return 1, b"", b"Error: Failed to load cloud config bundle (workspace-managed policies)."
        return 0, _events(), b""

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(codex, "_run", run)
    monkeypatch.setattr(codex.asyncio, "sleep", sleep)
    monkeypatch.setattr(codex.random, "uniform", lambda a, b: (a+b)/2)
    llm = codex.CodexLLM()
    with usage.collect() as meter:
        call = llm.ask("read", "꾸민 지침", "꾸민 문의", SCHEMA, timeout=timeout, model="gpt-6.2-sol")
        if outcome == "success":
            assert asyncio.run(call) == {"text": "꾸민 답"}
        elif outcome == "timeout":
            with pytest.raises(LLMTimeout):
                asyncio.run(call)
        else:
            with pytest.raises(LLMError, match="workspace_config"):
                asyncio.run(call)
    assert meter.summary()["calls"] == expected == len(budgets)
    assert delays == pytest.approx([.6, 1.2][:expected-1])
    assert all(0 < sec <= timeout for sec in budgets)
    assert budgets == sorted(budgets, reverse=True)
    assert meter.summary()["output_tokens"] == (15 if outcome == "success" else 0)
    assert meter.summary()["est_cost_usd"] is not None


@pytest.mark.parametrize(("task", "web", "item", "success"), [
    ("trend", True, "web_search", True), ("trend", False, "web_search", False),
    ("shopper", True, "web_search", False), ("trend", True, "command_execution", False),
    ("read", False, "file_change", False), ("plan", False, "mcp_tool_call", False),
])
def test_only_trend_can_search(monkeypatch, fixture_login, task, web, item, success):
    async def run(command, env, cwd, user, timeout):
        assert f'web_search="{"live" if task == "trend" and web else "disabled"}"' in command
        return 0, _events(item), b""

    monkeypatch.setattr(codex, "_run", run)
    llm = codex.CodexLLM()
    call = llm.ask(task, "꾸민 지침", "꾸민 문의", SCHEMA, web=web)
    if success:
        assert asyncio.run(call) == {"text": "꾸민 답"}
    else:
        with pytest.raises(LLMError, match="unexpected_tool"):
            asyncio.run(call)
    assert llm.log[0]["ok"] == success


@pytest.mark.parametrize(("status", "out", "err", "reason"), [
    (1, b'{}', b'401 Unauthorized, fixture-key stays private', "authentication"),
    (1, b'{"type":"turn.failed"}', b'invalid_json_schema fixture prompt', "schema"),
    (0, _events(text="fixture invalid JSON"), b'', "unreadable"),
    (0, b'{"type":"turn.failed"}', b'', "cli_exit"),
])
def test_failed_calls_strip_raw_errors(monkeypatch, fixture_login, status, out, err, reason):
    async def run(*args):
        return status, out, err

    monkeypatch.setattr(codex, "_run", run)
    llm = codex.CodexLLM()
    with usage.collect() as meter, pytest.raises(LLMError) as caught:
        asyncio.run(llm.ask("read", "꾸민 지침", "꾸민 문의", SCHEMA))
    assert "fixture" not in str(caught.value)
    assert llm.log[0]["why"] == reason
    assert llm.log[0]["ok"] is False
    assert meter.summary()["calls"] == 1


@pytest.mark.parametrize("cancel_during_spawn", [False, True])
def test_reaps_process_group_on_timeout_and_cancel(monkeypatch, fixture_login, cancel_during_spawn):
    llm = codex.CodexLLM()
    killed = []

    async def run():
        spawning = asyncio.Event()
        release = asyncio.Event()

        class Process:
            pid = 12345

            async def communicate(self, stdin=None):
                if stdin is not None:
                    await asyncio.Future()
                return b"", b""

        async def spawn(*args, **kwargs):
            assert kwargs["start_new_session"] is True
            spawning.set()
            if cancel_during_spawn:
                await release.wait()
            return Process()

        monkeypatch.setattr(codex.asyncio, "create_subprocess_exec", spawn)
        monkeypatch.setattr(codex.os, "killpg", lambda pid, sig: killed.append((pid, sig)))
        task = asyncio.create_task(llm.ask("read", "꾸민 지침", "꾸민 문의", SCHEMA,
                                           timeout=30 if cancel_during_spawn else 0.02))
        await spawning.wait()
        if cancel_during_spawn:
            task.cancel()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(LLMTimeout):
                await task

    with usage.collect() as meter:
        asyncio.run(run())
    assert killed == [(12345, signal.SIGKILL)]
    assert len(llm.log) == meter.summary()["calls"] == 1
    assert llm.log[0]["why"] == ("cancelled" if cancel_during_spawn else "timeout")
