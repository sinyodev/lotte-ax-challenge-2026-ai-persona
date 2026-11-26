import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import httpx2
import pytest

from agent.steps import fast_model
from agent.voice import voice_model
from llm import base, openai_api, usage
from llm.base import LLMError, LLMTimeout, TURN_CALLS
from shelftest.runner import shopper_model


HOST = "gateway.fixture.invalid"
URL = f"https://{HOST}/fixture/v1"
KEY = "fixture-authorization-value"
SYSTEM = "꾸민 지침 본문"
USER = "꾸민 사용자 원문"
OUTPUT = '{"rows":[{"text":"꾸민 답","number":null,"required_null":null}]}'
SCHEMA = {
    "type": "object", "required": ["rows"],
    "properties": {"rows": {"type": "array", "items": {
        "type": "object", "required": ["text", "required_null"],
        "properties": {"text": {"type": "string"}, "number": {"type": "integer"},
                       "required_null": {"type": ["string", "null"]}},
    }}},
}
USAGE = {
    "input_tokens": 100, "output_tokens": 20, "total_tokens": 120,
    "input_tokens_details": {"cached_tokens": 40, "cache_write_tokens": 8,
                             "cache_write_tokens_details": {"ttl_30m_tokens": 6, "ttl_12h_tokens": 2}},
    "output_tokens_details": {"reasoning_tokens": 11},
}


def _response(output=OUTPUT, *, status="completed", model="gpt-6-luna", tokens=USAGE, web=False):
    items = [{"type": "web_search_call", "status": "completed", "id": "ws-fixture"}] if web else []
    if output is not None:
        items.append({"type": "message", "role": "assistant", "status": status, "id": "msg-fixture",
                      "content": [{"type": "output_text", "text": output, "annotations": []}]})
    return httpx.Response(200, json={"id": "resp-fixture", "object": "response", "status": status,
                                     "model": model, "usage": tokens, "output": items})


