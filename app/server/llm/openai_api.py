"""대회 게이트웨이에서 Responses API의 구조화된 답을 받는다."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
from contextvars import ContextVar
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from httpx2 import URL, AsyncClient, InvalidURL, Request
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, OpenAIError

from llm import usage
from llm.base import LLMError, LLMTimeout, note_call
from llm.models import choice_for_call
from llm.schema import _restore_optional, _strict_schema


_ENV_FILE = Path(__file__).resolve().parents[1] / ".env.local"
_SETTING_NAMES = ("OPENAI_BASE_URL", "OPENAI_API_KEY")
_BACKOFF = (0.5, 1.0)
_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}\Z")
_IN_GATEWAY_CALL: ContextVar[bool] = ContextVar("openai_gateway_call", default=False)


def _allow_dependency_log(_record: logging.LogRecord) -> bool:
    return not _IN_GATEWAY_CALL.get()


def _guard_dependency_logs() -> None:
    # HTTPX의 URL, SDK의 요청 ID, HTTP Core의 응답 헤더가 기록될 수 있다.
    # 이 호출 문맥의 로그만 막으므로 다른 HTTP 요청에는 영향이 없다.
    for name in ("openai", "openai._base_client", "openai._response", "openai._legacy_response",
                 "openai.resources.responses.responses", "httpx", "httpx2"):
        logging.getLogger(name).addFilter(_allow_dependency_log)
    for library in ("httpcore", "httpcore2"):
        for name in ("connection", "http11", "http2", "proxy", "socks"):
            logging.getLogger(f"{library}.{name}").addFilter(_allow_dependency_log)


def _credentials() -> tuple[URL, str]:
    values = {name: os.environ.get(name, "").strip() for name in _SETTING_NAMES}
    missing = {name for name, value in values.items() if not value}
    if missing:
        unreadable = False
        try:
            lines = _ENV_FILE.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            lines = []
        except (OSError, UnicodeError):
            unreadable = True
        if unreadable:
            names = ", ".join(name for name in _SETTING_NAMES if name in missing)
            raise LLMError(f".env.local을 읽지 못했어요. {names} 환경 변수를 확인해 주세요")
        for line in lines:
            name, separator, raw_value = line.partition("=")
            name = name.strip()
            if separator and name in missing:
                value = raw_value.strip()
                if len(value) >= 2 and value[0] in "\"'" and value[0] == value[-1]:
                    value = value[1:-1].strip()
                values[name] = value

    absent = [name for name, value in values.items() if not value]
    if absent:
        raise LLMError(f"대회 게이트웨이 설정에 {', '.join(absent)} 값이 필요해요")

    key = values["OPENAI_API_KEY"]
    if any(not 33 <= ord(char) <= 126 for char in key):
        raise LLMError("OPENAI_API_KEY 설정 형식을 확인해 주세요")
    try:
        url = URL(values["OPENAI_BASE_URL"])
    except (InvalidURL, ValueError):
        url = None
    if (url is None or url.scheme not in ("http", "https") or not url.host or "%" in url.host or url.userinfo
            or url.fragment or url.host.rstrip(".").lower() == "api.openai.com"):
        raise LLMError("OPENAI_BASE_URL에 대회 게이트웨이 주소를 설정해 주세요")
    return url, key


def _retry_after(headers: Any) -> float | None:
    for name, divisor in (("retry-after", 1), ("retry-after-ms", 1000)):
        value = headers.get(name)
        if value is None:
            continue
        try:
            seconds = float(value) / divisor
        except ValueError:
            if name != "retry-after":
                continue
            try:
                date = parsedate_to_datetime(value)
                if date.tzinfo is None:
                    date = date.replace(tzinfo=timezone.utc)
                seconds = max(0.0, (date - datetime.now(timezone.utc)).total_seconds())
            except (ValueError, OverflowError):
                continue
        if math.isfinite(seconds) and seconds >= 0:
            return seconds
    return None


class _RateLimited(LLMError):
    def __init__(self, delay: float | None) -> None:
        super().__init__("대회 게이트웨이의 요청 한도에 걸렸어요")
        self.delay = delay


def _field(value: Any, name: str) -> Any:
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)


def _usage_fields(reported: Any) -> dict[str, int]:
    inputs = _field(reported, "input_tokens_details")
    outputs = _field(reported, "output_tokens_details")
    writes = _field(inputs, "cache_write_tokens_details")
    fields = {
        "input_tokens": _field(reported, "input_tokens"),
        "output_tokens": _field(reported, "output_tokens"),
        "total_tokens": _field(reported, "total_tokens"),
        "reasoning_tokens": _field(outputs, "reasoning_tokens"),
        "cached_input_tokens": _field(inputs, "cached_tokens"),
        "cache_write_input_tokens": _field(inputs, "cache_write_tokens"),
        "cache_write_30m_input_tokens": _field(writes, "ttl_30m_tokens"),
        "cache_write_12h_input_tokens": _field(writes, "ttl_12h_tokens"),
    }
    return {name: value for name, value in fields.items() if type(value) is int and value >= 0}


def _reject_json_constant(_value: str) -> None:
    raise ValueError("정해진 JSON 형식이 아니에요")


class OpenAILLM:
    def __init__(self) -> None:
        self.log: list[dict[str, Any]] = []
        _guard_dependency_logs()

    async def ask(self, task: str, system: str, user: str, schema: dict[str, Any], *,
                  web: bool = False, timeout: float = 60.0, model: str | None = None) -> dict[str, Any]:
        choice = choice_for_call(task, model, backend="openai")
        request: dict[str, Any] = {
            "model": choice.model, "instructions": system, "input": user, "store": False,
            "text": {"format": {"type": "json_schema", "name": "chilseong_reply",
                                "strict": True, "schema": _strict_schema(schema)}},
        }
        if choice.effort:
            request["reasoning"] = {"effort": choice.effort}
        if task == "trend" and web:
            request["tools"] = [{"type": "web_search"}]

        logging_token = _IN_GATEWAY_CALL.set(True)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        try:
            async with asyncio.timeout_at(deadline) as limit:
                url, key = _credentials()
                async with AsyncClient(follow_redirects=False, trust_env=False) as http:
                    try:
                        client = AsyncOpenAI(base_url=str(url.copy_with(query=None)), api_key=key, http_client=http,
                                             timeout=timeout, max_retries=0,
                                             default_headers={"Authorization": f"Bearer {key}"})
                    except (OpenAIError, ValueError, TypeError):
                        client = None
                    if client is None:
                        raise LLMError("대회 게이트웨이 연결 설정을 확인해 주세요")
                    for fallback in (*_BACKOFF, None):
                        if loop.time() >= deadline:
                            break
                        try:
                            return await self._attempt(client, http, url.query, limit, task, request, schema)
                        except _RateLimited as error:
                            if fallback is None:
                                raise
                            delay = fallback if error.delay is None else error.delay
                        if delay >= deadline - loop.time():
                            break
                        await asyncio.sleep(delay)
        except TimeoutError:
            pass
        finally:
            _IN_GATEWAY_CALL.reset(logging_token)
        raise LLMTimeout("대회 게이트웨이 응답을 기다리는 시간이 넘었어요")

    async def _attempt(self, client: AsyncOpenAI, http: AsyncClient, query: bytes, limit: asyncio.Timeout,
                       task: str, request: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        started = loop.time()
        sent = False
        entry: dict[str, Any] = {"task": task, "model": request["model"], "ok": False}
        output = ""

        async def before_send(outgoing: Request) -> None:
            nonlocal sent
            if query:
                outgoing.url = outgoing.url.copy_with(query=query)
            sent = True

        http.event_hooks["request"] = [before_send]
        try:
            response = await client.responses.create(**request)
            reported_model = _field(response, "model")
            if isinstance(reported_model, str) and _MODEL_ID.fullmatch(reported_model):
                entry["model"] = reported_model
            entry.update(_usage_fields(_field(response, "usage")))
            response_text = getattr(response, "output_text", "")
            output = response_text if isinstance(response_text, str) else ""
            status = _field(response, "status")
            if status != "completed":
                entry["why"] = "incomplete" if status == "incomplete" else "response_error"
                raise LLMError("대회 게이트웨이에서 완료된 답을 받지 못했어요")
            if not output.strip():
                entry["why"] = "empty"
                raise LLMError("대회 게이트웨이에서 빈 답을 받았어요")
            try:
                data = json.loads(output, parse_constant=_reject_json_constant)
            except (ValueError, RecursionError):
                data = None
            if not isinstance(data, dict):
                entry["why"] = "unreadable"
                raise LLMError("대회 게이트웨이의 답을 정해진 형식으로 읽지 못했어요")
            result = _restore_optional(data, schema)
            entry["ok"] = True
            return result
        except asyncio.CancelledError:
            entry["why"] = "timeout" if limit.expired() else "cancelled"
            raise
        except (APITimeoutError, TimeoutError):
            entry["why"] = "timeout"
            error = LLMTimeout("대회 게이트웨이 응답을 기다리는 시간이 넘었어요")
        except APIStatusError as exc:
            reported = _field(exc.body, "usage")
            if reported is None:
                # SDK의 예외 본문에는 바깥 응답의 usage가 빠질 수 있다.
                try:
                    reported = _field(exc.response.json(), "usage")
                except (ValueError, RecursionError):
                    pass
            entry.update(_usage_fields(reported))
            if exc.status_code == 429:
                entry["why"] = "rate_limit"
                error = _RateLimited(_retry_after(exc.response.headers))
            else:
                entry["why"] = "http_error"
                error = LLMError(f"대회 게이트웨이 요청에 실패했어요 (HTTP {exc.status_code})")
        except APIConnectionError:
            entry["why"] = "network"
            error = LLMError("대회 게이트웨이에 연결하지 못했어요")
        except (OpenAIError, ValueError, TypeError, AttributeError):
            entry["why"] = "response_error"
            error = LLMError("대회 게이트웨이의 응답을 처리하지 못했어요")
        finally:
            if sent:
                if not entry["ok"] and not {"input_tokens", "output_tokens"} <= entry.keys():
                    entry["priceable"] = False
                entry["sec"] = round(loop.time() - started, 3)
                self.log.append(entry)
                note_call(entry)
                usage.record(entry, system=request["instructions"], user=request["input"], output=output)
        # SDK 예외에 포함된 본문, URL, 인증 정보를 앱의 예외와 연결하지 않는다.
        raise error
