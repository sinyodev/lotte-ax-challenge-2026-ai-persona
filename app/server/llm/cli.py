"""Claude Code 명령줄(claude -p)로 부른다. API 열쇠 없이 요금제 로그인으로 돈다.

- 작업 폴더는 저장소 밖의 빈 임시 폴더다. 저장소의 안내 파일이나 기억이 딸려 들어가지 않게 한다.
- 설정 파일(--setting-sources "")과 MCP(--strict-mcp-config)를 읽지 않고, 대화를 저장하지 않는다.
- 도구는 모두 막는다. 흐름 찾기(web=True)에서만 웹 검색 하나를 허용한다.
- 시간이 넘으면 프로세스를 끄고 LLMError.
- 화면이 멈춰 차례가 취소되면(asyncio.CancelledError) 프로세스 묶음을 끄고 "[llm] … 취소함"을 남긴다(지시서 11).
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import tempfile
from typing import Any

from llm import usage
from llm.base import LLMError, LLMTimeout, note_call
from llm.models import choice_for_call

DEFAULT_MODEL = "claude-opus-5-5"


class CliLLM:
    def __init__(self, model: str | None = None) -> None:
        self._override = model
        self.model = model or os.environ.get("AX_CLI_MODEL", DEFAULT_MODEL)
        self.log: list[dict[str, Any]] = []  # 부른 기록(일, 걸린 시간, 성공)

    def command(self, system: str, schema: dict[str, Any], web: bool, model: str | None = None,
                effort: str | None = None) -> list[str]:
        cmd = ["claude", "-p", "--model", model or self.model, "--system-prompt", system,
               "--setting-sources", "", "--strict-mcp-config", "--no-session-persistence",
               "--output-format", "json", "--json-schema", json.dumps(schema, ensure_ascii=False)]
        if effort:
            cmd += ["--effort", effort]
        if web:
            cmd += ["--tools", "WebSearch", "--allowedTools", "WebSearch"]
        else:
            cmd += ["--tools", ""]
        return cmd

    def _log(self, entry: dict[str, Any]) -> None:
        self.log.append(entry)
        note_call(entry)

    async def ask(self, task: str, system: str, user: str, schema: dict[str, Any], *,
                  web: bool = False, timeout: float = 60.0, model: str | None = None) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        started = loop.time()
        choice = choice_for_call(task, model or self._override, backend="cli")
        entry = {"task": task, "model": choice.model, "ok": False}
        proc = None
        output = ""
        print(f"[llm] {task} 부름", file=sys.stderr, flush=True)
        try:
            with tempfile.TemporaryDirectory(prefix="chilseong-", ignore_cleanup_errors=True) as workdir:
                # 새 프로세스 묶음으로 띄워 취소·시간 초과 때 딸린 프로세스도 끈다.
                proc = await asyncio.create_subprocess_exec(
                    *self.command(system, schema, web, choice.model, choice.effort), cwd=workdir,
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    start_new_session=True,
                )
                out, _ = await asyncio.wait_for(proc.communicate(user.encode("utf-8")), timeout=timeout)
            try:
                events = json.loads(out)
                events = events if isinstance(events, list) else [events]
                result = next(e for e in reversed(events) if isinstance(e, dict) and e.get("type") == "result")
            except (ValueError, StopIteration) as e:
                entry["why"] = "unreadable"
                raise LLMError(f"{task}: 답을 읽지 못했어요") from e
            entry.update(_result_usage(result, events, entry["model"]))
            data = result.get("structured_output")
            if not result.get("is_error"):
                if isinstance(data, dict):
                    output = json.dumps(data, ensure_ascii=False)
                elif isinstance(result.get("result"), str):
                    output = result["result"]
            if result.get("is_error") or not isinstance(data, dict):
                entry["why"] = "no structured output"
                raise LLMError(f"{task}: 정해진 형식의 답이 없어요")
            entry["ok"] = True
            return data
        except asyncio.CancelledError:
            entry["why"] = "cancelled"
            if proc is not None:
                _kill(proc)
            raise
        except asyncio.TimeoutError as e:
            entry["why"] = "timeout"
            if proc is not None:
                _kill(proc)
                await proc.wait()
            raise LLMTimeout(f"{task}: {timeout:.0f}초가 넘었어요") from e
        except OSError as e:
            entry["why"] = "subprocess"
            if proc is not None:
                _kill(proc)
            raise LLMError(f"{task}: 모델을 부르지 못했어요") from e
        finally:
            seconds = loop.time() - started
            entry["sec"] = seconds
            usage.record(entry, system=system, user=user, output=output)
            self._log({**entry, "sec": round(seconds, 1)})
            status = {
                "cancelled": "취소함", "timeout": "시간 넘음", "unreadable": "답을 읽지 못함",
                "no structured output": "형식 없음", "subprocess": "모델을 부르지 못함",
            }.get(entry.get("why"), "" if entry["ok"] else "실패함")
            print(f"[llm] {task} {seconds:.1f}초 {status}".rstrip(), file=sys.stderr, flush=True)


def _result_usage(result: dict, events: list, requested_model: str) -> dict:
    """Claude Code의 결과에 있는 집계와 모델별 수치를 한 번씩만 읽는다.

    https://code.claude.com/docs/en/agent-sdk/cost-tracking.md
    """
    raw_usage = result.get("usage")
    aggregate = raw_usage if isinstance(raw_usage, dict) else {}
    init_model = next((event.get("model") for event in events if isinstance(event, dict)
                       and event.get("type") == "system" and event.get("subtype") == "init"), None)
    actual = next((name for name in (result.get("model"), init_model) if isinstance(name, str) and name), None)
    breakdown = result.get("modelUsage")
    if not isinstance(breakdown, dict):
        breakdown = {}
    if len(breakdown) > 1:
        model = actual or requested_model
        aggregate_counts = _claude_tokens(aggregate, {})
        models = {name: _claude_tokens({}, counts) for name, counts in breakdown.items() if isinstance(counts, dict)}
        if len(models) == len(breakdown) and all({"input_tokens", "output_tokens"} <= row.keys()
                                                 for row in models.values()):
            return {"model": model, **aggregate_counts,
                    "model_usage": [{"model": name, **counts} for name, counts in models.items()]}
        return {"model": model, **aggregate_counts, "priceable": False}
    model = next(iter(breakdown), actual or requested_model)
    model_counts = breakdown.get(model)
    cache_creation = aggregate.get("cache_creation")
    long_write = cache_creation.get("ephemeral_1h_input_tokens") if isinstance(cache_creation, dict) else None
    return {"model": model, **_claude_tokens(aggregate, model_counts if isinstance(model_counts, dict) else {}),
            "cache_write_1h_input_tokens": long_write}


def _claude_tokens(aggregate: dict, model_counts: dict) -> dict[str, int]:
    counts = {}
    for name, total_key, model_key in (
        ("input_tokens", "input_tokens", "inputTokens"),
        ("output_tokens", "output_tokens", "outputTokens"),
        ("cached_input_tokens", "cache_read_input_tokens", "cacheReadInputTokens"),
        ("cache_write_input_tokens", "cache_creation_input_tokens", "cacheCreationInputTokens"),
    ):
        for value in (model_counts.get(model_key), aggregate.get(total_key)):
            if type(value) is int and value >= 0:
                counts[name] = value
                break
    if "input_tokens" in counts:
        # Claude의 input_tokens에는 캐시에서 읽거나 캐시에 쓴 입력이 빠져 있다.
        counts["input_tokens"] += counts.get("cached_input_tokens", 0) + counts.get("cache_write_input_tokens", 0)
    return counts


def _kill(proc: asyncio.subprocess.Process) -> None:
    """프로세스 묶음 전체를 끈다. 기다리지 않는다(취소된 차례 안에서는 다시 기다릴 수 없다). 거두는 것은 asyncio가 한다."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass
