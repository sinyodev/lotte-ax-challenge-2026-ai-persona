"""공개 API의 표준 텍스트 요금으로 토큰 비용을 추정한다."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Rates:
    input: float
    output: float
    cached_input: float
    cache_write: float
    cache_write_long: float | None = None
    context_threshold: int | None = None
    context_input_multiplier: float = 2
    context_output_multiplier: float = 1.5


# 2026-11-24 확인. 표준 처리의 텍스트 토큰 100만 개당 USD.
# https://developers.openai.com/api/docs/pricing
# 장문 배율은 개별 모델 문서 기준이다. 캐시 쓰기 순서는 30분, 12시간이다.
# https://developers.openai.com/api/docs/guides/prompt-caching
# https://developers.openai.com/api/docs/models/gpt-6.2-astra
# https://developers.openai.com/api/docs/models/gpt-6.2-sol
# https://developers.openai.com/api/docs/models/gpt-6.1-terra
# https://developers.openai.com/api/docs/models/gpt-6-luna
RATES = {
    "gpt-6.2-astra": Rates(8, 40, 0.40, 10, 20, context_threshold=272_000),
    "gpt-6.2-sol": Rates(2, 10, 0.10, 2.50, 5, context_threshold=272_000),
    "gpt-6.1-terra": Rates(1, 5, 0.05, 1.25, 2.50, context_threshold=272_000),
    "gpt-6-luna": Rates(0.10, 0.50, 0.01, 0.125, 0.25, context_threshold=272_000),
    # 2026-11-24 확인. 표준 처리의 토큰 100만 개당 USD. 캐시 쓰기 순서는 5분, 1시간.
    # https://platform.claude.com/docs/en/about-claude/pricing
    "claude-opus-5-5": Rates(4, 20, 0.20, 5, 8),
    "claude-sonnet-5-5": Rates(2, 10, 0.10, 2.50, 4),
    "claude-haiku-5-5": Rates(0.10, 0.50, 0.01, 0.125, 0.20, 100_000, 5, 5),
}

# 표시용 가정 1 USD = 1,400 KRW. 현물 환율을 조회하지 않는다.
DEFAULT_USD_KRW = 1_400.0


def usd_krw() -> float:
    try:
        rate = float(os.environ.get("AX_USD_KRW", str(DEFAULT_USD_KRW)))
    except ValueError:
        return DEFAULT_USD_KRW
    return rate if math.isfinite(rate) and rate > 0 else DEFAULT_USD_KRW


def token_cost_usd(model: str, input_tokens: int, output_tokens: int,
                  cached_input_tokens: int = 0, cache_write_input_tokens: int = 0,
                  long_cache_write_tokens: int = 0) -> float | None:
    """입력 합계에는 캐시 읽기와 쓰기가 포함된다. 도구·게이트웨이 요금은 별도다."""
    rates = RATES.get(model)
    if rates is None:
        return None
    uncached = input_tokens - cached_input_tokens - cache_write_input_tokens
    short_write = cache_write_input_tokens - long_cache_write_tokens
    input_charge = (uncached * rates.input + cached_input_tokens * rates.cached_input
                    + short_write * rates.cache_write
                    + long_cache_write_tokens * (rates.cache_write_long or rates.cache_write))
    output_charge = output_tokens * rates.output
    if rates.context_threshold is not None and input_tokens > rates.context_threshold:
        input_charge *= rates.context_input_multiplier
        output_charge *= rates.context_output_multiplier
    return (input_charge + output_charge) / 1_000_000