@pytest.fixture
def gateway(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_BASE_URL", URL)
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    monkeypatch.delenv("OPENAI_CUSTOM_HEADERS", raising=False)
    for role in ("READ", "PLAN", "SHOPPER", "INTERVIEW", "VOICE"):
        monkeypatch.delenv(f"AX_MODEL_{role}", raising=False)
        monkeypatch.delenv(f"AX_EFFORT_{role}", raising=False)
    for name in ("AX_SHOPPER_MODEL", "AX_VOICE_MODEL"):
        monkeypatch.delenv(name, raising=False)

    dotenv = tmp_path / ".env.local"
    monkeypatch.setattr(openai_api, "_ENV_FILE", dotenv)
    requests = []

    async def forbidden(_request):
        raise AssertionError("전송 시도가 없어야 해요")

    def mock(handler=forbidden):
        async def capture(request):
            assert request.url.host == HOST
            requests.append(request)
            return await handler(request)

        monkeypatch.setattr(openai_api, "AsyncClient", lambda **options: httpx.AsyncClient(
            transport=httpx.MockTransport(capture), **options,
        ))

    mock()
    return dotenv, requests, mock


def _ask(llm, **options):
    return llm.ask("ideas", SYSTEM, USER, SCHEMA, **options)


def test_strict_response_and_measured_cost(gateway, monkeypatch):
    dotenv, requests, mock = gateway
    dotenv.mkdir()  # 환경에 두 값이 있으면 읽을 수 없는 파일 경로에도 손대지 않는다.
    monkeypatch.setenv("OPENAI_CUSTOM_HEADERS", "authorization: Bearer fixture-ignored")
    monkeypatch.setenv("AX_MODEL_PLAN", "fixture-route")
    records = []
    record_usage = usage.record

    def record(entry, **texts):
        records.append((entry.copy(), texts))
        record_usage(entry, **texts)

    async def handle(_request):
        return _response()

    mock(handle)
    monkeypatch.setattr(usage, "record", record)
    llm = openai_api.OpenAILLM()
    turn = []
    token = TURN_CALLS.set(turn)
    try:
        with usage.collect() as meter:
            result = asyncio.run(_ask(llm))
    finally:
        TURN_CALLS.reset(token)

    assert result == {"rows": [{"text": "꾸민 답", "required_null": None}]}
    sent, = requests
    assert sent.method == "POST" and str(sent.url) == f"{URL}/responses"
    assert sent.headers["authorization"] == f"Bearer {KEY}"
    payload = json.loads(sent.content)
    assert payload["model"] == "fixture-route" and payload["reasoning"] == {"effort": "low"}
    assert payload["instructions"] == SYSTEM and payload["input"] == USER and payload["store"] is False
    assert "tools" not in payload
    response_format = payload["text"]["format"]
    assert response_format["type"] == "json_schema" and response_format["strict"] is True
    strict = response_format["schema"]
    assert strict["additionalProperties"] is False
    item = strict["properties"]["rows"]["items"]
    assert item["additionalProperties"] is False and item["required"] == ["text", "number", "required_null"]
    assert item["properties"]["number"] == {"anyOf": [{"type": "integer"}, {"type": "null"}]}
    assert SCHEMA["properties"]["rows"]["items"]["required"] == ["text", "required_null"]

    entry, = llm.log
    assert turn == [entry]
    assert records == [(entry, {"system": SYSTEM, "user": USER, "output": OUTPUT})]
    assert entry["ok"] and entry["model"] == "gpt-6-luna" and entry["total_tokens"] == 120
    assert entry["reasoning_tokens"] == 11 and entry["cache_write_12h_input_tokens"] == 2
    assert entry["cache_write_30m_input_tokens"] == 6
    summary = meter.summary()
    assert summary["calls"] == 1 and summary["failed_calls"] == 0 and summary["estimated"] is False
    assert summary["priced_as"] == "gpt-6-luna" and summary["cached_input_tokens"] == 40
    assert summary["input_tokens"] == 100 and summary["output_tokens"] == 20
    assert summary["est_cost_usd"] == pytest.approx((52 * 0.10 + 40 * 0.01 + 6 * 0.125 + 2 * 0.25
                                                    + 20 * 0.50) / 1e6)


def test_app_entry_routes_roles_effort_and_web(monkeypatch, gateway):
    _, requests, mock = gateway
    monkeypatch.setenv("AX_LLM", "openai")
    for role, effort in (("READ", "low"), ("PLAN", "medium"), ("SHOPPER", "none"),
                         ("INTERVIEW", "high"), ("VOICE", "minimal")):
        monkeypatch.setenv(f"AX_MODEL_{role}", f"fixture-{role.lower()}")
        monkeypatch.setenv(f"AX_EFFORT_{role}", effort)

    async def handle(request):
        payload = json.loads(request.content)
        return _response(web="tools" in payload)

    mock(handle)
    llm = base.get_llm()
    assert isinstance(llm, openai_api.OpenAILLM)

    async def run():
        await llm.ask("read_first", SYSTEM, USER, SCHEMA, model=fast_model(), web=True)
        await llm.ask("trend", SYSTEM, USER, SCHEMA, web=True)
        await llm.ask("trend", SYSTEM, USER, SCHEMA)
        await llm.ask("shopper", SYSTEM, USER, SCHEMA, model=shopper_model())
        await llm.ask("interview", SYSTEM, USER, SCHEMA, model=shopper_model())
        await llm.ask("group_turn", SYSTEM, USER, SCHEMA, model="fixture-explicit")
        await llm.ask("voice", SYSTEM, USER, SCHEMA, model=voice_model())

    asyncio.run(run())
    bodies = [json.loads(request.content) for request in requests]
    assert [(body["model"], body["reasoning"]["effort"]) for body in bodies] == [
        ("fixture-read", "low"), ("fixture-plan", "medium"), ("fixture-plan", "medium"),
        ("fixture-shopper", "none"), ("fixture-interview", "high"), ("fixture-explicit", "high"),
        ("fixture-voice", "minimal"),
    ]
    assert [body.get("tools") for body in bodies] == [None, [{"type": "web_search"}], None, None, None, None, None]


def test_native_sdk_transport_handles_query_without_logging_it(gateway, monkeypatch, caplog):
    query = "fixture-native-private-query"
    monkeypatch.setenv("OPENAI_BASE_URL", f"{URL}?token={query}")
    requests = []

    async def handle(request):
        requests.append(request)
        return httpx2.Response(200, json=_response().json())

    monkeypatch.setattr(openai_api, "AsyncClient", lambda **options: httpx2.AsyncClient(
        transport=httpx2.MockTransport(handle), **options,
    ))
    with caplog.at_level(logging.DEBUG):
        asyncio.run(_ask(openai_api.OpenAILLM()))
    request, = requests
    assert str(request.url) == f"{URL}/responses?token={query}"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert all(secret not in caplog.text for secret in (query, KEY, SYSTEM, USER))


@pytest.mark.parametrize("missing", ["OPENAI_BASE_URL", "OPENAI_API_KEY", "both"])
def test_dotenv_fills_missing_values_only(monkeypatch, gateway, missing):
    dotenv, requests, mock = gateway
    dotenv.write_text(f'# fixture\nOPENAI_BASE_URL = "{URL}/fallback?fixture=alpha%2Bbeta&fixture=two"\n'
                      'IGNORED=value\nOPENAI_API_KEY = \'fixture-file-key=\'\n', encoding="utf-8")
    file_url = missing in ("OPENAI_BASE_URL", "both")
    file_key = missing in ("OPENAI_API_KEY", "both")
    if file_url:
        monkeypatch.delenv("OPENAI_BASE_URL")
    if file_key:
        monkeypatch.setenv("OPENAI_API_KEY", "   ")

    async def handle(_request):
        return _response()

    mock(handle)
    asyncio.run(_ask(openai_api.OpenAILLM()))
    sent, = requests
    suffix = "/fallback/responses?fixture=alpha%2Bbeta&fixture=two" if file_url else "/responses"
    assert str(sent.url) == URL + suffix
    assert sent.headers["authorization"] == "Bearer " + ("fixture-file-key=" if file_key else KEY)


@pytest.mark.parametrize("names", [("OPENAI_API_KEY",), ("OPENAI_BASE_URL",), ("OPENAI_API_KEY", "OPENAI_BASE_URL")])
def test_missing_settings_never_send_or_record(gateway, monkeypatch, names):
    _, requests, _ = gateway
    monkeypatch.setenv("OPENAI_BASE_URL", f"{URL}?fixture=secret-query")
    for name in names:
        monkeypatch.delenv(name)
    llm = openai_api.OpenAILLM()
    with usage.collect() as meter, pytest.raises(LLMError) as failure:
        asyncio.run(_ask(llm))
    assert all(name in str(failure.value) for name in names)
    assert KEY not in str(failure.value) and "secret-query" not in str(failure.value)
    assert not (llm.log or requests) and meter.summary()["calls"] == 0


@pytest.mark.parametrize(("setting", "value"), [
    ("OPENAI_BASE_URL", "https://api.openai.com/v1?fixture=secret-query"),
    ("OPENAI_BASE_URL", "https://bad[.invalid/v1?fixture=secret-query"),
    ("OPENAI_API_KEY", "fixture\nsecret-query"),
])
def test_invalid_settings_are_safe(gateway, monkeypatch, setting, value):
    _, requests, _ = gateway
    monkeypatch.setenv(setting, value)
    with pytest.raises(LLMError, match=setting) as failure:
        asyncio.run(_ask(openai_api.OpenAILLM()))
    assert "secret-query" not in str(failure.value) and failure.value.__context__ is None
    assert not requests


def test_429_uses_retry_after_and_records_each_send(gateway, monkeypatch):
    _, requests, mock = gateway
    delays = []
    delay_date = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=5), usegmt=True)

    async def sleep(delay):
        delays.append(delay)

    async def handle(_request):
        if len(requests) == 1:
            return httpx.Response(429, headers={"Retry-After": "0.25", "retry-after-ms": "5"},
                                  json={"error": {"message": USER}})
        if len(requests) == 2:
            return httpx.Response(429, headers={"Retry-After": delay_date}, json={"error": {"message": KEY}})
        return _response()

    monkeypatch.setattr(openai_api.asyncio, "sleep", sleep)
    mock(handle)
    llm = openai_api.OpenAILLM()
    turn = []
    token = TURN_CALLS.set(turn)
    try:
        with usage.collect() as meter:
            asyncio.run(_ask(llm, timeout=10, model="gpt-6-luna"))
    finally:
        TURN_CALLS.reset(token)

    assert len(requests) == 3 and all(r.content == requests[0].content for r in requests)
    assert [r.headers["x-stainless-retry-count"] for r in requests] == ["0", "0", "0"]
    assert len(delays) == 2 and delays[0] == 0.25 and 3 < delays[1] <= 5
    assert turn == llm.log and [item.get("why") for item in turn] == ["rate_limit", "rate_limit", None]
    summary = meter.summary()
    assert summary["calls"] == 3 and summary["failed_calls"] == 2
    assert summary["estimated"] is True and summary["est_cost_usd"] is None
    assert summary["output_tokens"] == 20 and summary["input_tokens"] > 100


def test_rate_limit_backoff_is_bounded(gateway, monkeypatch):
    _, requests, mock = gateway
    delays = []

    async def sleep(delay):
        delays.append(delay)

    async def handle(_request):
        return httpx.Response(429, headers={"Retry-After": "invalid-fixture"}, json={"error": {"message": USER}})

    monkeypatch.setattr(openai_api.asyncio, "sleep", sleep)
    mock(handle)
    llm = openai_api.OpenAILLM()
    with usage.collect() as meter, pytest.raises(LLMError, match="요청 한도") as failure:
        asyncio.run(_ask(llm))
    assert failure.value.__context__ is None
    assert delays == [0.5, 1.0] and len(llm.log) == len(requests) == meter.summary()["failed_calls"] == 3


@pytest.mark.parametrize("code", [302, 401, 500])
def test_http_failure_keeps_secrets_out_of_logs_and_does_not_retry(gateway, monkeypatch, caplog, code):
    _, requests, mock = gateway
    query = "fixture-private-query"
    monkeypatch.setenv("OPENAI_BASE_URL", f"{URL}?token={query}")

    async def handle(_request):
        return httpx.Response(code, headers={"location": "https://redirect.fixture.invalid/responses",
                                             "x-request-id": f"{KEY} {query}"},
                              json={"error": {"message": f"{SYSTEM} {USER} {KEY} {query}"}})

    mock(handle)
    llm = openai_api.OpenAILLM()
    with caplog.at_level(logging.DEBUG), pytest.raises(LLMError, match=f"HTTP {code}") as failure, usage.collect() as meter:
        asyncio.run(_ask(llm))

    assert failure.value.__context__ is None and failure.value.__cause__ is None
    for secret in (SYSTEM, USER, KEY, URL, query):
        assert secret not in str(failure.value) and secret not in caplog.text and secret not in str(llm.log)
    assert len(requests) == len(llm.log) == meter.summary()["failed_calls"] == 1
    assert llm.log[0]["why"] == "http_error" and meter.summary()["est_cost_usd"] is None


