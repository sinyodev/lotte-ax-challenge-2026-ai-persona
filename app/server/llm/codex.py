"""저장된 Codex CLI 워크스페이스 로그인으로 구조화된 앱 응답을 받는다."""

from __future__ import annotations

import asyncio
import json
import os
import random
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from llm.base import LLMError, LLMTimeout, note_call
from llm.models import ModelChoice, choice_for_call
from llm.schema import _restore_optional, _strict_schema

# codex-cli 0.172.0의 exec --help, features list, config.schema.json 기준.
_DISABLED_FEATURES = (
    "shell_tool", "shell_snapshot", "view_image", "hooks", "plugins", "apps",
    "browser_use", "computer_use", "image_generation", "multi_agent", "multi_agent_v2",
    "goals", "tool_suggest", "workspace_dependencies", "unbounded_connection_retries",
)
_CONFIG = (
    'model_provider="openai"', 'forced_login_method="chatgpt"', 'cli_auth_credentials_store="file"',
    'approval_policy="never"', 'mcp_servers={}', 'plugins={}', 'project_doc_max_bytes=0',
    'include_environment_context=false', 'include_permissions_instructions=false',
    'include_collaboration_mode_instructions=false', 'include_apps_instructions=false',
    'skills.include_instructions=false', 'skills.bundled.enabled=false', 'tools.update_plan.enabled=false',
    'analytics.enabled=false', 'otel.log_user_prompt=false',
)

# CLI가 임시 CODEX_HOME에서 auth.json 링크로 기존 로그인을 사용한다. 인증 원본은
# CLI 내부의 토큰 갱신이나 로그아웃이 시도돼도 이 프로세스가 고칠 수 없다.
_MAC_SANDBOX = """(version 1)
(allow default)
(deny file-write* (subpath (param "LOGIN_HOME")) (literal (param "LOGIN_FILE")))
"""

_TOKEN_KEYS = ("input_tokens", "output_tokens", "cached_input_tokens")
_TOOL_EVENTS = {"command_execution", "file_change", "mcp_tool_call", "collab_tool_call"}


class _WorkspaceConfigUnavailable(LLMError):
    """CLI가 모델 호출 전에 관리 정책 설정을 가져오지 못했다."""


class CodexLLM:
    def __init__(self) -> None:
        self.log: list[dict[str, Any]] = []

    async def ask(self, task: str, system: str, user: str, schema: dict[str, Any], *,
                  web: bool = False, timeout: float = 60.0, model: str | None = None) -> dict[str, Any]:
        choice = choice_for_call(task, model, backend="codex")
        allow_web = task == "trend" and web
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        for attempt in range(3):
            try:
                return await self._attempt(task, system, user, schema, choice, allow_web, deadline)
            except _WorkspaceConfigUnavailable:
                if attempt == 2:
                    raise
                delay = random.uniform(0.4, 0.8) * 2 ** attempt
                if loop.time() + delay >= deadline:
                    raise LLMTimeout(f"{task}: Codex 재시도 시간이 부족해요") from None
                await asyncio.sleep(delay)

    async def _attempt(self, task: str, system: str, user: str, schema: dict[str, Any],
                       choice: ModelChoice, allow_web: bool, deadline: float) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        started = loop.time()
        entry: dict[str, Any] = {"task": task, "model": choice.model, "ok": False}
        output_text = ""
        try:
            with tempfile.TemporaryDirectory(prefix="chilseong-codex-", dir="/tmp") as temp:
                root = Path(temp).resolve()
                command, env, workdir = _prepare(root, choice, system, schema, allow_web)
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise TimeoutError
                returncode, stdout, stderr = await _run(command, env, workdir, user, remaining)
            output_text, tokens, status = _read_events(stdout, allow_web)
            entry.update(tokens)
            if status or returncode != 0:
                entry["why"] = status if status == "unexpected_tool" else _exit_reason(stdout, stderr)
                if entry["why"] == "workspace_config" and b'"turn.started"' not in stdout:
                    # 모델 차례를 시작하기도 전에 끝난 CLI 실행이다.
                    entry.update(input_tokens=0, output_tokens=0)
                    raise _WorkspaceConfigUnavailable(f"{task}: Codex 호출 실패 (workspace_config)")
                raise LLMError(f"{task}: Codex 호출 실패 ({entry['why']})")
            try:
                data = json.loads(output_text)
            except ValueError:
                data = None
            if not isinstance(data, dict):
                entry["why"] = "unreadable"
                raise LLMError(f"{task}: 정해진 형식의 답을 읽지 못했어요")
            result = _restore_optional(data, schema)
            entry["ok"] = True
            return result
        except asyncio.CancelledError:
            entry["why"] = "cancelled"
            raise
        except TimeoutError:
            entry["why"] = "timeout"
            raise LLMTimeout(f"{task}: Codex 호출 시간이 초과됐어요") from None
        except FileNotFoundError:
            entry["why"] = "cli_missing"
            raise LLMError(f"{task}: Codex CLI 또는 격리 실행기를 찾지 못했어요") from None
        except OSError:
            entry["why"] = "process_error"
            raise LLMError(f"{task}: Codex 실행 환경을 준비하지 못했어요") from None
        finally:
            from llm import usage

            entry["sec"] = round(loop.time() - started, 3)
            self.log.append(entry)
            note_call(entry)
            cost_input = (0 if entry.get("why") == "workspace_config" and entry.get("input_tokens") == 0 else
                          usage.estimate_direct_api_input(system, user, _strict_schema(schema)))
            usage.record({**entry, "cost_input_tokens": cost_input}, system=system, user=user, output=output_text)


def _prepare(root: Path, choice: ModelChoice, system: str, schema: dict[str, Any],
             web: bool) -> tuple[list[str], dict[str, str], Path]:
    executable = shutil.which("codex")
    if executable is None:
        raise FileNotFoundError
    login_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").resolve()
    login_file = (login_home / "auth.json").resolve()
    isolated_home = root / "codex"
    isolated_home.mkdir()
    (isolated_home / "auth.json").symlink_to(login_file)
    workdir = root / "work"
    workdir.mkdir()
    (root / "instructions.txt").write_text(system, encoding="utf-8")
    (root / "schema.json").write_text(json.dumps(_strict_schema(schema), ensure_ascii=False), encoding="utf-8")

    if sys.platform == "darwin":
        sandbox = ["/usr/bin/sandbox-exec", "-D", f"LOGIN_HOME={login_home}", "-D", f"LOGIN_FILE={login_file}",
                   "-p", _MAC_SANDBOX]
    elif sys.platform == "linux" and (bwrap := shutil.which("bwrap")):
        sandbox = [bwrap, "--ro-bind", "/", "/", "--bind", str(root), str(root), "--dev", "/dev", "--proc", "/proc", "--"]
    else:
        raise FileNotFoundError

    # 환경 변수를 골라 전달한다. 대회 키, 게이트웨이 주소, 인증·원격 실행 오버라이드는 넘기지 않는다.
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "LC_CTYPE") if key in os.environ}
    env.update(HOME=str(root), CODEX_HOME=str(isolated_home), TMPDIR=str(root), CODEX_EXEC_SERVER_URL="none")
    config = (*_CONFIG, f'web_search="{"live" if web else "disabled"}"',
              f"model_instructions_file={json.dumps(str(root / 'instructions.txt'))}")
    if choice.effort:
        config += (f"model_reasoning_effort={json.dumps(choice.effort)}",)
    command = [*sandbox, executable, "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral",
               "--skip-git-repo-check", "--sandbox", "read-only", "--json", "--color", "never",
               "--model", choice.model, "--output-schema", str(root / "schema.json"),
               "--enable", "skip_host_skill_discovery"]
    for item in config:
        command.extend(("-c", item))
    for feature in _DISABLED_FEATURES:
        command.extend(("--disable", feature))
    command.append("-")
    return command, env, workdir


async def _run(command: list[str], env: dict[str, str], workdir: Path, user: str,
               timeout: float) -> tuple[int | None, bytes, bytes]:
    spawned = asyncio.create_task(asyncio.create_subprocess_exec(
        *command, env=env, cwd=workdir, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, start_new_session=True,
    ))
    try:
        async with asyncio.timeout(timeout):
            proc = await asyncio.shield(spawned)
            stdout, stderr = await proc.communicate(user.encode("utf-8"))
            return proc.returncode, stdout, stderr
    except (asyncio.CancelledError, TimeoutError):
        # 프로세스 생성 중에도 취소될 수 있다. 생성 결과를 받은 뒤 그룹을 끄고 파이프를 거둔다.
        cleanup = asyncio.create_task(_reap(spawned))
        await asyncio.shield(cleanup)
        raise


async def _reap(spawned: asyncio.Task[asyncio.subprocess.Process]) -> None:
    from llm.cli import _kill

    try:
        proc = await spawned
    except OSError:
        return
    _kill(proc)
    await proc.communicate()


def _read_events(stdout: bytes, web: bool) -> tuple[str, dict[str, int], str | None]:
    output = ""
    tokens: dict[str, int] = {}
    completed = False
    failure = None
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        if event_type == "turn.completed":
            completed = True
            details = event.get("usage")
            if isinstance(details, dict):
                tokens = {key: details[key] for key in _TOKEN_KEYS if type(details.get(key)) is int and details[key] >= 0}
        if event_type == "turn.failed" and failure is None:
            failure = "cli_exit"
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type in _TOOL_EVENTS or (item_type == "web_search" and not web):
            failure = "unexpected_tool"
        if event_type == "item.completed" and item_type == "agent_message" and isinstance(item.get("text"), str):
            output = item["text"]
    return output, tokens, failure or (None if completed else "cli_exit")


def _exit_reason(stdout: bytes, stderr: bytes) -> str:
    error = (stdout + stderr).lower()
    if any(s in error for s in (b"invalid_json_schema", b"invalid schema", b"schema for response_format")):
        return "schema"
    if any(s in error for s in (b"429 too many", b"rate limit", b"usage limit")):
        return "rate_limit"
    if any(s in error for s in (b"401 unauthorized", b"access token", b"login required", b"logging out",
                               b"missing bearer", b"please run codex login")):
        return "authentication"
    if b"failed to load cloud config bundle" in stderr.lower():
        return "workspace_config"
    if any(s in error for s in (b"sandbox_apply", b"error loading config", b"error parsing -c", b"unexpected argument")):
        return "configuration"
    if any(s in error for s in (b"stream disconnected", b"failed to connect", b"error sending request")):
        return "network"
    return "cli_exit"
