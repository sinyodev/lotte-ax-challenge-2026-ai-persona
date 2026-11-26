"""호출 문맥과 그 문맥을 상속한 작업이 쓴 토큰을 모은다."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from math import fsum

from llm.prices import token_cost_usd, usd_krw


@dataclass(frozen=True)
class _ModelUsage:
    model: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int | None
    estimated: bool
    cost_input_tokens: int
    cost_basis: str
    cost_usd: float | None


@dataclass(frozen=True)
class _Attempt:
    task: str
    sec: float
    ok: bool
    models: tuple[_ModelUsage, ...]


def _totals(rows: list[_ModelUsage], exchange_rate: float) -> dict:
    caches = [row.cached_input_tokens for row in rows]
    costs = [row.cost_usd for row in rows]
    bases = {row.cost_basis for row in rows}
    usd = fsum(costs) if costs and None not in costs else None
    return {
        "input_tokens": sum(row.input_tokens for row in rows),
        "output_tokens": sum(row.output_tokens for row in rows),
        "cached_input_tokens": sum(caches) if None not in caches else None,
        "estimated": any(row.estimated for row in rows),
        "cost_input_tokens": sum(row.cost_input_tokens for row in rows),
        "cost_basis": "mixed" if len(bases) > 1 else next(iter(bases), None),
        "est_cost_usd": usd,
        # 저장소가 호출별 원화 비용을 합한 뒤 화면에서 반올림한다.
        "est_cost_krw": usd * exchange_rate if usd is not None else None,
    }


class Usage:
    def __init__(self) -> None:
        self._attempts: list[_Attempt] = []

    def summary(self) -> dict:
        """현재까지 끝난 시도 요약. 모델별 calls에는 그 모델을 사용한 시도가 잡힌다."""
        attempts = self._attempts.copy()
        rows = [row for attempt in attempts for row in attempt.models]
        models: dict[str, list[_ModelUsage]] = defaultdict(list)
        for row in rows:
            models[row.model].append(row)
        exchange_rate = usd_krw()
        totals = _totals(rows, exchange_rate)
        return {
            **totals,
            "calls": len(attempts),
            "failed_calls": sum(not attempt.ok for attempt in attempts),
            "call_seconds": fsum(attempt.sec for attempt in attempts),
            # 여러 단가가 섞이면 합계는 유효하지만 단일 모델명으로 표시할 수 없다.
            "priced_as": next(iter(models)) if len(models) == 1 and totals["est_cost_usd"] is not None else None,
            "by_model": {
                model: {"calls": len(model_rows), **_totals(model_rows, exchange_rate)}
                for model, model_rows in models.items()
            },
        }


_COLLECTORS: ContextVar[tuple[Usage, ...]] = ContextVar("llm_usage_collectors", default=())


@contextmanager
def collect() -> Iterator[Usage]:
    current = Usage()
    token = _COLLECTORS.set((*_COLLECTORS.get(), current))
    try:
        yield current
    finally:
        _COLLECTORS.reset(token)


def _token_count(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def estimate_direct_api_input(system: str, user: str, strict_schema: dict) -> int:
    """직접 API에 보내는 문자열을 UTF-8 4바이트당 약 1토큰으로 어림한다."""
    # 2026-11-24, Codex CLI 0.172.0에서 지침·스키마를 고정한 한국어 견본의 입력 증가량을 비교했다.
    # 1바이트 입력을 138/680바이트로 늘리면 Luna는 33/175토큰, Sol은 680바이트에서 175토큰 증가했다.
    # 이 식의 증가량은 34/169토큰이다. API 쪽에서 붙이는 메시지 형식은 포함하지 않는다.
    schema_text = json.dumps(strict_schema, ensure_ascii=False, separators=(",", ":"))
    return sum((len(text.encode("utf-8")) + 3) // 4 for text in (system, user, schema_text))


def _model_usage(entry: dict, *, input_chars: int, output_chars: int) -> _ModelUsage:
    model = entry["model"]
    input_tokens = _token_count(entry.get("input_tokens"))
    measured_output = _token_count(entry.get("output_tokens"))
    direct_input = _token_count(entry.get("cost_input_tokens"))
    cached = _token_count(entry.get("cached_input_tokens"))
    # 캐시 읽기 수가 없으면 일반 입력 단가를 적용한다. 쓰기 수명의 세부값이 없으면 기본 단가를 적용한다.
    writes = _token_count(entry.get("cache_write_input_tokens")) or 0
    long_writes = sum(_token_count(entry.get(key)) or 0
                      for key in ("cache_write_1h_input_tokens", "cache_write_12h_input_tokens"))
    cache_tokens = (cached or 0) + writes
    estimated = (direct_input is not None or input_tokens is None or measured_output is None
                 or entry.get("estimated") is True)
    # 토크나이저를 쓸 수 없을 때 글자 4개당 약 1토큰으로 가정한다.
    if input_tokens is None:
        input_tokens = max((input_chars + 3) // 4, cache_tokens)
    output_tokens = measured_output if measured_output is not None else (output_chars + 3) // 4
    cost_input_tokens = input_tokens if direct_input is None else direct_input
    cost_basis = "adapter_usage"
    cost = None
    if direct_input is not None:
        # 실행기 캐시 적중은 직접 API에서 재현된 것으로 보지 않는다.
        cost_basis = "direct_api_uncached_estimate"
        if entry.get("priceable", True) and measured_output is not None:
            cost = token_cost_usd(model, direct_input, measured_output)
    elif entry.get("priceable", True) and cache_tokens <= input_tokens and long_writes <= writes:
        cost = token_cost_usd(model, input_tokens, output_tokens, cached or 0, writes, long_writes)
    if cached is not None and cached > input_tokens:
        cached = None
    return _ModelUsage(model, input_tokens, output_tokens, cached, estimated, cost_input_tokens, cost_basis, cost)


def record(entry: dict, *, system: str, user: str, output: str) -> None:
    """시도 하나를 기록한다. 본문은 토큰 추정에 쓰고 버린다.

    input_tokens는 cached_input_tokens를 포함한다. CLI가 모델별 수치를
    반환하면 model_usage의 각 행을 사용해도 호출 수와 시간은 한 번만 센다.
    cost_input_tokens가 있으면 실측 입력과 별도로 첫 API 호출의 비용을 추정한다.
    """
    collectors = _COLLECTORS.get()
    if not collectors:
        return
    models = tuple(_model_usage(row, input_chars=len(system) + len(user), output_chars=len(output))
                   for row in (entry.get("model_usage") or (entry,)))
    attempt = _Attempt(entry["task"], entry["sec"], entry["ok"], models)
    for collector in collectors:
        collector._attempts.append(attempt)