def test_http_failure_preserves_reported_usage(gateway):
    _, _, mock = gateway

    async def handle(_request):
        return httpx.Response(500, json={"error": {"message": USER}, "usage": USAGE})

    mock(handle)
    with usage.collect() as meter, pytest.raises(LLMError):
        asyncio.run(_ask(openai_api.OpenAILLM(), model="gpt-6-luna"))
    summary = meter.summary()
    assert summary["calls"] == summary["failed_calls"] == 1
    assert summary["input_tokens"] == 100 and summary["output_tokens"] == 20
    assert summary["estimated"] is False and summary["est_cost_usd"] > 0


@pytest.mark.parametrize(("status", "output", "reason"), [
    ("incomplete", '{"rows":', "incomplete"), ("failed", None, "response_error"),
    ("completed", None, "empty"), ("completed", "  ", "empty"),
    ("completed", "```{unreadable}```", "unreadable"), ("completed", "[]", "unreadable"),
    ("completed", '{"rows":NaN}', "unreadable"),
])
def test_failed_answers_keep_measured_usage(gateway, status, output, reason):
    _, requests, mock = gateway

    async def handle(_request):
        return _response(output, status=status)

    mock(handle)
    llm = openai_api.OpenAILLM()
    with usage.collect() as meter, pytest.raises(LLMError):
        asyncio.run(_ask(llm))
    summary = meter.summary()
    assert summary["calls"] == summary["failed_calls"] == len(requests) == 1
    assert llm.log[0]["why"] == reason and not llm.log[0]["ok"]
    assert summary["input_tokens"] == 100 and summary["output_tokens"] == 20
    assert summary["estimated"] is False and summary["est_cost_usd"] > 0


