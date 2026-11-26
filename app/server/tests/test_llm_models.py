import pytest

from agent.steps import fast_model
from agent.voice import voice_model
from llm.models import ModelChoice, model_for, role_for_task
from shelftest.runner import shopper_model


@pytest.fixture(autouse=True)
def clear_settings(monkeypatch):
    for role in ("READ", "PLAN", "SHOPPER", "INTERVIEW", "VOICE"):
        monkeypatch.delenv(f"AX_MODEL_{role}", raising=False)
        monkeypatch.delenv(f"AX_EFFORT_{role}", raising=False)
    for var in ("AX_LLM", "AX_CLI_MODEL", "AX_SHOPPER_MODEL", "AX_VOICE_MODEL"):
        monkeypatch.delenv(var, raising=False)


def test_cli_and_fake_keep_current_model_defaults(monkeypatch):
    for backend in ("cli", "fake"):
        monkeypatch.setenv("AX_LLM", backend)
        assert shopper_model() == "claude-opus-5-5"
        assert voice_model() == fast_model() == "sonnet"
        assert model_for("plan") == ModelChoice("claude-opus-5-5")
        assert model_for("interview") == model_for("shopper")
    monkeypatch.setenv("AX_CLI_MODEL", "fixture-plan")
    monkeypatch.setenv("AX_SHOPPER_MODEL", "fixture-shopper")
    monkeypatch.setenv("AX_VOICE_MODEL", "fixture-voice")
    assert shopper_model() == model_for("interview").model == "fixture-shopper"
    assert voice_model() == fast_model() == "fixture-voice"
    assert model_for("plan").model == "fixture-plan"


@pytest.mark.parametrize("backend", ["codex", "openai"])
def test_gpt_settings_override_legacy_per_role(monkeypatch, backend):
    monkeypatch.setenv("AX_LLM", backend)
    monkeypatch.setenv("AX_CLI_MODEL", "claude-fixture")
    assert model_for("plan") == ModelChoice("gpt-6.2-sol", "low")
    assert model_for("shopper") == ModelChoice("gpt-6-luna", "low")
    assert shopper_model() == "gpt-6-luna"
    monkeypatch.setenv("AX_VOICE_MODEL", "fixture-legacy")
    monkeypatch.setenv("AX_SHOPPER_MODEL", "fixture-legacy-shopper")
    monkeypatch.setenv("AX_MODEL_READ", "fixture-read")
    monkeypatch.setenv("AX_MODEL_SHOPPER", "fixture-shopper")
    monkeypatch.setenv("AX_MODEL_INTERVIEW", "fixture-interview")
    monkeypatch.setenv("AX_EFFORT_INTERVIEW", "high")
    assert fast_model() == "fixture-read"
    assert voice_model() == "fixture-legacy"
    assert shopper_model() == "fixture-shopper"
    assert model_for("interview") == ModelChoice("fixture-interview", "high")


@pytest.mark.parametrize(("task", "role"), [
    ("read", "read"), ("read_first", "read"), ("pod", "read"), ("improve_extract", "read"),
    ("ideas", "plan"), ("trend", "plan"), ("concepts", "plan"), ("improve", "plan"), ("proposal", "plan"),
    ("shopper", "shopper"), ("interview", "interview"), ("group_turn", "interview"), ("voice", "voice"),
])
def test_task_role(task, role):
    assert role_for_task(task) == role


def test_cli_uses_role_overrides_for_plan_and_interview(monkeypatch):
    import asyncio

    from llm.cli import CliLLM

    commands = []

    class Process:
        async def communicate(self, message):
            return b'{"type":"result","structured_output":{}}', b""

    async def spawn(*args, **kwargs):
        commands.append(args)
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setenv("AX_MODEL_PLAN", "fixture-plan")
    monkeypatch.setenv("AX_MODEL_INTERVIEW", "fixture-interview")
    monkeypatch.setenv("AX_EFFORT_INTERVIEW", "high")
    responder = CliLLM()
    asyncio.run(responder.ask("ideas", "지침", "견본", {}))
    asyncio.run(responder.ask("interview", "지침", "견본", {}, model=model_for("shopper", backend="cli").model))
    assert commands[0][commands[0].index("--model") + 1] == "fixture-plan"
    assert commands[1][commands[1].index("--model") + 1] == "fixture-interview"
    assert commands[1][commands[1].index("--effort") + 1] == "high"
