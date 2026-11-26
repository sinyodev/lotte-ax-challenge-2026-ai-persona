"""실행별 벽시계 시간과 실제 모델 호출 기록."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any

from shelftest import store

try:
    from llm import usage as model_usage
except ImportError:
    model_usage = None

METRICS = ("input_tokens", "output_tokens", "est_cost_krw", "est_cost_usd", "priced_as")
ACTIVE: dict[str, RunUsage] = {}


def _checkpoint(entries: list[dict[str, Any]]) -> float:
    return max((entry["elapsed_s"] for entry in entries), default=0.0)


class RunUsage:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.before = _checkpoint(store.usage_entries(run_id))
        self.started = time.monotonic()
        self.ended: float | None = None

    def elapsed(self) -> float:
        end = self.ended if self.ended is not None else time.monotonic()
        return self.before + end - self.started

    def _write(self, **entry: Any) -> None:
        store.append_usage(self.run_id, {"elapsed_s": round(self.elapsed(), 3), **entry})

    @contextmanager
    def call(self):
        # 형식 오류로 다시 모델을 부르는 경우와 답을 받기 전에 중단된 호출도 포함한다.
        self._write(calls=1)
        collected = None
        try:
            if model_usage is None:
                yield
            else:
                with model_usage.collect() as collected:
                    yield
        finally:
            summary = collected.summary() if collected is not None else {}
            if summary.get("calls"):
                self._write(calls=summary["calls"] - 1, measured=summary["calls"],
                            **{key: summary.get(key) for key in METRICS})
            else:
                self._write()

    def finish(self) -> None:
        if self.ended is None and ACTIVE.get(self.run_id) is self:
            self.ended = time.monotonic()
            ACTIVE.pop(self.run_id)
            self._write()


def begin(run_id: str) -> RunUsage:
    active = ACTIVE[run_id] = RunUsage(run_id)
    return active


def view(run_id: str) -> dict[str, Any]:
    entries = store.usage_entries(run_id)
    active = ACTIVE.get(run_id)
    elapsed = active.elapsed() if active else _checkpoint(entries)
    calls = sum(e.get("calls", 0) for e in entries)
    measured = [e for e in entries if e.get("measured")]
    complete = bool(calls) and sum(e["measured"] for e in measured) == calls
    totals: dict[str, Any] = {"elapsed_s": round(elapsed, 3), "calls": calls}
    for key in METRICS:
        values = [e.get(key) for e in measured]
        totals[key] = None
        if complete and all(v is not None for v in values):
            if key == "priced_as":
                totals[key] = values[0] if len(set(values)) == 1 else None
            else:
                totals[key] = sum(values)
    return totals