def test_success_without_sdk_usage_is_estimated(gateway):
    _, _, mock = gateway

    async def handle(_request):
        return _response(tokens=None)

    mock(handle)
    with usage.collect() as meter:
        asyncio.run(_ask(openai_api.OpenAILLM()))
    summary = meter.summary()
    assert summary["estimated"] and summary["failed_calls"] == 0
    assert summary["input_tokens"] > 0 and summary["output_tokens"] > 0


@pytest.mark.parametrize(("transport_error", "expected_error", "reason"), [
    (httpx.ConnectError, LLMError, "network"), (httpx.ReadTimeout, LLMTimeout, "timeout"),
])
def test_transport_error_is_safe_and_counted_once(gateway, transport_error, expected_error, reason):
    _, requests, mock = gateway

    async def handle(request):
        raise transport_error(f"{KEY} {USER} {request.url}", request=request)

    mock(handle)
    llm = openai_api.OpenAILLM()
    with usage.collect() as meter, pytest.raises(expected_error) as failure:
        asyncio.run(_ask(llm))
    assert failure.value.__context__ is None and KEY not in str(failure.value)
    assert len(requests) == len(llm.log) == meter.summary()["failed_calls"] == 1
    assert llm.log[0]["why"] == reason


def test_retry_after_larger_than_total_budget_never_sends_again(gateway):
    _, requests, mock = gateway

    async def handle(_request):
        return httpx.Response(429, headers={"Retry-After": "60"}, json={"error": {"message": USER}})

    mock(handle)
    llm = openai_api.OpenAILLM()
    with usage.collect() as meter, pytest.raises(LLMTimeout):
        asyncio.run(_ask(llm, timeout=2))
    assert len(requests) == len(llm.log) == meter.summary()["failed_calls"] == 1
    assert llm.log[0]["why"] == "rate_limit"


def test_total_timeout_cancels_the_retry_in_flight(gateway):
    _, requests, mock = gateway

    async def handle(_request):
        if len(requests) == 1:
            return httpx.Response(429, headers={"Retry-After": "0.01"}, json={"error": {"message": USER}})
        await asyncio.Future()

    mock(handle)
    llm = openai_api.OpenAILLM()
    with usage.collect() as meter, pytest.raises(LLMTimeout):
        asyncio.run(_ask(llm, timeout=0.25))
    assert len(requests) == meter.summary()["failed_calls"] == 2
    assert [item["why"] for item in llm.log] == ["rate_limit", "timeout"]


@pytest.mark.parametrize("during_backoff", [False, True])
def test_cancellation_propagates_without_phantom_attempt(gateway, monkeypatch, during_backoff):
    _, requests, mock = gateway
    signal = asyncio.Event()

    async def sleep(_seconds):
        signal.set()
        await asyncio.Future()

    async def handle(_request):
        if during_backoff:
            return httpx.Response(429, headers={"Retry-After": "1"}, json={"error": {"message": USER}})
        signal.set()
        await asyncio.Future()

    if during_backoff:
        monkeypatch.setattr(openai_api.asyncio, "sleep", sleep)
    mock(handle)
    llm = openai_api.OpenAILLM()
    turn = []

    async def run():
        token = TURN_CALLS.set(turn)
        try:
            request_task = asyncio.create_task(_ask(llm))
            await asyncio.wait_for(signal.wait(), timeout=2)
            request_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await request_task
        finally:
            TURN_CALLS.reset(token)

    with usage.collect() as meter:
        asyncio.run(run())
    assert len(requests) == len(turn) == len(llm.log) == meter.summary()["failed_calls"] == 1
    assert turn[0]["why"] == ("rate_limit" if during_backoff else "cancelled")
